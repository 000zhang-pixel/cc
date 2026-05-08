"""
FeishuSyncer — pulls records from Feishu Bitable into local SQLite.

Strategy:
  - Default mode is hybrid: startup always does a full scan, periodic runs use
    formula-based incremental sync when a cursor exists, and a scheduled full
    rescan is performed every FEISHU_SYNC_FULL_SCAN_EVERY cycles as a safety net.
  - FEISHU_SYNC_MODE can still be forced to full_scan or formula_modified_time
    for debugging/experiments.
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
import os
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


def _plan_confirmed(val: Any) -> bool:
    return _text(val) in {"是", "立即执行"}


def _plan_status(val: Any) -> str | None:
    status = _text(val)
    return status if status in {"待执行", "执行中", "完成", "失败"} else None


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
    _NATURAL_KEY_FIELDS = {
        Sku: ("sku_code",),
        Plan: ("plan_code",),
        Content: ("content_code",),
        PublishRecord: ("pub_code",),
        Material: ("material_code",),
        Tag: ("tag_code", "tag_name"),
    }

    def __init__(self, feishu, table_ids: dict, engine=None):
        """
        feishu: FeishuClient instance
        table_ids: dict with keys sku/plan/content/publish/material/tag
        engine: SQLAlchemy engine (uses make_engine() default if None)
        """
        self.feishu = feishu
        self.table_ids = table_ids
        self.engine = engine or make_engine()
        self.sync_mode = (os.environ.get("FEISHU_SYNC_MODE", "hybrid") or "hybrid").strip().lower()
        if self.sync_mode not in {"full_scan", "formula_modified_time", "hybrid"}:
            raise RuntimeError(
                f"Unsupported FEISHU_SYNC_MODE={self.sync_mode!r}; expected 'full_scan', 'formula_modified_time', or 'hybrid'"
            )
        self._hybrid_full_scan_every = max(
            0,
            int((os.environ.get("FEISHU_SYNC_FULL_SCAN_EVERY", "12") or "12").strip() or "12"),
        )
        self._periodic_run_count = 0

    def _identity_key(self, model_cls, obj):
        for field_name in self._NATURAL_KEY_FIELDS.get(model_cls, ()): 
            value = getattr(obj, field_name, None)
            if value:
                return (field_name, value)
        record_id = getattr(obj, "feishu_record_id", None)
        if record_id:
            return ("feishu_record_id", record_id)
        return None

    def _find_existing(self, session: Session, model_cls, obj):
        record_id = getattr(obj, "feishu_record_id", None)
        if record_id:
            existing = session.execute(
                select(model_cls).where(model_cls.feishu_record_id == record_id)
            ).scalar_one_or_none()
            if existing:
                return existing

        identity = self._identity_key(model_cls, obj)
        if not identity or identity[0] == "feishu_record_id":
            return None

        field_name, value = identity
        return session.execute(
            select(model_cls).where(getattr(model_cls, field_name) == value)
        ).scalar_one_or_none()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def _resolve_run_mode(self, *, reason: str, force_mode: str | None) -> str:
        if force_mode:
            return force_mode
        if reason == "startup":
            return "full_scan"
        if self.sync_mode != "hybrid":
            return self.sync_mode
        if self._hybrid_full_scan_every and self._periodic_run_count % self._hybrid_full_scan_every == 0:
            return "full_scan"
        return "formula_modified_time"

    def _run_label(self, *, reason: str, run_mode: str) -> str:
        if reason == "startup":
            return "startup full sync"
        if reason == "periodic" and self.sync_mode == "hybrid":
            if run_mode == "full_scan":
                return "periodic hybrid sync (scheduled full rescan)"
            return "periodic hybrid sync"
        if reason == "periodic":
            return f"periodic {run_mode} sync"
        if reason == "manual":
            return f"manual {run_mode} sync"
        return f"{reason} {run_mode} sync"

    def sync_all(self, *, reason: str = "manual", force_mode: str | None = None):
        """Sync all tables sequentially. Safe to call on startup or periodically."""
        if reason == "periodic":
            self._periodic_run_count += 1
        run_mode = self._resolve_run_mode(reason=reason, force_mode=force_mode)
        logger.info("[Sync] Starting %s of all tables", self._run_label(reason=reason, run_mode=run_mode))
        self.sync_skus(run_mode=run_mode, reason=reason)
        self.sync_plans(run_mode=run_mode, reason=reason)
        self.sync_contents(run_mode=run_mode, reason=reason)
        self.sync_publish_records(run_mode=run_mode, reason=reason)
        self.sync_materials(run_mode=run_mode, reason=reason)
        self.sync_tags(run_mode=run_mode, reason=reason)
        logger.info("[Sync] All tables synced (%s)", self._run_label(reason=reason, run_mode=run_mode))

    def sync_skus(self, *, run_mode: str | None = None, reason: str = "manual"):
        self._sync_table(
            cursor_key="feishu_sku",
            table_id=self.table_ids["sku"],
            mapper=self._map_sku,
            model_cls=Sku,
            run_mode=run_mode,
            reason=reason,
        )

    def sync_plans(self, *, run_mode: str | None = None, reason: str = "manual"):
        self._sync_table(
            cursor_key="feishu_plan",
            table_id=self.table_ids["plan"],
            mapper=self._map_plan,
            model_cls=Plan,
            run_mode=run_mode,
            reason=reason,
        )

    def sync_contents(self, *, run_mode: str | None = None, reason: str = "manual"):
        self._sync_table(
            cursor_key="feishu_content",
            table_id=self.table_ids["content"],
            mapper=self._map_content,
            model_cls=Content,
            run_mode=run_mode,
            reason=reason,
        )

    def sync_publish_records(self, *, run_mode: str | None = None, reason: str = "manual"):
        self._sync_table(
            cursor_key="feishu_publish",
            table_id=self.table_ids["publish"],
            mapper=self._map_publish_record,
            model_cls=PublishRecord,
            run_mode=run_mode,
            reason=reason,
        )

    def sync_materials(self, *, run_mode: str | None = None, reason: str = "manual"):
        self._sync_table(
            cursor_key="feishu_material",
            table_id=self.table_ids["material"],
            mapper=self._map_material,
            model_cls=Material,
            run_mode=run_mode,
            reason=reason,
        )

    def sync_tags(self, *, run_mode: str | None = None, reason: str = "manual"):
        self._sync_table(
            cursor_key="feishu_tag",
            table_id=self.table_ids["tag"],
            mapper=self._map_tag,
            model_cls=Tag,
            run_mode=run_mode,
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Core sync engine
    # ------------------------------------------------------------------

    def _sync_table(self, cursor_key: str, table_id: str, mapper, model_cls, *, run_mode: str | None = None, reason: str = "manual"):
        with Session(self.engine) as session:
            cursor = session.get(SyncCursor, cursor_key)
            last_sync = cursor.last_sync_at if cursor else None

        effective_mode = run_mode or self._resolve_run_mode(reason=reason, force_mode=None)
        if effective_mode == "formula_modified_time" and not last_sync:
            effective_mode = "full_scan"

        logger.info(
            "[Sync] %s — last_sync=%s configured_mode=%s effective_mode=%s reason=%s",
            cursor_key,
            last_sync,
            self.sync_mode,
            effective_mode,
            reason,
        )

        filter_str = None
        if effective_mode == "formula_modified_time" and last_sync:
            ts_ms = int(last_sync.timestamp() * 1000)
            filter_str = f'CurrentValue.[修改时间]>{ts_ms}'

        try:
            records = self.feishu.list_records(table_id=table_id, filter_str=filter_str)
        except Exception as e:
            logger.error("[Sync] %s fetch failed: %s", cursor_key, e)
            return

        if not records:
            logger.info("[Sync] %s — no new records", cursor_key)
            self._update_cursor(cursor_key, last_sync or datetime.utcnow(), len(records))
            return

        upserted = 0
        seen_identity_keys: set[tuple[str, str]] = set()
        with Session(self.engine) as session:
            for raw in records:
                try:
                    with session.begin_nested():
                        obj = mapper(raw, session)
                        if obj is None:
                            continue

                        identity_key = self._identity_key(model_cls, obj)
                        if identity_key and identity_key in seen_identity_keys:
                            logger.info(
                                "[Sync] %s skipped duplicate remote record for %s=%s (record_id=%s)",
                                cursor_key,
                                identity_key[0],
                                identity_key[1],
                                raw.get("record_id"),
                            )
                            continue
                        if identity_key:
                            seen_identity_keys.add(identity_key)

                        existing = self._find_existing(session, model_cls, obj)

                        if existing:
                            previous_record_id = getattr(existing, "feishu_record_id", None)
                            record_id_changed = previous_record_id != raw["record_id"]
                            # Update non-status fields only
                            for k, v in vars(obj).items():
                                if k.startswith("_"):
                                    continue
                                if k in _STATUS_FIELDS:
                                    continue  # never overwrite local status
                                setattr(existing, k, v)
                            self._reconcile_remote_plan_state(existing, raw)
                            existing.synced_at = datetime.utcnow()
                            if record_id_changed:
                                logger.info(
                                    "[Sync] %s remapped %s natural key to new feishu_record_id: %s -> %s",
                                    cursor_key,
                                    model_cls.__name__,
                                    previous_record_id,
                                    raw["record_id"],
                                )
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

    def _reconcile_remote_plan_state(self, existing: Any, raw: dict) -> None:
        if not isinstance(existing, Plan):
            return
        fields = raw.get("fields") or {}
        remote_status = _plan_status(fields.get("执行状态"))
        if not remote_status:
            return

        existing.confirmed_exec = _plan_confirmed(fields.get("确认执行"))

        if remote_status == "完成":
            existing.exec_status = "完成"
            existing.finished_at = _ms_to_dt(fields.get("任务完成时间")) or existing.finished_at or datetime.utcnow()
            remote_log = _text(fields.get("任务日志"))
            if remote_log:
                existing.error_msg = remote_log
            return

        if remote_status == "失败":
            existing.exec_status = "失败"
            existing.finished_at = _ms_to_dt(fields.get("任务完成时间")) or existing.finished_at or datetime.utcnow()
            remote_log = _text(fields.get("任务日志"))
            if remote_log:
                existing.error_msg = remote_log
            return

        if remote_status == "执行中" and existing.exec_status == "待执行":
            existing.exec_status = "执行中"

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
