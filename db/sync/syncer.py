"""
FeishuSyncer — pulls records from Feishu Bitable into local SQLite.

Strategy:
  - Full sync on first run (sync_cursors has no entry).
  - Incremental sync on subsequent runs: only records updated after last_sync_at.
  - State fields (exec_status, gen_status, pub_status, etc.) are NEVER overwritten
    from Feishu — local DB is authoritative for those.
  - All other fields use Feishu as source of truth.

Usage:
    syncer = FeishuSyncer(feishu_client, table_ids, engine)
    syncer.sync_all()          # sync all tables once
    syncer.sync_skus()         # sync a single table
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from db.models import (
    Sku, Plan, Content, PublishRecord, Material, Tag,
    SyncCursor, make_engine,
)

logger = logging.getLogger(__name__)

# Feishu time fields arrive as millisecond timestamps (int)
def _ms_to_dt(ms: Any) -> datetime | None:
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def _list_field(val: Any) -> str | None:
    """Convert a Feishu multi-select (list of str) to JSON string."""
    if val is None:
        return None
    if isinstance(val, list):
        return json.dumps([str(v) for v in val], ensure_ascii=False)
    return json.dumps([str(val)], ensure_ascii=False)


def _text(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, list):
        # Rich text: list of {text: "...", type: "text"} segments
        return "".join(seg.get("text", "") for seg in val if isinstance(seg, dict))
    return str(val)


def _attachment_urls(val: Any) -> str | None:
    """Extract URL list from Feishu attachment field."""
    if not val:
        return None
    if isinstance(val, list):
        urls = [a.get("url") or a.get("tmp_url") for a in val if isinstance(a, dict)]
        urls = [u for u in urls if u]
        return json.dumps(urls, ensure_ascii=False) if urls else None
    return None


def _linked_record_ids(val: Any) -> list[str]:
    """Extract record_id list from Feishu link field."""
    if not val:
        return []
    if isinstance(val, list):
        return [r.get("record_id") for r in val if isinstance(r, dict) and r.get("record_id")]
    return []


class FeishuSyncer:
    def __init__(self, feishu, table_ids: dict, engine=None):
        """
        feishu: FeishuClient instance
        table_ids: dict with keys sku/plan/content/publish/material/tag
        engine: SQLAlchemy engine (uses make_engine() default if None)
        """
        self.feishu = feishu
        self.table_ids = table_ids
        self.engine = engine or make_engine()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sync_all(self):
        """Sync all tables sequentially. Safe to call on startup."""
        logger.info("[Sync] Starting full sync of all tables")
        self.sync_skus()
        self.sync_plans()
        self.sync_contents()
        self.sync_publish_records()
        self.sync_materials()
        self.sync_tags()
        logger.info("[Sync] All tables synced")

    def sync_skus(self):
        self._sync_table(
            cursor_key="feishu_sku",
            table_id=self.table_ids["sku"],
            mapper=self._map_sku,
            model_cls=Sku,
        )

    def sync_plans(self):
        self._sync_table(
            cursor_key="feishu_plan",
            table_id=self.table_ids["plan"],
            mapper=self._map_plan,
            model_cls=Plan,
        )

    def sync_contents(self):
        self._sync_table(
            cursor_key="feishu_content",
            table_id=self.table_ids["content"],
            mapper=self._map_content,
            model_cls=Content,
        )

    def sync_publish_records(self):
        self._sync_table(
            cursor_key="feishu_publish",
            table_id=self.table_ids["publish"],
            mapper=self._map_publish_record,
            model_cls=PublishRecord,
        )

    def sync_materials(self):
        self._sync_table(
            cursor_key="feishu_material",
            table_id=self.table_ids["material"],
            mapper=self._map_material,
            model_cls=Material,
        )

    def sync_tags(self):
        self._sync_table(
            cursor_key="feishu_tag",
            table_id=self.table_ids["tag"],
            mapper=self._map_tag,
            model_cls=Tag,
        )

    # ------------------------------------------------------------------
    # Core sync engine
    # ------------------------------------------------------------------

    def _sync_table(self, cursor_key: str, table_id: str, mapper, model_cls):
        with Session(self.engine) as session:
            cursor = session.get(SyncCursor, cursor_key)
            last_sync = cursor.last_sync_at if cursor else None

        logger.info("[Sync] %s — last_sync=%s", cursor_key, last_sync)

        # Full table scan: Feishu bitable's formula filter does not support system
        # modification-time fields reliably, so we always fetch all records and let
        # the upsert logic skip unchanged ones.
        try:
            records = self.feishu.list_records(table_id=table_id)
        except Exception as e:
            logger.error("[Sync] %s fetch failed: %s", cursor_key, e)
            return

        if not records:
            logger.info("[Sync] %s — no new records", cursor_key)
            self._update_cursor(cursor_key, last_sync or datetime.utcnow(), len(records))
            return

        upserted = 0
        with Session(self.engine) as session:
            for raw in records:
                try:
                    with session.begin_nested():
                        obj = mapper(raw, session)
                        if obj is None:
                            continue
                        existing = session.execute(
                            select(model_cls).where(
                                model_cls.feishu_record_id == raw["record_id"]
                            )
                        ).scalar_one_or_none()

                        if existing:
                            # Update non-status fields only
                            for k, v in vars(obj).items():
                                if k.startswith("_"):
                                    continue
                                if k in _STATUS_FIELDS:
                                    continue  # never overwrite local status
                                setattr(existing, k, v)
                            existing.synced_at = datetime.utcnow()
                        else:
                            obj.synced_at = datetime.utcnow()
                            session.add(obj)

                        session.flush()
                        upserted += 1
                except IntegrityError as e:
                    logger.warning(
                        "[Sync] %s record %s skipped due to integrity conflict: %s",
                        cursor_key, raw.get("record_id"), e,
                    )
                except Exception as e:
                    logger.warning("[Sync] %s record %s mapping error: %s",
                                   cursor_key, raw.get("record_id"), e)

            session.commit()

        self._update_cursor(cursor_key, datetime.utcnow(), upserted)
        logger.info("[Sync] %s — upserted %d records", cursor_key, upserted)

    def _update_cursor(self, key: str, sync_at: datetime, count: int):
        with Session(self.engine) as session:
            cursor = session.get(SyncCursor, key)
            if cursor:
                cursor.last_sync_at = sync_at
                cursor.sync_count = (cursor.sync_count or 0) + count
                cursor.updated_at = datetime.utcnow()
            else:
                session.add(SyncCursor(
                    table_name=key,
                    last_sync_at=sync_at,
                    sync_count=count,
                ))
            session.commit()

    # ------------------------------------------------------------------
    # Mappers: Feishu raw record → ORM object (unsaved)
    # ------------------------------------------------------------------

    def _map_sku(self, raw: dict, session: Session) -> Sku | None:
        f = raw["fields"]
        sku_code = (_text(f.get("SKU编号")) or "").strip()
        if not sku_code:
            return None
        return Sku(
            feishu_record_id    = raw["record_id"],
            sku_code            = sku_code,
            sku_name            = _text(f.get("SKU名称")) or "",
            spu_code            = _text(f.get("SPU编号")),
            product_alias       = _text(f.get("产品简称")),
            display_name        = _text(f.get("商品名称")),
            category            = _text(f.get("品类")),
            model               = _text(f.get("适配机型")),
            material            = _list_field(f.get("材质")),
            color               = _list_field(f.get("颜色")),
            style               = _list_field(f.get("风格")),
            target_audience     = _list_field(f.get("目标人群")),
            selling_point_1     = _text(f.get("卖点1")),
            selling_point_2     = _text(f.get("卖点2")),
            selling_point_3     = _text(f.get("卖点3")),
            price_range         = f.get("价格区间"),
            platforms           = _list_field(f.get("销售平台")),
            listing_status      = _text(f.get("上架状态")) or "待上架",
            white_bg_urls       = _attachment_urls(f.get("白底图")),
        )

    def _map_plan(self, raw: dict, session: Session) -> Plan | None:
        f = raw["fields"]
        plan_code = _text(f.get("规划编号"))
        if not plan_code:
            return None

        # Resolve sku_id from linked SKU record
        sku_id = None
        linked_sku_ids = _linked_record_ids(f.get("关联SKU"))
        if linked_sku_ids:
            sku = session.execute(
                select(Sku).where(Sku.feishu_record_id == linked_sku_ids[0])
            ).scalar_one_or_none()
            if sku:
                sku_id = sku.id

        return Plan(
            feishu_record_id    = raw["record_id"],
            plan_code           = plan_code,
            sku_id              = sku_id,
            task_name           = _text(f.get("任务名称")),
            task_type           = _text(f.get("任务类型")) or "",
            content_types       = _list_field(f.get("内容类型")),
            target_platforms    = _list_field(f.get("目标平台")),
            img_count           = f.get("生成图文篇数") or 3,
            img_per_post        = f.get("每篇图片数") or 4,
            video_count         = f.get("生成视频篇数") or 0,
            video_min_sec       = f.get("视频最短时长(秒)"),
            video_max_sec       = f.get("视频最长时长(秒)"),
            tag_inject_n        = f.get("注入标签数(N)") or 5,
            text_model          = _text(f.get("文案模型")),
            image_model         = _text(f.get("图片模型")),
            video_model         = _text(f.get("视频模型")),
            notes               = _text(f.get("备注")),
            # exec_status intentionally not mapped — local is authoritative
        )

    def _map_content(self, raw: dict, session: Session) -> Content | None:
        f = raw["fields"]
        content_code = _text(f.get("内容编号"))
        if not content_code:
            return None

        # Resolve plan_id
        plan_id = None
        linked_plan_ids = _linked_record_ids(f.get("关联规划"))
        if linked_plan_ids:
            plan = session.execute(
                select(Plan).where(Plan.feishu_record_id == linked_plan_ids[0])
            ).scalar_one_or_none()
            if plan:
                plan_id = plan.id

        # Resolve sku_id
        sku_id = None
        linked_sku_ids = _linked_record_ids(f.get("关联SKU"))
        if linked_sku_ids:
            sku = session.execute(
                select(Sku).where(Sku.feishu_record_id == linked_sku_ids[0])
            ).scalar_one_or_none()
            if sku:
                sku_id = sku.id

        return Content(
            feishu_record_id    = raw["record_id"],
            content_code        = content_code,
            plan_id             = plan_id,
            sku_id              = sku_id,
            task_type           = _text(f.get("任务类型")),
            target_platform     = _text(f.get("目标平台")),
            content_type        = _text(f.get("内容类型")),
            content_form        = _text(f.get("内容形态")),
            title               = _text(f.get("标题")),
            body                = _text(f.get("正文")),
            tags                = _text(f.get("标签")),
            local_dir           = _text(f.get("素材文件夹路径")),
            generated_at        = _ms_to_dt(f.get("生成时间")),
            # gen_status / review_status not mapped — local is authoritative
        )

    def _map_publish_record(self, raw: dict, session: Session) -> PublishRecord | None:
        f = raw["fields"]
        pub_code = _text(f.get("发布编号"))
        if not pub_code:
            return None

        content_id = None
        linked_content_ids = _linked_record_ids(f.get("关联内容"))
        if linked_content_ids:
            content = session.execute(
                select(Content).where(Content.feishu_record_id == linked_content_ids[0])
            ).scalar_one_or_none()
            if content:
                content_id = content.id

        return PublishRecord(
            feishu_record_id    = raw["record_id"],
            pub_code            = pub_code,
            content_id          = content_id,
            publish_method      = _text(f.get("发布方式")) or "待定",
            scheduled_at        = _ms_to_dt(f.get("计划发布时间")),
            post_url            = _text(f.get("发布链接")),
            notes               = _text(f.get("备注")),
            # pub_status not mapped — local is authoritative
        )

    def _map_material(self, raw: dict, session: Session) -> Material | None:
        f = raw["fields"]
        return Material(
            feishu_record_id    = raw["record_id"],
            material_code       = _text(f.get("素材编号")),
            source_url          = _text(f.get("素材链接")),
            original_title      = _text(f.get("原始标题")),
            original_body       = _text(f.get("原始正文")),
            like_count          = f.get("点赞数"),
            collect_count       = f.get("收藏数"),
            source_platform     = _text(f.get("来源平台")),
            content_form        = _text(f.get("内容形态")),
            category            = _text(f.get("品类")),
            content_type        = _text(f.get("内容类型")),
            title_formula       = _text(f.get("标题公式")),
            body_structure      = _text(f.get("正文结构")),
            emotion_triggers    = _list_field(f.get("情绪触发点")),
            selling_style       = _text(f.get("卖点提炼方式")),
            composition_style   = _text(f.get("构图风格")),
            color_tone          = _text(f.get("色调氛围")),
            scene_props         = _text(f.get("场景道具")),
            tag_strategy        = _text(f.get("标签组合策略")),
            applied_to_engine   = _text(f.get("已应用至引擎")) == "是",
            # analysis_status not mapped — local is authoritative
        )

    def _map_tag(self, raw: dict, session: Session) -> Tag | None:
        f = raw["fields"]
        tag_name = _text(f.get("标签名称"))
        if not tag_name:
            return None
        return Tag(
            feishu_record_id    = raw["record_id"],
            tag_code            = _text(f.get("标签编号")),
            tag_name            = tag_name,
            platforms           = _list_field(f.get("平台")),
            industry            = _text(f.get("行业")),
            category            = _text(f.get("品类")),
            topic_heat          = f.get("话题热度"),
            weight_score        = f.get("权重评分"),
            use_count           = f.get("使用频次") or 0,
            enabled             = _text(f.get("是否启用")) != "停用",
            last_updated_at     = _ms_to_dt(f.get("最后更新时间")),
        )


# Fields that are local-authoritative — never overwritten from Feishu
_STATUS_FIELDS = {
    "exec_status", "confirmed_exec", "started_at", "finished_at",
    "gen_status", "migrate_status", "review_status",
    "pub_status", "published_at",
    "analysis_status",
    "error_msg",
}
