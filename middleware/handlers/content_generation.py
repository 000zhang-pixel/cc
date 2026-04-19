"""
ContentGenerationHandler — processes a 表2 内容规划表 record.

Full pipeline:
  1. Validate SKU completeness & 上架状态
  2. Read config fields from 表2
  3. Fetch TOP N tags from 表7 by platform + category
  4. build_groups()
  5. assign_scenes()
  6. lookup_persona() per group          ← v2 新增
  7. build_creative_brief() per group    ← v2 新增
  8. For each img/vid group: create 表3 Prompt records
  9. fill_prompts_from_brief()           ← v2 升级
  10. Call AI APIs to generate content
  11. Write results to 表4 内容生成表
  12. Update 表2 execution status
"""
from __future__ import annotations
import json
import logging
import random
from datetime import datetime

import db
from adapters.feishu import FeishuClient
from adapters.ai_models import (
    TextModelAdapter,
    ImageModelAdapter,
    VideoModelAdapter,
    build_text_adapter,
    build_image_adapter,
    build_video_adapter,
)
from core.local_storage import LocalStorage
from core.task import Task

logger = logging.getLogger(__name__)

# Maps Feishu dropdown display names → model_params.yaml provider keys
_MODEL_NAME_MAP = {
    "GPT-5.4":          "gpt-5.4",
    "GPT-4.1":          "gpt-4.1",
    "Kimi K2.5":        "kimi-k2.5",
    "DeepSeek":         "deepseek",
    "Nanobanana 2":     "nanobanana-2",
    "volcengine-seedream": "volcengine-seedream",
    "volcengine-seedance": "volcengine-seedance",
    "Veo 3":            "veo-3",
}


def _normalize_model(name: str) -> str:
    return _MODEL_NAME_MAP.get(name, name)


def _shotplan_form_aliases(content_form: str) -> list[str]:
    """Return compatible ShotPlan form aliases during enum migration.

    Runtime now prefers `图片`, but online Feishu data still contains legacy values
    like `图片生成` and `组图`. We accept both directions during transition.
    """
    aliases = {
        "图片": ["图片", "图片生成", "组图"],
        "图片生成": ["图片生成", "图片", "组图"],
        "组图": ["组图", "图片", "图片生成"],
        "视频": ["视频", "视频画面"],
        "视频画面": ["视频画面", "视频"],
    }
    return aliases.get(content_form, [content_form])


# Content types pool (12 types)
CONTENT_TYPES = [
    "种草推荐", "好物分享", "深度测评", "对比测评",
    "穿搭搭配", "场景展示", "日常vlog",
    "开箱", "买家秀/晒单", "节日/活动限定", "新品发布",
    "选购攻略/使用教程",
]


class ContentGenerationHandler:
    def __init__(
        self,
        feishu: FeishuClient,
        tables: dict,        # name → table_id
        model_params: dict,  # from model_params.yaml
        local_storage: LocalStorage | None = None,
    ):
        self._feishu = feishu
        self._tables = tables
        self._model_params = model_params
        self._storage = local_storage

    def __call__(self, task: Task):
        record_id = task.record_id
        table_plan = self._tables["plan"]

        # Mark plan as started in local DB (best-effort — plan may not yet be synced)
        plan_code = task.extra.get("plan_code") if task.extra else None
        if not plan_code:
            try:
                pr = self._feishu.get_record(table_plan, record_id)
                plan_code = self._feishu.get_text(pr, "规划编号").strip() or None
            except Exception:
                pass
        if plan_code:
            db.mark_plan_started(plan_code)

        try:
            self._run(record_id)
        except Exception as exc:
            logger.exception("ContentGeneration failed for record %s", record_id)
            self._feishu.update_record(table_plan, record_id, {
                "执行状态": "失败",
                "任务日志": str(exc),
            })
            if plan_code:
                db.mark_plan_failed(plan_code, str(exc)[:500])
                db.log_exc("plan", 0, f"ContentGeneration failed: {exc}")

    # ------------------------------------------------------------------
    def _run(self, record_id: str):
        table_plan = self._tables["plan"]
        f = self._feishu

        # --- 1. Read plan record ---
        plan = f.get_record(table_plan, record_id)
        plan_fields = plan["fields"]

        # --- 2. Validate & fetch SKU ---
        sku_record = self._validate_and_get_sku(plan_fields, record_id)
        sku_fields = sku_record["fields"]

        # --- 3. Parse plan config ---
        cfg = self._parse_plan_config(plan_fields)

        # --- 4. Fetch TOP N tags ---
        tags = self._fetch_tags(cfg["platforms"], sku_fields, cfg["tag_count"])

        # --- 5. Build group list ---
        groups = self._build_groups(cfg)

        plan_code = self._make_plan_id(record_id)

        # --- 5a. Save initial plan.json (creates directory) ---
        if self._storage:
            try:
                self._storage.save_plan(plan_code, {
                    "feishu_plan_record_id": record_id,
                    "sku_code": f.get_text(sku_record, "SKU编号"),
                    "sku_name": f.get_text(sku_record, "SKU名称"),
                    "platforms": cfg["platforms"],
                    "task_type": cfg["task_type"],
                    "text_model": cfg["text_model_name"],
                    "image_model": cfg["image_model_name"],
                    "video_model": cfg["video_model_name"],
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                })
            except Exception:
                logger.warning("Failed to save plan.json, continuing", exc_info=True)

        # --- 5b. Assign scenes to groups (merges into plan.json) ---
        scene_assignments = self._assign_scenes(groups, sku_fields, plan_code, cfg.get("scene_variety", "中"))

        # --- 5c. Lookup persona per group & build Creative Briefs ---
        # Inject category into cfg so Brief builder can access it without extra lookup
        cfg["_category"] = self._feishu.get_option({"fields": sku_fields}, "品类")
        persona_assignments = self._assign_personas(groups, sku_fields, cfg, scene_assignments)
        briefs = self._build_creative_briefs(groups, cfg, scene_assignments, persona_assignments)

        # Persist briefs to plan.json for observability
        if self._storage:
            try:
                self._storage.update_plan(plan_code, {"briefs": briefs})
            except Exception:
                logger.warning("Failed to write briefs to plan.json", exc_info=True)

        # --- 6. Validate providers before creating downstream records ---
        text_adapter = build_text_adapter(cfg["text_model_name"], self._model_params)
        has_img_group = any(group["type"] == "img" for group in groups)
        has_vid_group = any(group["type"] == "vid" for group in groups)
        if cfg["task_type"] == "AI全创作" and has_img_group:
            build_image_adapter(self._model_params, cfg["image_model_name"])
        if has_vid_group:
            build_video_adapter(self._model_params, cfg["video_model_name"])

        # --- 7. Create Prompt records in 表3 ---
        prompt_records = self._create_prompt_records(record_id, groups, plan_fields, sku_fields, cfg)

        # --- 8. Generate Prompts via Prompt engine ---
        self._fill_prompts(prompt_records, sku_fields, cfg, tags, text_adapter, scene_assignments, briefs, persona_assignments)

        # P0-2: Re-persist briefs now that _fill_prompts has resolved strategy_id + shotplan_id
        if self._storage:
            try:
                self._storage.update_plan(plan_code, {"briefs": briefs})
            except Exception:
                logger.warning("Failed to re-write briefs to plan.json after _fill_prompts", exc_info=True)

        # --- 8. Mark all prompts 已确认 ---
        for pr in prompt_records:
            f.update_record(self._tables["prompt"], pr["prompt_record_id"], {"状态": "已确认"})

        # --- 9. Generate content (call AI APIs) ---
        # Inject briefs/personas into cfg for _generate_content observability writes
        cfg["_briefs"] = briefs
        cfg["_persona_assignments"] = persona_assignments
        content_record_ids = self._generate_content(groups, prompt_records, sku_fields, cfg, record_id, tags)

        # --- 10. Update plan status ---
        completion_time = int(datetime.now().timestamp() * 1000)
        f.update_record(table_plan, record_id, {
            "执行状态": "完成",
            "任务完成时间": completion_time,
            "任务日志": (
                f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"共生成 {len(content_record_ids)} 条内容记录"
            ),
        })
        db.mark_plan_done(plan_code)
        db.log_task("plan", 0, "INFO",
                    f"ContentGeneration complete: {len(content_record_ids)} content records",
                    entity_code=plan_code)
        logger.info("ContentGeneration complete for plan %s (%d records)", record_id, len(content_record_ids))

    # ------------------------------------------------------------------
    # SKU validation
    # ------------------------------------------------------------------

    def _validate_and_get_sku(self, plan_fields: dict, plan_record_id: str) -> dict:
        f = self._feishu
        table_sku = self._tables["sku"]
        table_plan = self._tables["plan"]

        sku_link = plan_fields.get("关联SKU")
        if not sku_link:
            msg = "SKU数据不完整或未上架，请先完善SKU信息（未关联SKU）"
            f.update_record(table_plan, plan_record_id, {
                "执行状态": "失败",
                "任务日志": msg,
            })
            raise ValueError(msg)

        sku_ids = f.get_link_ids({"fields": {"关联SKU": sku_link}}, "关联SKU")
        if not sku_ids:
            msg = "关联SKU为空，无法执行"
            f.update_record(table_plan, plan_record_id, {
                "执行状态": "失败",
                "任务日志": msg,
            })
            raise ValueError(msg)

        sku_record = f.get_record(table_sku, sku_ids[0])
        sf = sku_record["fields"]

        # Required fields check
        required_text = ["SKU编号", "SKU名称", "产品简称", "品类", "卖点1"]
        missing = [field for field in required_text if not f.get_text(sku_record, field).strip()]

        # 白底图 must have at least one attachment
        attachments = sf.get("白底图") or []
        if not attachments:
            missing.append("白底图")

        if missing:
            msg = f"SKU数据不完整或未上架，请先完善SKU信息（缺少：{', '.join(missing)}）"
            f.update_record(table_plan, plan_record_id, {
                "执行状态": "失败",
                "任务日志": msg,
            })
            raise ValueError(msg)

        # 上架状态 must be 已上架
        status = f.get_option(sku_record, "上架状态")
        if status != "已上架":
            msg = f"SKU数据不完整或未上架，请先完善SKU信息（上架状态={status!r}）"
            f.update_record(table_plan, plan_record_id, {
                "执行状态": "失败",
                "任务日志": msg,
            })
            raise ValueError(msg)

        return sku_record

    # ------------------------------------------------------------------
    # Parse plan config fields
    # ------------------------------------------------------------------

    def _parse_plan_config(self, plan_fields: dict) -> dict:
        f = self._feishu
        dummy = {"fields": plan_fields}
        return {
            "task_type": f.get_option(dummy, "任务类型"),
            "content_types": f.get_options(dummy, "内容类型"),
            "platforms": f.get_options(dummy, "目标平台"),
            "img_count": int(f.get_number(dummy, "生成图文篇数", 3)),
            "img_per_piece": int(f.get_number(dummy, "每篇图片数", 4)),
            "vid_count": int(f.get_number(dummy, "生成视频篇数", 1)),
            "vid_min_sec": int(f.get_number(dummy, "视频最短时长(秒)", 5)),
            "vid_max_sec": int(f.get_number(dummy, "视频最长时长(秒)", 12)),
            "tag_count": int(f.get_number(dummy, "注入标签数(N)", 5)),
            "text_model_name":  _normalize_model(f.get_option(dummy, "文案模型",  "kimi-k2.5")),
            "image_model_name": _normalize_model(f.get_option(dummy, "图片模型",  "volcengine-seedream")),
            "video_model_name": _normalize_model(f.get_option(dummy, "视频模型",  "volcengine-seedance")),
            # v2 新增可选控制字段 — 飞书表中若未建立这些字段会返回空值，均有安全默认值
            "diff_strength":   f.get_option(dummy, "差异化强度")  or "中",   # 低/中/高
            "persona_mode":    f.get_option(dummy, "人设模式")    or "自动",  # 自动/固定主人设/多人设轮换
            "consistency_strength": f.get_option(dummy, "一致性强度") or "强",   # 中/强
            "scene_variety":   f.get_option(dummy, "场景丰富度")  or "中",   # 低/中/高
        }

    # ------------------------------------------------------------------
    # Fetch TOP N tags from 表7
    # ------------------------------------------------------------------

    def _fetch_tags(self, platforms: list[str], sku_fields: dict, n: int) -> list[str]:
        f = self._feishu
        table_tag = self._tables["tag"]
        category = f.get_option({"fields": sku_fields}, "品类")

        # Fetch all records without server-side filter (Feishu option-field filters are unreliable)
        records = f.list_records(table_tag)
        matched = []
        for rec in records:
            # Python-side filtering
            if f.get_option(rec, "是否启用") != "启用":
                continue
            rec_platforms = f.get_options(rec, "平台")
            rec_category  = f.get_option(rec, "品类")
            platform_match = any(p in rec_platforms for p in platforms)
            category_match = (rec_category == category or rec_category == "通用")
            if platform_match and category_match:
                weight = f.get_number(rec, "权重评分", 0)
                name   = f.get_text(rec, "标签名称")
                matched.append((weight, name, rec["record_id"]))

        matched.sort(key=lambda x: x[0], reverse=True)

        # 分层随机取标签：
        #   60%（四舍五入）从排名前20随机取
        #   40%（四舍五入）从排名第11名之后随机取
        n_top  = round(n * 0.6)          # 60% 来自前20
        n_tail = n - n_top               # 40% 来自第11名之后
        pool_top  = matched[:20]         # 前20
        pool_tail = matched[10:]         # 第11名之后（index 10起）

        selected_top  = random.sample(pool_top,  min(n_top,  len(pool_top)))
        selected_tail = random.sample(pool_tail, min(n_tail, len(pool_tail)))

        # 合并去重（pool有重叠区间11-20，防止同一条被选两次）
        seen = set()
        chosen = []
        for item in selected_top + selected_tail:
            if item[2] not in seen:
                seen.add(item[2])
                chosen.append(item)

        logger.info("[Tags] platform=%s category=%s matched=%d top_pool=%d tail_pool=%d chosen=%d",
                    platforms, category, len(matched), len(pool_top), len(pool_tail), len(chosen))

        # Increment usage count (best-effort)
        for _, _, rid in chosen:
            try:
                tag_rec = f.get_record(table_tag, rid)
                current = int(f.get_number(tag_rec, "使用频次", 0))
                f.update_record(table_tag, rid, {"使用频次": current + 1})
            except Exception:
                pass

        return [name for _, name, _ in chosen]

    # ------------------------------------------------------------------
    # Build group list
    # ------------------------------------------------------------------

    def _build_groups(self, cfg: dict) -> list[dict]:
        groups = []
        content_types = list(cfg["content_types"] or CONTENT_TYPES)
        total = cfg["img_count"] + cfg["vid_count"]

        # Shuffle once, then cycle round-robin to avoid duplicates across posts
        shuffled = content_types[:]
        random.shuffle(shuffled)
        pool = [shuffled[i % len(shuffled)] for i in range(total)]
        idx = 0

        for i in range(1, cfg["img_count"] + 1):
            groups.append({
                "group_id": f"img{i:02d}",
                "type": "img",
                "content_type": pool[idx],
                "img_per_piece": cfg["img_per_piece"],
            })
            idx += 1
        for i in range(1, cfg["vid_count"] + 1):
            groups.append({
                "group_id": f"vid{i:02d}",
                "type": "vid",
                "content_type": pool[idx],
                "vid_min_sec": cfg["vid_min_sec"],
                "vid_max_sec": cfg["vid_max_sec"],
            })
            idx += 1
        return groups

    # ------------------------------------------------------------------
    # Create 表3 Prompt records (stub data, filled by engine next step)
    # ------------------------------------------------------------------

    def _make_plan_id(self, record_id: str) -> str:
        """Derive plan code from record. If 规划编号 field was set by user, use that.
        Otherwise fall back to a generated code."""
        plan_rec = self._feishu.get_record(self._tables["plan"], record_id)
        code = self._feishu.get_text(plan_rec, "规划编号").strip()
        return code or f"PLAN_{record_id[:8]}"

    def _create_prompt_records(
        self, plan_record_id: str, groups: list[dict], plan_fields: dict, sku_fields: dict, cfg: dict
    ) -> list[dict]:
        f = self._feishu
        table_prompt = self._tables["prompt"]
        now_ms = int(datetime.now().timestamp() * 1000)
        plan_code = self._make_plan_id(plan_record_id)

        results = []
        for g in groups:
            gid = g["group_id"]
            for suffix, prompt_type in self._prompt_types_for_group(g):
                prompt_code = f"P_{plan_code}_{gid}_{suffix}"

                # Dedup guard: reuse existing prompt record if already created
                existing = f.list_records(table_prompt, filter_str=f'CurrentValue.[提示词编号] = "{prompt_code}"')
                if existing:
                    logger.warning("Prompt record %s already exists, reusing", prompt_code)
                    results.append({
                        "group": g,
                        "suffix": suffix,
                        "prompt_type": prompt_type,
                        "prompt_code": prompt_code,
                        "prompt_record_id": existing[0]["record_id"],
                    })
                    continue

                fields = {
                    "提示词编号": prompt_code,
                    "关联规划": [plan_record_id],
                    "组号": gid,
                    "Prompt类型": prompt_type,
                    "使用模型": 
                        cfg["text_model_name"] if suffix == "C" else (
                            cfg["image_model_name"] if g["type"] == "img" else cfg["video_model_name"]
                        
                    ),
                    "生成来源": "AI自动生成",
                    "版本号": 1,
                    "状态": "草稿",
                    "生成时间": now_ms,
                }
                # Add SKU link
                sku_link_val = plan_fields.get("关联SKU")
                if sku_link_val:
                    sku_ids = f.get_link_ids({"fields": {"关联SKU": sku_link_val}}, "关联SKU")
                    if sku_ids:
                        fields["关联SKU"] = sku_ids

                prompt_record_id = f.create_record(table_prompt, fields)
                results.append({
                    "group": g,
                    "suffix": suffix,
                    "prompt_type": prompt_type,
                    "prompt_code": prompt_code,
                    "prompt_record_id": prompt_record_id,
                })
        return results

    @staticmethod
    def _prompt_types_for_group(g: dict) -> list[tuple[str, str]]:
        if g["type"] == "img":
            return [("C", "图文正文"), ("I", "图片生成")]
        else:
            return [("C", "视频内容"), ("I", "视频脚本")]

    # ------------------------------------------------------------------
    # Prompt engine — table-driven lookup helpers
    # ------------------------------------------------------------------

    def _select_best(
        self,
        records: list,
        content_type: str,
        platform: str | None,
        category: str,
        ct_field: str,
        pt_field: str | None,
        cat_field: str,
    ) -> dict | None:
        """
        Generic multi-level fallback selector for Strategy / ShotPlan records.

        Scoring levels (higher = more specific):
          4 — content_type match + platform match + category match
          3 — content_type match + platform match + category=通用(empty)
          2 — content_type match + platform=通用   + category=通用(empty)
          1 — all fields empty (全通用兜底)

        Within the winning level, picks the record with the highest 优先级;
        if tied, picks randomly.
        """
        f = self._feishu

        def _score(r: dict) -> tuple[int, int]:
            ct_vals  = f.get_options(r, ct_field)  or []
            cat_vals = f.get_options(r, cat_field) or []
            pt_vals  = f.get_options(r, pt_field)  or [] if pt_field else []

            ct_match  = content_type in ct_vals  if content_type else False
            cat_match = category     in cat_vals if category     else False
            pt_match  = platform     in pt_vals  if platform     else False

            ct_empty  = not ct_vals
            cat_empty = not cat_vals
            pt_empty  = not pt_vals

            prio = int(f.get_number(r, "优先级", 0))

            if   ct_match and (pt_match or not pt_field) and cat_match: return (4, prio)
            elif ct_match and (pt_match or not pt_field) and cat_empty: return (3, prio)
            elif ct_match and pt_empty                  and cat_empty:  return (2, prio)
            elif ct_empty and pt_empty                  and cat_empty:  return (1, prio)
            return (0, 0)

        scored = [(_score(r), r) for r in records if _score(r)[0] > 0]
        if not scored:
            return None
        max_level = max(s[0] for s, _ in scored)
        max_prio  = max(s[1] for s, _ in scored if s[0] == max_level)
        top = [r for s, r in scored if s == (max_level, max_prio)]
        return random.choice(top)

    def _lookup_strategy(
        self, content_type: str, platform: str, category: str
    ) -> dict | None:
        """Fetch best-matching Strategy record from 表8. Returns None if table not configured."""
        table_id = self._tables.get("strategy", "")
        if not table_id:
            return None
        try:
            records = self._feishu.list_records(
                table_id, filter_str='CurrentValue.[是否启用]="启用"'
            )
        except Exception:
            logger.warning("_lookup_strategy: failed to list records", exc_info=True)
            return None
        result = self._select_best(
            records, content_type, platform, category,
            ct_field="适用内容类型", pt_field="适用平台", cat_field="适用品类",
        )
        logger.info(
            "_lookup_strategy: content_type=%r platform=%r category=%r enabled_count=%d result=%s",
            content_type, platform, category, len(records),
            result["record_id"] if result else None,
        )
        return result

    def _lookup_shotplan(
        self, content_form: str, content_type: str, category: str
    ) -> dict | None:
        """Fetch best-matching ShotPlan record from 表9. Returns None if table not configured."""
        table_id = self._tables.get("shotplan", "")
        if not table_id:
            return None
        try:
            records = self._feishu.list_records(
                table_id, filter_str='CurrentValue.[是否启用]="启用"'
            )
        except Exception:
            logger.warning("_lookup_shotplan: failed to list records", exc_info=True)
            return None
        form_aliases = set(_shotplan_form_aliases(content_form))
        form_matched = [
            r for r in records
            if form_aliases.intersection(self._feishu.get_options(r, "适用内容形态") or [])
        ]
        candidates = form_matched if form_matched else records
        logger.info(
            "_lookup_shotplan: content_form=%r aliases=%s matched=%d enabled=%d",
            content_form, sorted(form_aliases), len(form_matched), len(records),
        )
        return self._select_best(
            candidates, content_type, platform=None, category=category,
            ct_field="适用内容类型", pt_field=None, cat_field="适用品类",
        )

    # ------------------------------------------------------------------
    # Scene assignment
    # ------------------------------------------------------------------

    def _fetch_scenes(self, category: str) -> list[tuple[int, dict]]:
        """Return [(weight, record), ...] for all enabled scenes matching category."""
        table_id = self._tables.get("scene", "")
        if not table_id:
            return []
        try:
            records = self._feishu.list_records(
                table_id, filter_str='CurrentValue.[是否启用]="启用"'
            )
        except Exception:
            logger.warning("_fetch_scenes: failed to list records", exc_info=True)
            return []
        f = self._feishu
        matched = []
        for r in records:
            cats = f.get_options(r, "适用品类") or []
            if not cats or category in cats:   # empty = 通用
                weight = int(f.get_number(r, "权重", 0))
                matched.append((weight, r))
        return matched

    def _assign_scenes(
        self, groups: list[dict], sku_fields: dict, plan_code: str,
        scene_variety: str = "中",
    ) -> dict:
        """
        Assign one distinct Scene per group (best-effort round-robin if scenes < groups).
        scene_variety:
          低 → step=1 (current behavior, tighter spread)
          中 → step=1 (same as 低, default)
          高 → step=2 (skip-one spread to maximize scene diversity across groups)
        Writes assignments to plan.json["scene_assignments"] and returns the dict.
        Format: {group_id: {scene_id, scene_record_id, 场景基底_英文, 风格基调词, 排除描述}}
        """
        f = self._feishu
        category = f.get_option({"fields": sku_fields}, "品类")
        weighted = self._fetch_scenes(category)
        if not weighted:
            logger.info("_assign_scenes: no Scene records found, skipping")
            return {}

        # Sort by weight desc; shuffle within each weight tier for diversity
        from itertools import groupby as _groupby
        weighted.sort(key=lambda x: x[0], reverse=True)
        pool: list[dict] = []
        for _, tier_iter in _groupby(weighted, key=lambda x: x[0]):
            tier = list(tier_iter)
            random.shuffle(tier)
            pool.extend(r for _, r in tier)

        # Build ordered scene sequence according to scene_variety:
        #   低/中 → sequential round-robin (start at random offset)
        #   高    → maximize uniqueness:
        #             • if pool >= groups: each group gets a distinct scene (no repeats)
        #             • if pool < groups: re-shuffle pool each full cycle to avoid
        #               step-size collision that could make all groups hit same scene
        start = random.randrange(len(pool))
        if scene_variety == "高":
            n = len(pool)
            if n >= len(groups):
                scene_seq = [pool[(start + j) % n] for j in range(len(groups))]
            else:
                scene_seq: list = []
                while len(scene_seq) < len(groups):
                    chunk = pool[:]
                    random.shuffle(chunk)
                    scene_seq.extend(chunk)
                scene_seq = scene_seq[:len(groups)]
        else:
            scene_seq = [pool[(start + i) % len(pool)] for i in range(len(groups))]

        assignments: dict = {}
        for g, scene in zip(groups, scene_seq):
            assignments[g["group_id"]] = {
                "scene_id":        f.get_text(scene, "场景编号"),
                "scene_record_id": scene["record_id"],
                "场景基底_英文":   f.get_text(scene, "场景基底_英文"),
                "场景描述_中文":   f.get_text(scene, "场景描述_中文"),
                "风格基调词":      f.get_text(scene, "风格基调词"),
                "排除描述":        f.get_text(scene, "排除描述"),
                # Person fields
                "人物类型":        f.get_text(scene, "人物类型"),
                "性别倾向":        f.get_text(scene, "性别倾向"),
                "年龄段":          f.get_text(scene, "年龄段"),
                "外貌风格":        f.get_text(scene, "外貌风格"),
                "姿态倾向":        f.get_text(scene, "姿态倾向"),
                # Technical parameters (single-select fields)
                "时段光境":        f.get_option(scene, "时段光境"),
                "空间感":          f.get_option(scene, "空间感"),
                "光线方向":        f.get_option(scene, "光线方向"),
                "色温":            f.get_option(scene, "色温"),
                "景深感":          f.get_option(scene, "景深感"),
                "镜头感":          f.get_option(scene, "镜头感"),
                # New optional v2 fields — needed by prompt builders and persona soft-match
                "场景主题":        f.get_option(scene, "场景主题"),
                "道具建议":        f.get_text(scene, "道具建议"),
                "适合人设标签":    f.get_options(scene, "适合人设标签") or [],
            }

        if self._storage:
            try:
                self._storage.update_plan(plan_code, {"scene_assignments": assignments})
            except Exception:
                logger.warning("_assign_scenes: failed to write plan.json", exc_info=True)

        return assignments

    # ------------------------------------------------------------------
    # Persona lookup  (表12 Persona人设模板表)
    # ------------------------------------------------------------------

    def _assign_personas(
        self, groups: list[dict], sku_fields: dict, cfg: dict,
        scene_assignments: dict,
    ) -> dict:
        """
        Assign one Persona record per group.  Falls back gracefully:
          1. If 表12 is configured and has matching records → use Persona table
          2. Otherwise → derive pseudo-persona from Scene person fields (existing behavior)

        Returns {group_id: persona_dict_or_None}
        """
        f = self._feishu
        table_id = self._tables.get("persona", "")
        category = f.get_option({"fields": sku_fields}, "品类")
        persona_mode = cfg.get("persona_mode", "自动")   # 自动 / 固定主人设 / 多人设轮换

        persona_pool: list[dict] = []
        if table_id:
            try:
                records = f.list_records(table_id, filter_str='CurrentValue.[是否启用]="启用"')
                # Filter by category (empty 适用品类 = 通用)
                for r in records:
                    cats = f.get_options(r, "适用品类") or []
                    if not cats or category in cats:
                        prio = int(f.get_number(r, "优先级", 0))
                        persona_pool.append((prio, r))
                persona_pool.sort(key=lambda x: x[0], reverse=True)
                persona_pool = [r for _, r in persona_pool]
                logger.info("_assign_personas: table configured, pool_size=%d", len(persona_pool))
            except Exception:
                logger.warning("_assign_personas: failed to read Persona table", exc_info=True)
                persona_pool = []

        assignments: dict = {}

        if persona_pool:
            # Build strategy-tags cache (content_type → set[人设适配标签]) for soft-match scoring.
            # Strategy lookup is cached so each unique content_type hits the API at most once.
            _strategy_tag_cache: dict = {}
            _platform = (cfg.get("platforms") or [""])[0]
            _category = cfg.get("_category", "")

            def _get_strategy_tags(ct: str) -> set:
                if ct not in _strategy_tag_cache:
                    try:
                        strat = self._lookup_strategy(ct, _platform, _category)
                        tags = set(f.get_options(strat, "人设适配标签") or []) if strat else set()
                    except Exception:
                        tags = set()
                    _strategy_tag_cache[ct] = tags
                return _strategy_tag_cache[ct]

            # Soft-match scoring: content-type fit + scene↔persona tag overlap
            #   + persona scene fit + strategy persona-tag overlap + priority tiebreaker
            def _soft_score(prec: dict, content_type: str, scene_dict: dict) -> float:
                sc = 0.0
                # +2 if persona supports the group's content type
                ctypes = f.get_options(prec, "适用内容类型") or []
                if content_type in ctypes:
                    sc += 2.0
                # +1 per scene 适合人设标签 that overlaps with persona 气质标签
                scene_tags = set(scene_dict.get("适合人设标签") or [])
                qi_zhi     = set(f.get_options(prec, "气质标签") or [])
                sc += len(scene_tags & qi_zhi)
                # +1 if persona 适合场景标签 contains the scene's 场景主题
                scene_theme = scene_dict.get("场景主题", "")
                if scene_theme:
                    persona_scene_tags = set(f.get_options(prec, "适合场景标签") or [])
                    if scene_theme in persona_scene_tags:
                        sc += 1.0
                # +1 per strategy 人设适配标签 that overlaps with persona 气质标签
                strategy_tags = _get_strategy_tags(content_type)
                sc += len(strategy_tags & qi_zhi)
                # priority as fractional tiebreaker (max ~200, so /200 keeps it < 1.0)
                sc += int(f.get_number(prec, "优先级", 0)) / 200.0
                return sc

            def _tag_signal(prec: dict, content_type: str, scene_dict: dict) -> float:
                """Score without the priority tiebreaker — used to detect zero-signal assignments."""
                return _soft_score(prec, content_type, scene_dict) - int(f.get_number(prec, "优先级", 0)) / 200.0

            if persona_mode == "固定主人设":
                # Pick persona with best aggregate fit across all groups
                best = max(persona_pool, key=lambda r: sum(
                    _soft_score(r, g.get("content_type", ""), scene_assignments.get(g["group_id"], {}))
                    for g in groups
                ))
                # Warn if best persona has no tag signal across any group
                _best_signal = max(
                    _tag_signal(best, g.get("content_type", ""), scene_assignments.get(g["group_id"], {}))
                    for g in groups
                )
                if _best_signal < 0.001:
                    logger.warning(
                        "_assign_personas [固定主人设]: zero tag signal — selected %s by priority only; "
                        "consider adding 适合人设标签/人设适配标签 config",
                        f.get_text(best, "人设编号"),
                    )
                for g in groups:
                    assignments[g["group_id"]] = self._extract_persona_fields(best)
            else:
                # 自动 / 多人设轮换: best-fit per group, prefer variety (avoid reuse)
                _used_rec_ids: set = set()
                for g in groups:
                    gid = g["group_id"]
                    content_type = g.get("content_type", "")
                    scene_dict   = scene_assignments.get(gid, {})
                    # Prefer personas not yet assigned in this batch; fallback to full pool
                    candidates = [r for r in persona_pool if r.get("record_id") not in _used_rec_ids] or persona_pool
                    chosen = max(candidates, key=lambda r: _soft_score(r, content_type, scene_dict))
                    assignments[gid] = self._extract_persona_fields(chosen)
                    _used_rec_ids.add(chosen.get("record_id"))
                    # Warn if chosen persona has no tag signal (selected purely by priority)
                    if _tag_signal(chosen, content_type, scene_dict) < 0.001:
                        logger.warning(
                            "_assign_personas [%s]: zero tag signal for group %s (content_type=%r) — "
                            "selected %s by priority only; consider adding 适合人设标签/人设适配标签 config",
                            persona_mode, gid, content_type, f.get_text(chosen, "人设编号"),
                        )
        else:
            # Fallback: derive pseudo-persona from Scene person fields
            for g in groups:
                scene = scene_assignments.get(g["group_id"], {})
                person_type = scene.get("人物类型", "").strip()
                if person_type and person_type not in ("无人物", "纯产品", ""):
                    assignments[g["group_id"]] = {
                        "persona_id": None,
                        "persona_label": person_type,
                        "gender": scene.get("性别倾向", ""),
                        "age": scene.get("年龄段", ""),
                        "appearance": scene.get("外貌风格", ""),
                        "posture": scene.get("姿态倾向", ""),
                        "style": "",
                        "action": "",
                        "prompt_template": "",
                        "consistency_template": "",
                        "source": "scene_fallback",
                    }
                else:
                    assignments[g["group_id"]] = None

        return assignments

    def _extract_persona_fields(self, persona_rec: dict) -> dict:
        """Extract Persona table fields into a flat dict."""
        f = self._feishu
        return {
            "persona_id":             f.get_text(persona_rec, "人设编号"),
            "persona_label":          f.get_text(persona_rec, "人设名称"),
            "gender":                 f.get_option(persona_rec, "性别倾向"),
            "age":                    f.get_option(persona_rec, "年龄段"),
            "appearance":             f.get_text(persona_rec, "外貌风格"),
            "style":                  f.get_text(persona_rec, "穿搭风格"),
            "action":                 f.get_text(persona_rec, "动作倾向"),
            "qi_zhi_tags":            f.get_options(persona_rec, "气质标签"),
            "prompt_template":        f.get_text(persona_rec, "Prompt描述模板"),
            "consistency_template":   f.get_text(persona_rec, "一致性锚点模板"),
            "source": "persona_table",
        }

    # ------------------------------------------------------------------
    # Creative Brief  (per-group unified intent object)
    # ------------------------------------------------------------------

    # Ordered title pattern pool (also used by _build_text_prompts_from_strategy for legacy path)
    _TITLE_PATTERNS = [
        "疑问句式（如：为什么我…？）",
        "数字/对比句式（如：买了X件才发现…）",
        "场景直述句式（如：健身/通勤/约会时…）",
        "反转/意外句式（如：没想到一条链子竟然…）",
        "情绪共鸣句式（如：那种感觉就是…）",
    ]

    _NARRATIVE_ANGLES = [
        "搭配点睛",
        "日常实用",
        "细节质感",
        "氛围感种草",
        "礼物推荐",
    ]

    _STRUCTURE_MODES = [
        "场景切入",
        "痛点切入",
        "体验切入",
        "对比切入",
        "情绪切入",
    ]

    def _build_creative_briefs(
        self, groups: list[dict], cfg: dict,
        scene_assignments: dict, persona_assignments: dict,
    ) -> dict:
        """
        Build one Creative Brief dict per group.
        Brief consolidates: strategy_id, scene_id, persona_id, shotplan_id,
        title_pattern, narrative_angle, structure_mode, consistency_anchor.
        """
        f = self._feishu
        platform = cfg["platforms"][0] if cfg["platforms"] else ""
        category = cfg.get("_category", "")   # will be populated below if empty

        # Only C-suffix groups for indexing (determines title pattern rotation)
        img_groups = [g for g in groups if g["type"] == "img"]
        total_img = len(img_groups)

        # Differentiation strength → how far apart narrative angles / structure modes spread
        diff_strength        = cfg.get("diff_strength", "中")
        consistency_strength = cfg.get("consistency_strength", "强")

        # Per-dimension rotation step per diff_strength:
        #   低 → title rotates step=1 (avoids exact repetition), narrative/structure fixed at [0]
        #         Rationale: avoid quality regression ("all titles identical") while keeping
        #         narrative tone consistent across a low-differentiation batch.
        #   中 → all dimensions rotate step=1 (sequential round-robin, current default)
        #   高 → all dimensions rotate step=2 (skip-one spread; 2 is coprime with pool size 5)
        if diff_strength == "高":
            _title_step = _narrative_step = _structure_step = 2
        elif diff_strength == "低":
            _title_step, _narrative_step, _structure_step = 1, 0, 0
        else:  # 中 or unknown
            _title_step = _narrative_step = _structure_step = 1

        briefs: dict = {}
        for i, g in enumerate(groups):
            gid = g["group_id"]
            content_type = g["content_type"]
            scene = scene_assignments.get(gid, {})
            persona = persona_assignments.get(gid)

            # Rotate title pattern per group (img groups only; vid groups inherit index 0)
            if g["type"] == "img":
                group_idx = img_groups.index(g)   # 0-based
                title_pattern   = self._TITLE_PATTERNS[(group_idx * _title_step) % len(self._TITLE_PATTERNS)]
                narrative_angle = self._NARRATIVE_ANGLES[(group_idx * _narrative_step) % len(self._NARRATIVE_ANGLES)]
                structure_mode  = self._STRUCTURE_MODES[(group_idx * _structure_step) % len(self._STRUCTURE_MODES)]
            else:
                title_pattern   = self._TITLE_PATTERNS[0]
                narrative_angle = self._NARRATIVE_ANGLES[0]
                structure_mode  = self._STRUCTURE_MODES[0]

            # Try to read narrative angle overrides from Strategy table if it has 叙事角度标签
            # (non-blocking — if field missing just keep default)
            strategy_id   = ""
            shotplan_id   = ""
            scene_id      = scene.get("scene_id", "")
            persona_id    = (persona or {}).get("persona_id") or ""
            persona_label = (persona or {}).get("persona_label") or ""

            # Build consistency_anchor from Persona (preferred) or Scene fallback
            if persona:
                tmpl = persona.get("consistency_template", "")
                if tmpl:
                    consistency_anchor = tmpl
                else:
                    parts = [
                        persona.get("persona_label", ""),
                        persona.get("gender", ""),
                        persona.get("age", ""),
                        persona.get("appearance", ""),
                    ]
                    desc = "、".join(x for x in parts if x)
                    consistency_anchor = f"同一人物（{desc}），同套服装，同款发型，同一面部特征" if desc else ""
            else:
                # No persona — build from scene
                gender = scene.get("性别倾向", "")
                age    = scene.get("年龄段", "")
                appear = scene.get("外貌风格", "")
                desc   = "、".join(x for x in [gender, age, appear] if x)
                consistency_anchor = f"同一人物（{desc}），同套服装，同款发型，同一面部特征" if desc else ""

            briefs[gid] = {
                "group_id":           gid,
                "group_type":         g["type"],
                "platform":           platform,
                "content_type":       content_type,
                "title_pattern":      title_pattern,
                "narrative_angle":    narrative_angle,
                "structure_mode":     structure_mode,
                "persona_id":         persona_id,
                "persona_label":      persona_label,
                "scene_id":           scene_id,
                "scene_mode":         scene.get("场景描述_中文", "")[:30],
                "strategy_id":        strategy_id,   # filled later by _fill_prompts
                "shotplan_id":        shotplan_id,   # filled later by _fill_prompts
                "consistency_anchor": {
                    "person":  consistency_anchor,
                    "product": "同一颜色、同一材质、同一挂接方式",
                    "style":   "统一光线、统一色温、统一画面风格",
                },
                "diff_strength":          diff_strength,
                "consistency_strength":   consistency_strength,
            }
            logger.info(
                "_build_creative_briefs: group=%s title_pattern=%r narrative_angle=%r persona=%r scene=%s",
                gid, title_pattern, narrative_angle, persona_label, scene_id,
            )

        return briefs

    # ------------------------------------------------------------------
    # Prompt builders (table-driven)
    # ------------------------------------------------------------------

    def _build_text_prompts_from_strategy(
        self,
        strategy: dict,
        sku_summary: str,
        platforms: list[str],
        content_type: str,
        group_type: str = "img",
        scene: dict | None = None,
        group_index: int = 1,
        total_groups: int = 1,
        brief: dict | None = None,
        persona: dict | None = None,
    ) -> tuple[str, str]:
        """Build (system_prompt, user_prompt) using a Strategy record from 表8.
        When `brief` is provided, title_pattern and narrative_angle come from Brief.
        """
        f = self._feishu
        system = f.get_text(strategy, "系统提示词前缀").strip() or (
            "你是一名专业的电商种草文案策划，擅长为得物/小红书平台创作高转化率内容。"
        )

        # P1-2: Inject 正文禁忌 into system prompt if configured (best-effort, field may not exist)
        try:
            forbidden_text = f.get_text(strategy, "正文禁忌").strip()
            if forbidden_text:
                system += f"\n\n【正文禁忌】以下表达绝对禁止出现：{forbidden_text}"
        except Exception:
            pass
        nodes_raw = f.get_text(strategy, "文案叙事节点").strip()
        try:
            nodes = json.loads(nodes_raw) if nodes_raw else []
        except json.JSONDecodeError:
            nodes = []

        if nodes:
            normalized_nodes: list[tuple[int, str, str]] = []
            for idx, n in enumerate(nodes, start=1):
                if isinstance(n, dict):
                    label = str(n.get("zh") or n.get("node") or "").strip()
                    guidance = str(n.get("guidance") or "").strip()
                    node_index = n.get("index")
                    try:
                        node_index = int(node_index)
                    except Exception:
                        node_index = idx
                    normalized_nodes.append((node_index, label, guidance))
                else:
                    normalized_nodes.append((idx, str(n).strip(), ""))
            node_lines = "\n".join(
                f"{node_index}. 【{label}】{guidance}".rstrip()
                for node_index, label, guidance in normalized_nodes if label
            ) or "（按内容类型的常规结构展开）"
        elif nodes_raw:
            import re as _re
            raw_parts = _re.split(r"→|->|\n", nodes_raw)
            raw_parts = [p.strip() for p in raw_parts if p.strip()]
            node_lines = "\n".join(f"{i + 1}. 【{p}】" for i, p in enumerate(raw_parts))
        else:
            node_lines = "（按内容类型的常规结构展开）"

        platform_str = "、".join(platforms)
        word_count = "50-200字" if group_type == "vid" else "300-800字"

        # Build scene context block
        scene_block = ""
        if scene:
            scene_desc = scene.get("场景描述_中文", "")
            scene_style = scene.get("风格基调词", "")
            # Read new optional field: 道具建议 — adds props richness to text context
            props_hint = scene.get("道具建议", "").strip()
            parts = [p for p in [scene_desc, scene_style] if p]
            if parts:
                scene_block = f"\n\n场景设定（请将内容植入此场景氛围中）：{'｜'.join(parts)}"
                if props_hint:
                    scene_block += f"。画面道具参考：{props_hint}"

        # Title guidance — prefer Strategy 标题句式池 JSON array if present
        title_guide = f.get_text(strategy, "标题写作指南").strip()

        # Read new optional Strategy field: 标题句式池
        title_pool_raw = ""
        try:
            title_pool_raw = f.get_text(strategy, "标题句式池").strip()
        except Exception:
            pass

        title_pool: list[str] = []
        if title_pool_raw:
            try:
                parsed = json.loads(title_pool_raw)
                if isinstance(parsed, list):
                    title_pool = [str(x) for x in parsed if x]
            except (json.JSONDecodeError, Exception):
                pass

        # Resolve this group's title pattern:
        # 1. From Brief (preferred — already rotated by _build_creative_briefs)
        # 2. From Strategy 标题句式池 (table-configured pool)
        # 3. From hardcoded _TITLE_PATTERNS (legacy fallback)
        #
        # P1-2: When no Brief, prefer Strategy 叙事角度标签/结构模式 over empty defaults
        if brief:
            this_pattern    = brief.get("title_pattern") or self._TITLE_PATTERNS[(group_index - 1) % len(self._TITLE_PATTERNS)]
            narrative_angle = brief.get("narrative_angle", "")
            structure_mode  = brief.get("structure_mode", "")
        else:
            if title_pool:
                this_pattern = title_pool[(group_index - 1) % len(title_pool)]
            else:
                this_pattern = self._TITLE_PATTERNS[(group_index - 1) % len(self._TITLE_PATTERNS)]
            # Try Strategy 叙事角度标签 (multi-select) → pick one by round-robin
            try:
                strategy_angles = f.get_options(strategy, "叙事角度标签") or []
                narrative_angle = strategy_angles[(group_index - 1) % len(strategy_angles)] if strategy_angles else ""
            except Exception:
                narrative_angle = ""
            # Try Strategy 结构模式 (single-select)
            try:
                structure_mode = f.get_option(strategy, "结构模式") or ""
            except Exception:
                structure_mode = ""

        title_instruction = (
            f"<标题（≤20字）>\n参考方向：{title_guide}" if title_guide else "<标题（≤20字）>"
        )

        # Read new optional Strategy field: 差异化提示模板
        diff_template = ""
        try:
            diff_template = f.get_text(strategy, "差异化提示模板").strip()
        except Exception:
            pass

        # Diversity instruction block
        diversity_block = ""
        if total_groups > 1:
            if diff_template:
                # Use table-configured template, substituting placeholders
                diversity_block = (
                    "\n\n" + diff_template
                    .replace("{group_index}", str(group_index))
                    .replace("{total_groups}", str(total_groups))
                    .replace("{title_pattern}", this_pattern)
                    .replace("{narrative_angle}", narrative_angle)
                )
            else:
                diversity_block = (
                    f"\n\n⚠️ 差异化要求：这是本产品第 {group_index} 篇笔记（共 {total_groups} 篇）。"
                    f"标题请采用「{this_pattern}」"
                )
                if narrative_angle:
                    diversity_block += f"，叙事角度为「{narrative_angle}」"
                if structure_mode:
                    diversity_block += f"，结构模式为「{structure_mode}」"
                diversity_block += "，叙事切入角度必须与其他篇次明显区分，禁止重复相同的开头句式或叙事骨架。"

        # Optional persona context in text (adds persona feeling to scene description)
        # P1-3: prefer prompt_template as the authoritative persona description
        persona_block = ""
        if persona:
            _pt = persona.get("prompt_template", "").strip()
            if _pt:
                persona_block = f"\n\n人物感觉参考（请将此人物形象自然融入场景叙事中）：{_pt}"
            else:
                pa = persona.get("appearance", "")
                ps = persona.get("style", "")
                pq = "、".join(persona.get("qi_zhi_tags") or [])
                persona_parts = [x for x in [pa, ps, pq] if x]
                if persona_parts:
                    persona_block = f"\n\n人物感觉参考：{', '.join(persona_parts)}，使用时请自然地将此人物形象融入场景叙事中。"

        user = (
            f"请为以下产品生成「{content_type}」类型的完整内容（标题+正文）。\n\n"
            f"目标平台：{platform_str}\n"
            f"内容类型：{content_type}\n\n"
            f"产品信息：\n{sku_summary}{scene_block}{persona_block}\n\n"
            f"叙事结构（请按顺序展开）：\n{node_lines}{diversity_block}\n\n"
            f"输出格式：\n【标题】\n{title_instruction}\n\n【正文】\n<正文（{word_count}）>"
        )
        return system, user

    _EMOTION_ZH: dict[str, str] = {
        "松弛感":   "放松随性",
        "兴奋感":   "活力四射",
        "专业理性": "专业理性",
        "温暖亲密": "温暖亲密",
        "高冷极简": "高冷极简",
        "活泼俏皮": "活泼俏皮",
    }

    # Default shot roles when no ShotPlan is configured — ensures each image is distinct
    _DEFAULT_SHOT_ROLES: list[str] = [
        "产品正面全景，完整展示整体外观与设计风格",
        "产品细节特写，聚焦材质质感与精工细节",
        "产品上手使用，展示自然持握/使用中的状态",
        "产品侧后角度，呈现立体感与侧面线条",
        "产品平铺俯拍，俯视视角展示整体与搭配",
        "产品场景融合，与背景道具自然搭配构图",
    ]

    # Master prompt target length; sub-prompts target 200 chars each
    _MASTER_PROMPT_MAX = 600
    # Technical params that add atmosphere without overwhelming the prompt
    _TECH_PARAM_KEYS = ("光线方向", "色温", "景深感", "镜头感")

    def _build_image_master_prompt(
        self, strategy: dict | None, sku_fields: dict, scene: dict,
        persona: dict | None = None, brief: dict | None = None,
    ) -> str:
        """Build the master context prompt in Chinese for image generation.

        Length budget: target ≤600 chars so combined (master + sub) stays ≤800.
        Sections are dropped in priority order if over budget — never hard-truncated:
          drop order: 【技术参数】 → 【避免】缩短 → 【场景】缩短
        """
        f = self._feishu
        rec = {"fields": sku_fields}
        colors    = "、".join(f.get_options(rec, "颜色"))
        materials = "、".join(f.get_options(rec, "材质"))
        styles    = "、".join(f.get_options(rec, "风格"))
        name      = f.get_text(rec, "产品简称") or f.get_text(rec, "SKU名称")
        product_desc = f"{name}，{colors}色，{materials}材质，{styles}风格".strip("，")

        scene_zh    = scene.get("场景描述_中文", "").strip()
        style_words = scene.get("风格基调词", "").strip()
        exclude     = scene.get("排除描述", "").strip()

        # Person fields — prefer Persona table, fallback to Scene
        # P1-3: If Persona has prompt_template, use it as the full person description
        person_type = scene.get("人物类型", "").strip()
        _persona_prompt_template = (persona or {}).get("prompt_template", "").strip()
        if persona:
            gender     = persona.get("gender", "").strip() or scene.get("性别倾向", "").strip()
            age_range  = persona.get("age", "").strip()    or scene.get("年龄段", "").strip()
            appearance = persona.get("appearance", "").strip() or scene.get("外貌风格", "").strip()
            posture    = persona.get("action", "").strip()     or scene.get("姿态倾向", "").strip()
        else:
            gender     = scene.get("性别倾向", "").strip()
            age_range  = scene.get("年龄段", "").strip()
            appearance = scene.get("外貌风格", "").strip()
            posture    = scene.get("姿态倾向", "").strip()

        # Technical parameter fields (single-select, may be empty)
        tech_params = [
            scene.get(k, "").strip() for k in self._TECH_PARAM_KEYS if scene.get(k, "").strip()
        ]

        emotion_zh = f.get_option(strategy, "情绪基调") if strategy else ""
        mood_zh    = self._EMOTION_ZH.get(emotion_zh, "自然真实")

        # New optional field: 道具建议 from Scene (adds prop variety to image)
        props_hint = scene.get("道具建议", "").strip()

        # --- build core sections (always included) ---
        # Chain-on-phone attachment note: always injected for phone chain products
        chain_note = (
            "手机链通过手机壳底部中间挂绳孔或侧边孔穿入固定，"
            "链条自然垂坠于手机下方或侧方，比例协调，挂接处自然无穿帮，"
            "链条长度约为手机高度的1/2至等长，不拉扯变形"
        )
        core_parts = [
            f"【产品】{product_desc}",
            f"【挂接规范】{chain_note}",
            "",
            f"【场景】{scene_zh}" if scene_zh else "",
            f"风格：{style_words}。情绪：{mood_zh}。" if style_words else f"情绪：{mood_zh}。",
        ]

        person_part: list[str] = []
        if person_type and person_type not in ("无人物",):
            if _persona_prompt_template:
                # action (动作倾向) provides specific pose guidance; style is now embedded in prompt_template
                _posture = (persona or {}).get("action", "").strip()
                _extra_str = "，" + _posture if _posture else ""
                person_part = ["", f"【人物】{_persona_prompt_template}{_extra_str}"]
                # Scene 外貌风格 quality standard: inject when it's a rich description (>12 chars)
                # e.g. "年轻亚洲女性，精致五官，自然妆感，无过度美颜修图" — ensures photo-realism
                # Short labels like "精致通勤" (4 chars) are skipped
                if appearance and len(appearance) > 12:
                    person_part.append(f"人物质感：{appearance}")
            else:
                person_attrs = [x for x in [gender, age_range, appearance, posture] if x]
                person_line = person_type
                if person_attrs:
                    person_line += "，" + "，".join(person_attrs)
                person_part = ["", f"【人物】{person_line}"]

        # Consistency anchor: use Persona consistency_template if present (richer description)
        persona_consistency = ""
        if persona:
            tmpl = persona.get("consistency_template", "").strip()
            if tmpl:
                persona_consistency = tmpl
        if not persona_consistency and brief:
            ca = brief.get("consistency_anchor", {})
            if ca.get("person"):
                persona_consistency = ca["person"]

        consistency_strength = (brief or {}).get("consistency_strength", "强")
        consistency_lines = [
            "",
            "【一致性要求】",
            "- 所有图片保持完全相同的产品外观（颜色、材质、细节）",
        ]
        if persona_consistency:
            consistency_lines.append(f"- {persona_consistency}")
        else:
            consistency_lines.append("- 同一人物（同一人、同套服装、同款发型）")
        consistency_lines.append("- 统一光线和色彩风格贯穿始终")
        if consistency_strength == "强":
            consistency_lines.append(
                "- 【强一致性】人物面孔特征、发型、服装颜色/款式/细节禁止在不同图片间出现任何漂移或变化，"
                "产品颜色/材质/挂接方式必须完全一致，禁止换人、换装、换发型"
            )
        consistency_part = consistency_lines

        # Optional sections, dropped first when over budget
        exclude_part = ["", f"【避免】{exclude}"] if exclude else []
        tech_part    = ["", f"【技术参数】{'、'.join(tech_params)}"] if tech_params else []
        props_part   = ["", f"【道具参考】{props_hint}"] if props_hint else []

        def _join(parts_list: list[list[str]]) -> str:
            merged = []
            for p in parts_list:
                merged.extend(p)
            return "\n".join(x for x in merged if x is not None)

        # Try full prompt first (props > tech > exclude drop order)
        full = _join([core_parts, person_part, props_part, tech_part, consistency_part, exclude_part])
        if len(full) <= self._MASTER_PROMPT_MAX:
            return full

        # Drop tech params
        reduced = _join([core_parts, person_part, props_part, consistency_part, exclude_part])
        if len(reduced) <= self._MASTER_PROMPT_MAX:
            return reduced

        # Drop props
        reduced = _join([core_parts, person_part, consistency_part, exclude_part])
        if len(reduced) <= self._MASTER_PROMPT_MAX:
            return reduced

        # Trim exclude to first clause
        if exclude:
            short_excl = exclude.split("，")[0].split("。")[0]
            reduced = _join([core_parts, person_part, consistency_part, ["", f"【避免】{short_excl}"]])
            if len(reduced) <= self._MASTER_PROMPT_MAX:
                return reduced

        # Drop exclude entirely
        reduced = _join([core_parts, person_part, consistency_part])
        if len(reduced) <= self._MASTER_PROMPT_MAX:
            return reduced

        # Last resort: trim scene_zh to ≤60 chars
        if scene_zh and len(scene_zh) > 60:
            core_parts[3] = f"【场景】{scene_zh[:60]}"
        return _join([core_parts, person_part, consistency_part])

    def _build_image_sub_prompts(
        self, shotplan: dict | None, scene: dict, img_count: int,
        persona: dict | None = None, brief: dict | None = None,
    ) -> list[str]:
        """Build per-shot sub-prompts in Chinese from ShotPlan + Scene."""
        f = self._feishu
        scene_zh = scene.get("场景描述_中文", "").strip()
        scene_suffix = f"，{scene_zh}" if scene_zh else ""

        # Build person suffix for shots that should include real people
        # Persona source (preferred) → Scene fallback
        # P1-3: use prompt_template as the authoritative person description when available
        person_type = scene.get("人物类型", "").strip()
        _no_person_types = {"无人物", "纯产品", ""}
        if person_type and person_type not in _no_person_types:
            _sub_prompt_template = (persona or {}).get("prompt_template", "").strip()
            if persona:
                gender  = persona.get("gender", "").strip() or scene.get("性别倾向", "").strip()
                age     = persona.get("age", "").strip()    or scene.get("年龄段", "").strip()
                appear  = persona.get("appearance", "").strip() or scene.get("外貌风格", "").strip()
                posture = persona.get("action", "").strip()     or scene.get("姿态倾向", "").strip()
            else:
                gender  = scene.get("性别倾向", "").strip()
                age     = scene.get("年龄段", "").strip()
                appear  = scene.get("外貌风格", "").strip()
                posture = scene.get("姿态倾向", "").strip()

            if _sub_prompt_template:
                # action (动作倾向) provides specific pose guidance; style is now embedded in prompt_template
                # Quality standard (外貌风格) is already injected in master_prompt — no duplication needed
                _posture = (persona or {}).get("action", "").strip()
                _extra_str = "，" + _posture if _posture else ""
                person_suffix = f"，画面中有{person_type}（{_sub_prompt_template}{_extra_str}）"
            else:
                person_attrs = "、".join(x for x in [gender, age, appear, posture] if x)
                person_suffix = f"，画面中有{person_type}" + (f"（{person_attrs}）" if person_attrs else "")

            # Consistency anchor — prefer Persona consistency_template; else build from appearance
            appearance_anchor = "、".join(x for x in [gender, age, appear] if x)
            if persona and persona.get("consistency_template"):
                _anchor_text = persona["consistency_template"]
            elif brief and brief.get("consistency_anchor", {}).get("person"):
                _anchor_text = brief["consistency_anchor"]["person"]
            else:
                _anchor_text = (
                    f"本组所有图片为同一人物（{appearance_anchor}）："
                    "保持完全相同的服装（颜色/款式/细节）、相同发型、相同面孔特征，禁止更换服装或人物"
                )
            # consistency_strength=强 appends a hard drift-prohibition clause
            _cs = (brief or {}).get("consistency_strength", "强")
            if _cs == "强":
                _anchor_text += "；人物面孔/发型/服装禁止漂移，产品细节禁止变化"
            consistency_note = f"，【一致性约束】{_anchor_text}"
        else:
            person_suffix = ""
            consistency_note = ""

        # Read new optional ShotPlan fields for inter-shot differentiation
        no_repeat_shots = ""
        action_variety  = ""
        if shotplan:
            try:
                no_repeat_shots = f.get_text(shotplan, "禁止重复镜头").strip()
            except Exception:
                pass
            try:
                action_variety = f.get_text(shotplan, "动作变化要求").strip()
            except Exception:
                pass

        # Build constraint suffix combining action_variety + no_repeat_shots (P1-1)
        _constraint_parts = []
        if action_variety:
            _constraint_parts.append(f"动作变化：{action_variety}")
        if no_repeat_shots:
            _constraint_parts.append(f"禁止重复：{no_repeat_shots}")
        _constraint_suffix = f"，【构图约束】{'；'.join(_constraint_parts)}" if _constraint_parts else ""

        def _default_shot(idx: int) -> str:
            role = self._DEFAULT_SHOT_ROLES[idx % len(self._DEFAULT_SHOT_ROLES)]
            return f"第{idx + 1}张：{role}{scene_suffix}{person_suffix}{consistency_note}{_constraint_suffix}"

        if shotplan is None:
            return [_default_shot(i) for i in range(img_count)]

        nodes_raw = f.get_text(shotplan, "角色序列").strip()
        try:
            nodes = json.loads(nodes_raw) if nodes_raw else []
        except json.JSONDecodeError:
            nodes = []

        if not nodes:
            return [_default_shot(i) for i in range(img_count)]

        result = []
        for i in range(img_count):
            if i < len(nodes):
                node = nodes[i]
                # Build shot label from zh (name) + guidance (shooting instruction)
                zh_name = node.get("zh", "")
                guidance = node.get("guidance", "")
                # Also support legacy {"shot": "...", "desc": "..."} format
                if not zh_name and node.get("shot"):
                    zh_name = node["shot"]
                if not guidance and node.get("desc"):
                    guidance = node["desc"]

                if zh_name and guidance:
                    zh_text = f"{zh_name}：{guidance}"
                elif zh_name:
                    zh_text = zh_name
                elif guidance:
                    zh_text = guidance
                else:
                    zh_text = ""

                had_placeholder = "{scene_description}" in zh_text
                zh_text = zh_text.replace("{scene_description}", scene_zh)
                effective_scene_suffix = "" if had_placeholder else scene_suffix
                if zh_text:
                    result.append(f"第{i + 1}张：{zh_text}{effective_scene_suffix}{person_suffix}{consistency_note}{_constraint_suffix}")
                else:
                    result.append(_default_shot(i))
            else:
                # ShotPlan nodes exhausted — fall back to default roles
                result.append(_default_shot(i))
        return result

    # ------------------------------------------------------------------
    # Prompt engine — generates actual Prompt text and writes to 表3
    # ------------------------------------------------------------------

    def _fill_prompts(
        self,
        prompt_records: list[dict],
        sku_fields: dict,
        cfg: dict,
        tags: list[str],
        text_adapter: TextModelAdapter,
        scene_assignments: dict | None = None,
        briefs: dict | None = None,
        persona_assignments: dict | None = None,
    ):
        f = self._feishu
        table_prompt = self._tables["prompt"]

        sku_summary = self._build_sku_summary(sku_fields)
        tag_str = " ".join(tags)
        category = f.get_option({"fields": sku_fields}, "品类")
        if scene_assignments is None:
            scene_assignments = {}
        if briefs is None:
            briefs = {}
        if persona_assignments is None:
            persona_assignments = {}

        # Pre-compute ordered list of C-suffix records for group_index tracking
        c_suffix_records = [pr for pr in prompt_records if pr["suffix"] == "C"]
        total_c_groups = len(c_suffix_records)
        c_group_index_map = {pr["group"]["group_id"]: i + 1 for i, pr in enumerate(c_suffix_records)}

        for pr in prompt_records:
            g = pr["group"]
            suffix = pr["suffix"]
            prompt_type = pr["prompt_type"]
            record_id = pr["prompt_record_id"]
            content_type = g["content_type"]
            platforms = cfg["platforms"]
            gid = g["group_id"]

            brief  = briefs.get(gid)
            persona = persona_assignments.get(gid)

            if suffix == "C":
                # Text/copy prompt — use Strategy if available, else hardcoded
                scene = scene_assignments.get(gid, {})
                strategy = self._lookup_strategy(
                    content_type, platforms[0] if platforms else "", category
                )
                # Update brief with resolved strategy_id for observability
                if brief and strategy:
                    brief["strategy_id"] = strategy.get("record_id", "")
                if strategy:
                    _group_index = c_group_index_map.get(gid, 1)
                    _system_prompt, user_prompt = self._build_text_prompts_from_strategy(
                        strategy, sku_summary, platforms, content_type, g["type"], scene=scene,
                        group_index=_group_index, total_groups=total_c_groups,
                        brief=brief, persona=persona,
                    )
                    combined_prompt = f"[SYS]\n{_system_prompt}\n[USR]\n{user_prompt}"
                    f.update_record(table_prompt, record_id, {"总Prompt": combined_prompt})
                else:
                    system_prompt, user_prompt = self._build_meta_prompt(
                        suffix, prompt_type, sku_summary, cfg, g, tag_str
                    )
                    try:
                        generated = text_adapter.complete(system_prompt, user_prompt)
                    except Exception as exc:
                        logger.error("Prompt engine failed for %s: %s", pr["prompt_code"], exc)
                        generated = f"[生成失败: {exc}]"
                    f.update_record(table_prompt, record_id, {"总Prompt": generated})

            else:  # suffix == "I" — image/video generation prompt
                scene = scene_assignments.get(gid, {})
                strategy = self._lookup_strategy(
                    content_type, platforms[0] if platforms else "", category
                )
                if g["type"] == "img":
                    img_count = g.get("img_per_piece", 4)
                    shotplan = self._lookup_shotplan("图片", content_type, category)
                            # Update brief with resolved shotplan_id for observability
                    if brief and shotplan:
                        brief["shotplan_id"] = shotplan.get("record_id", "")
                    master = self._build_image_master_prompt(
                        strategy, sku_fields, scene, persona=persona, brief=brief
                    )
                    subs = self._build_image_sub_prompts(
                        shotplan, scene, img_count, persona=persona, brief=brief
                    )
                    f.update_record(table_prompt, record_id, {
                        "总Prompt": master,
                        "子Prompt列表": json.dumps(subs, ensure_ascii=False),
                    })
                else:
                    # Video script prompt — use text adapter
                    system_prompt, user_prompt = self._build_meta_prompt(
                        suffix, prompt_type, sku_summary, cfg, g, tag_str
                    )
                    try:
                        generated = text_adapter.complete(system_prompt, user_prompt)
                    except Exception as exc:
                        logger.error("Prompt engine failed for %s: %s", pr["prompt_code"], exc)
                        generated = f"[生成失败: {exc}]"
                    f.update_record(table_prompt, record_id, {"总Prompt": generated})

            # Write observability fields to 表3 (best-effort, non-blocking)
            if brief:
                try:
                    ca = brief.get("consistency_anchor", {})
                    brief_summary = " | ".join(x for x in [
                        brief.get("persona_label", ""),
                        brief.get("scene_mode", ""),
                        brief.get("narrative_angle", ""),
                    ] if x)
                    obs_update: dict = {
                        "创意包摘要": brief_summary or "(无)",
                        "创意包JSON": json.dumps(brief, ensure_ascii=False),
                        "命中策略ID": brief.get("strategy_id", ""),
                        "命中场景ID": brief.get("scene_id", ""),
                        "命中人设ID": brief.get("persona_id", ""),
                        "命中ShotPlanID": brief.get("shotplan_id", ""),
                        "标题句式": brief.get("title_pattern", ""),
                        "叙事角度": brief.get("narrative_angle", ""),
                        "一致性锚点": ca.get("person", ""),
                        "是否兜底生成": "否" if brief.get("strategy_id") else "是",
                    }
                    f.update_record(table_prompt, record_id, obs_update)
                except Exception:
                    logger.debug("Failed to write observability fields to 表3 for %s", gid, exc_info=True)

    def _build_sku_summary(self, sku_fields: dict) -> str:
        f = self._feishu
        rec = {"fields": sku_fields}
        lines = [
            f"产品简称: {f.get_text(rec, '产品简称')}",
            f"SKU名称: {f.get_text(rec, 'SKU名称')}",
            f"商品名称: {f.get_text(rec, '商品名称')}",
            f"品类: {f.get_option(rec, '品类')}",
            f"适配机型: {f.get_text(rec, '适配机型')}",
            f"材质: {', '.join(f.get_options(rec, '材质'))}",
            f"颜色: {', '.join(f.get_options(rec, '颜色'))}",
            f"风格: {', '.join(f.get_options(rec, '风格'))}",
            f"目标人群: {', '.join(f.get_options(rec, '目标人群'))}",
            f"卖点1: {f.get_text(rec, '卖点1')}",
        ]
        sp2 = f.get_text(rec, "卖点2")
        if sp2:
            lines.append(f"卖点2: {sp2}")
        sp3 = f.get_text(rec, "卖点3")
        if sp3:
            lines.append(f"卖点3: {sp3}")
        price = f.get_number(rec, "价格区间")
        if price:
            lines.append(f"价格区间: {price}元")
        return "\n".join(lines)

    def _build_meta_prompt(
        self, suffix: str, prompt_type: str, sku_summary: str, cfg: dict, g: dict, tag_str: str
    ) -> tuple[str, str]:
        platforms = "、".join(cfg["platforms"])
        content_type = g["content_type"]

        if suffix == "C":
            word_count = "50-200字" if g["type"] == "vid" else "300-800字"
            system = (
                "你是一名专业的电商种草文案策划，擅长为得物/小红书平台创作高转化率内容。"
                "你生成的是用于后续AI生成内容的提示词（Prompt），不是最终文案。"
                "生成的Prompt应包含：内容风格、结构要求、情绪调性、平台特色表达要求。"
            )
            user = (
                f"请为以下产品生成一个「{prompt_type}」类型的Prompt。\n\n"
                f"目标平台：{platforms}\n"
                f"内容类型：{content_type}\n\n"
                f"产品信息：\n{sku_summary}\n\n"
                f"要求：Prompt应指导AI生成完整的标题（≤20字）、正文（{word_count}），"
                f"风格符合{content_type}定位，调性适合{platforms}平台受众。"
            )
        else:
            if g["type"] == "img":
                img_count = g.get("img_per_piece", 4)
                system = (
                    "你是一名专业的商业摄影/AI图片生成Prompt专家，擅长为电商产品设计高质量图片描述。"
                    "你生成的Prompt将用于AI图片生成模型。"
                    f"需要生成1个总体风格Prompt和{img_count}个单图子Prompt（JSON数组格式）。"
                )
                user = (
                    f"请为以下产品生成图片生成Prompt。\n\n"
                    f"目标平台：{platforms}\n"
                    f"内容类型：{content_type}\n\n"
                    f"产品信息：\n{sku_summary}\n\n"
                    f"输出格式：\n"
                    f"【总Prompt】\n<整体风格和视觉要求描述，英文，≤500字>\n\n"
                    f"【子Prompt列表】\n"
                    f"[\"<图1描述，英文，≤200字>\", \"<图2描述>\", ...（共{img_count}条）]"
                )
            else:
                system = (
                    "你是一名专业的短视频脚本策划，擅长为得物/小红书平台创作种草视频脚本。"
                    "你生成的是用于AI视频生成的Prompt/脚本，需包含画面描述、节奏、情绪和文案要点。"
                )
                user = (
                    f"请为以下产品生成视频脚本Prompt。\n\n"
                    f"目标平台：{platforms}\n"
                    f"内容类型：{content_type}\n"
                    f"视频时长：{g.get('vid_min_sec', 15)}-{g.get('vid_max_sec', 60)}秒\n\n"
                    f"产品信息：\n{sku_summary}\n\n"
                    f"要求：包含开场钩子、产品展示节奏、情绪高潮点和结尾CTA。"
                )

        return system, user

    @staticmethod
    def _extract_sub_prompts(generated_text: str, count: int) -> list[str]:
        """Try to parse sub-prompt JSON list from generated text. Fallback to splitting."""
        # Look for a JSON array in the text
        import re
        match = re.search(r'\[.*?\]', generated_text, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(0))
                if isinstance(result, list):
                    return result[:count]
            except json.JSONDecodeError:
                pass
        # Fallback: split by newline and take numbered items
        lines = [l.strip().lstrip('0123456789."•- ') for l in generated_text.split('\n') if l.strip()]
        return lines[:count] if lines else [generated_text[:200]]

    # ------------------------------------------------------------------
    # Generate content (AI API calls) → write to 表4
    # ------------------------------------------------------------------

    def _generate_content(
        self,
        groups: list[dict],
        prompt_records: list[dict],
        sku_fields: dict,
        cfg: dict,
        plan_record_id: str,
        tags: list[str] | None = None,
    ) -> list[str]:
        f = self._feishu
        table_content = self._tables["content"]
        table_prompt = self._tables["prompt"]
        now_ms = int(datetime.now().timestamp() * 1000)
        plan_code = self._make_plan_id(plan_record_id)

        # Build lookup: group_id + suffix → prompt record
        pr_map: dict[tuple, dict] = {}
        for pr in prompt_records:
            pr_map[(pr["group"]["group_id"], pr["suffix"])] = pr

        # Get SKU record_id from plan
        plan_rec = f.get_record(self._tables["plan"], plan_record_id)
        sku_link_val = plan_rec["fields"].get("关联SKU")
        sku_ids = f.get_link_ids({"fields": {"关联SKU": sku_link_val}}, "关联SKU") if sku_link_val else []

        content_record_ids = []
        task_type = cfg["task_type"]
        prior_titles: list[str] = []  # accumulate titles to prevent repetition across groups
        briefs = cfg.get("_briefs", {})
        persona_assignments = cfg.get("_persona_assignments", {})

        for g in groups:
            gid = g["group_id"]
            content_code = f"{plan_code}_{gid}"
            is_img = g["type"] == "img"

            # Dedup guard: if content record exists, check whether image generation needs retry
            existing_recs = f.list_records(table_content, filter_str=f'CurrentValue.[内容编号] = "{content_code}"')
            if existing_recs:
                existing_rec = existing_recs[0]
                content_record_id = existing_rec["record_id"]
                existing_gen_status = f.get_option(existing_rec, "生成状态")
                # If already successfully generated, skip entirely
                if existing_gen_status == "已生成":
                    logger.info("Content record %s already generated, skipping", content_code)
                    content_record_ids.append(content_record_id)
                    continue
                # Otherwise (生成失败 / 生成中 / blank) — retry generation without recreating the record
                logger.warning(
                    "Content record %s exists with status=%r — retrying generation",
                    content_code, existing_gen_status,
                )
                content_record_ids.append(content_record_id)
                # Reset status to 生成中 and clear failure reason
                f.update_record(table_content, content_record_id, {"生成状态": "生成中", "失败原因": ""})
                # Fall through to text + image generation below (skip the create block)
                created_new = False
            else:
                created_new = True

            if created_new:
                # Base content record
                content_fields: dict = {
                    "内容编号": content_code,
                    "关联规划": [plan_record_id],
                    "任务类型": task_type,
                    "目标平台": cfg["platforms"][0] if cfg["platforms"] else "",
                    "内容类型": g["content_type"],
                    "内容形态": ("单图文" if g.get("img_per_piece", 4) == 1 else "图文") if is_img else "视频",
                    "生成状态": "生成中",
                    "审核状态": "待审核",
                    "是否需要搬迁素材": "否" if task_type == "AI全创作" else "是",
                    "生成时间": now_ms,
                }
                if task_type != "AI全创作":
                    content_fields["搬迁状态"] = "待搬迁"
                if sku_ids:
                    content_fields["关联SKU"] = sku_ids

                content_record_id = f.create_record(table_content, content_fields)
                content_record_ids.append(content_record_id)

                # Mirror to local DB
                db.upsert_content(
                    content_code,
                    feishu_record_id=content_record_id,
                    plan_id=None,   # syncer will resolve FK later
                    task_type=task_type,
                    target_platform=cfg["platforms"][0] if cfg["platforms"] else "",
                    content_type=g["content_type"],
                    content_form=content_fields["内容形态"],
                    gen_status="生成中",
                )

                # Create skeleton content.json in local storage
                if self._storage:
                    try:
                        self._storage.save_content(plan_code, gid, {
                            "content_code": content_code,
                            "feishu_record_id": content_record_id,
                            "platform": cfg["platforms"][0] if cfg["platforms"] else "",
                            "content_type": g["content_type"],
                            "content_form": content_fields["内容形态"],
                            "title": "", "body": "", "tags": "",
                        }, {})
                        # Write local folder path back to Feishu record
                        folder_path = str(self._storage.get_content_path(plan_code, gid))
                        f.update_record(table_content, content_record_id, {"素材文件夹路径": folder_path})
                    except Exception:
                        logger.warning("LocalStorage save_content failed for %s", gid, exc_info=True)

            # Get text prompt
            c_pr = pr_map.get((gid, "C"))
            i_pr = pr_map.get((gid, "I"))

            c_prompt_rec = f.get_record(table_prompt, c_pr["prompt_record_id"]) if c_pr else None
            i_prompt_rec = f.get_record(table_prompt, i_pr["prompt_record_id"]) if i_pr else None

            c_prompt_text = f.get_text(c_prompt_rec, "总Prompt") if c_prompt_rec else ""
            i_prompt_text = f.get_text(i_prompt_rec, "总Prompt") if i_prompt_rec else ""

            # Parse strategy system prompt from combined [SYS]/[USR] format if present
            _SYS_MARKER = "[SYS]\n"
            _USR_MARKER = "\n[USR]\n"
            if c_prompt_text.startswith(_SYS_MARKER) and _USR_MARKER in c_prompt_text:
                _split_idx = c_prompt_text.index(_USR_MARKER)
                c_system_prompt = c_prompt_text[len(_SYS_MARKER):_split_idx]
                c_prompt_text = c_prompt_text[_split_idx + len(_USR_MARKER):]
            else:
                c_system_prompt = None

            update: dict = {}
            fail_reason = None

            if task_type in ("AI全创作", "图片实拍+AI文案", "视频实拍+AI文案"):
                # --- Generate text (title + body + tags) ---
                try:
                    text_adapter = build_text_adapter(cfg["text_model_name"], self._model_params)
                    _BASE_SYSTEM = (
                        "你是专业的电商种草文案撰写者，深谙得物、小红书、抖音等平台的爆款内容规律。\n"
                        "写作要求：\n"
                        "1. 标题必须有钩子感（痛点/数字/反转/共鸣），禁止平铺直述\n"
                        "2. 正文严格按照给定的叙事节点顺序展开，每个节点有明确的情绪递进\n"
                        "3. 语言口语化、真实感强，像真人在分享，不要广告腔\n"
                        "4. 适当使用emoji增强氛围感，但不过度堆砌\n"
                        "5. 结尾有行动引导或情感共鸣点\n\n"
                        "输出格式：\n【标题】\n<标题>\n\n【正文】\n<正文>"
                    )
                    # Use strategy-specific system prompt if available; append base rules as suffix
                    if c_system_prompt:
                        system_for_generation = c_system_prompt + "\n\n" + _BASE_SYSTEM
                    else:
                        system_for_generation = _BASE_SYSTEM
                    # Inject anti-repetition context: tell the LLM which titles already exist
                    if prior_titles:
                        prior_block = "\n".join(f"  - {t}" for t in prior_titles)
                        system_for_generation += (
                            f"\n\n⚠️ 本批次已生成以下标题，新内容的标题句式和叙事角度必须与之明显不同，禁止复用相同的开头词或句型结构：\n{prior_block}"
                        )
                    text_result = text_adapter.complete(system_for_generation, c_prompt_text)
                    title, body, _ = self._parse_text_result(text_result)
                    prior_titles.append(title)  # track for subsequent groups
                    tags_text = " ".join(tags) if tags else ""
                    update["标题"] = title
                    update["正文"] = body
                    update["标签"] = tags_text
                    # Save text locally + write debug/observability block to content.json
                    if self._storage:
                        try:
                            self._storage.update_text(plan_code, gid, title, body, tags_text)
                            # Persist debug block with brief info
                            _brief_g = briefs.get(gid, {})
                            if _brief_g:
                                _ca = _brief_g.get("consistency_anchor", {})
                                debug_block = {
                                    "brief_summary": " | ".join(x for x in [
                                        _brief_g.get("persona_label", ""),
                                        _brief_g.get("scene_mode", ""),
                                        _brief_g.get("narrative_angle", ""),
                                    ] if x),
                                    "strategy_id":        _brief_g.get("strategy_id", ""),
                                    "scene_id":           _brief_g.get("scene_id", ""),
                                    "persona_id":         _brief_g.get("persona_id", ""),
                                    "shotplan_id":        _brief_g.get("shotplan_id", ""),
                                    "title_pattern":      _brief_g.get("title_pattern", ""),
                                    "narrative_angle":    _brief_g.get("narrative_angle", ""),
                                    "consistency_anchor": _ca.get("person", ""),
                                    "failed_image_indexes": [],
                                }
                                self._storage.update_content_debug(plan_code, gid, debug_block)
                        except Exception:
                            logger.warning("LocalStorage update_text/debug failed for %s", gid, exc_info=True)
                    # Write text to Feishu immediately (don't wait for images)
                    try:
                        f.update_record(table_content, content_record_id, {
                            "标题": title, "正文": body, "标签": tags_text,
                        })
                        logger.info("Text written to Feishu for %s", gid)
                    except Exception:
                        logger.warning("Failed to write text to Feishu for %s", gid, exc_info=True)
                except Exception as exc:
                    fail_reason = f"文案生成失败: {exc}"

            if task_type == "AI全创作" and not fail_reason:
                if is_img:
                    # --- Generate images ---
                    sub_prompts_json = f.get_text(i_prompt_rec, "子Prompt列表") if i_prompt_rec else "[]"
                    try:
                        sub_prompts = json.loads(sub_prompts_json) if sub_prompts_json.strip() else []
                    except json.JSONDecodeError:
                        sub_prompts = []

                    img_adapter = build_image_adapter(self._model_params, cfg["image_model_name"])
                    img_count = g.get("img_per_piece", 4)

                    # Pad/trim sub-prompts to match img_count
                    if not sub_prompts:
                        sub_prompts = [i_prompt_text] * img_count
                    elif len(sub_prompts) < img_count:
                        sub_prompts = (sub_prompts + [sub_prompts[-1]] * img_count)[:img_count]
                    else:
                        sub_prompts = sub_prompts[:img_count]

                    attachment_tokens = []
                    failed_count = 0
                    _image_prompts: list[str] = []      # P1-4: accumulate per-image prompts
                    _image_failures: list[dict] = []    # P1-4: accumulate per-image failures

                    # Fetch 白底图 as reference image (Nanobanana only)
                    ref_images: list[bytes] = []
                    if hasattr(img_adapter, "generate_sequential"):
                        bai_di_attachments = sku_fields.get("白底图") or []
                        if bai_di_attachments:
                            first_token = bai_di_attachments[0].get("file_token") if isinstance(bai_di_attachments[0], dict) else None
                            if first_token:
                                try:
                                    ref_images = [f.download_media(first_token)]
                                    logger.info("Loaded 白底图 reference image (file_token=%s)", first_token)
                                except Exception as exc:
                                    logger.warning("Failed to download 白底图, proceeding without reference: %s", exc)

                    # Generate, upload, and save each image immediately (don't batch)
                    is_nanobanana = hasattr(img_adapter, "generate_sequential")
                    for idx in range(img_count):
                        img_filename = f"img_{idx+1:02d}.jpg"
                        # Skip images already saved locally (handles partial-failure retry)
                        if self._storage:
                            local_img = self._storage.get_content_path(plan_code, gid) / img_filename
                            if local_img.exists():
                                logger.info("Image %d already saved locally for %s, skipping", idx+1, gid)
                                attachment_tokens.append(f"__local__{img_filename}")
                                continue
                        sub_p = sub_prompts[idx]
                        combined = f"{i_prompt_text}\n\n---\n\n{sub_p}"
                        _image_prompts.append(combined)   # P1-4: record prompt for debug
                        try:
                            # Always combine master prompt + sub-prompt so consistency
                            # constraints and person description reach every image call
                            if is_nanobanana:
                                img_bytes = img_adapter.generate(combined, ref_images=ref_images or None)
                            else:
                                img_bytes = img_adapter.generate(combined)
                            logger.info("Image %d/%d generated (%d bytes) for %s", idx+1, img_count, len(img_bytes), gid)
                            token = self._upload_attachment(
                                table_content, content_record_id,
                                f"{content_code}_img{idx+1:02d}.jpg", img_bytes
                            )
                            if token:
                                attachment_tokens.append(token)
                            else:
                                failed_count += 1
                                logger.warning("Image %d upload returned no token for %s", idx+1, gid)
                            if self._storage and img_bytes:
                                try:
                                    self._storage.add_file(plan_code, gid, img_filename, img_bytes)
                                    logger.info("Image %d saved locally for %s", idx+1, gid)
                                except Exception:
                                    logger.error("LocalStorage add_file failed for img %d of %s", idx+1, gid, exc_info=True)
                        except Exception as exc:
                            failed_count += 1
                            logger.warning("Image %d failed for %s: %s", idx+1, gid, exc)
                            _image_failures.append({"index": idx, "error": str(exc)})  # P1-4
                            # Track failed index for debug block
                            _brief_g = briefs.get(gid, {})
                            if _brief_g and self._storage:
                                try:
                                    self._storage.append_failed_image_index(plan_code, gid, idx)
                                except Exception:
                                    pass

                    if not fail_reason and not attachment_tokens:
                        fail_reason = f"图片生成全部失败（{img_count}张）"
                    elif not fail_reason and failed_count > 0:
                        fail_reason = f"部分图片失败：{failed_count}/{img_count} 张未生成"

                    # P1-4: Write image_prompts + image_failures to content.json debug block
                    if self._storage and (_image_prompts or _image_failures):
                        try:
                            self._storage.update_content_debug(plan_code, gid, {
                                "image_prompts":  _image_prompts,
                                "image_failures": _image_failures,
                            })
                        except Exception:
                            logger.debug("Failed to write image debug info for %s", gid, exc_info=True)

                    # 表4: write image debug summary (摘要版, best-effort)
                    try:
                        _fail_count  = len(_image_failures)
                        _fail_idxs   = [e["index"] + 1 for e in _image_failures]
                        _prompt_prev = (_image_prompts[0][:120] + "…") if _image_prompts else ""
                        _img_debug = f"失败:{_fail_count}/{img_count}张"
                        if _fail_idxs:
                            _img_debug += f" 失败序号:{_fail_idxs}"
                        if _prompt_prev:
                            _img_debug += f" Prompt摘要:{_prompt_prev}"
                        update["图片生成调试信息"] = _img_debug
                    except Exception:
                        pass
                else:
                    # --- Generate video ---
                    try:
                        vid_adapter = build_video_adapter(self._model_params, cfg["video_model_name"])
                        vid_bytes = vid_adapter.generate(
                            i_prompt_text,
                            min_seconds=g.get("vid_min_sec", 5),
                            max_seconds=g.get("vid_max_sec", 12),
                        )
                        token = self._upload_attachment(
                            table_content, content_record_id,
                            f"{content_code}_video.mp4", vid_bytes,
                            field_name="生成视频",
                        )
                        if not token:
                            fail_reason = "视频已生成但上传至飞书失败"
                        # Save video locally regardless of Feishu upload result
                        if self._storage and vid_bytes:
                            try:
                                self._storage.add_file(plan_code, gid, "video.mp4", vid_bytes)
                            except Exception:
                                logger.warning("LocalStorage add_file failed for video", exc_info=True)
                    except Exception as exc:
                        fail_reason = f"视频生成失败: {exc}"

            if fail_reason:
                update["生成状态"] = "生成失败"
                update["失败原因"] = fail_reason
            else:
                update["生成状态"] = "已生成"

            # Write observability fields to 表4 (best-effort, non-blocking)
            brief = briefs.get(gid, {})
            if brief:
                try:
                    ca = brief.get("consistency_anchor", {})
                    brief_summary = " | ".join(x for x in [
                        brief.get("persona_label", ""),
                        brief.get("scene_mode", ""),
                        brief.get("narrative_angle", ""),
                    ] if x)
                    update["创意包摘要"]    = brief_summary or "(无)"
                    update["命中策略ID"]    = brief.get("strategy_id", "")
                    update["命中场景ID"]    = brief.get("scene_id", "")
                    update["命中人设ID"]    = brief.get("persona_id", "")
                    update["命中ShotPlanID"] = brief.get("shotplan_id", "")
                    update["标题句式"]      = brief.get("title_pattern", "")
                    update["叙事角度"]      = brief.get("narrative_angle", "")
                    update["组内一致性锚点"] = ca.get("person", "")
                except Exception:
                    logger.debug("Failed to build observability fields for 表4, group=%s", gid, exc_info=True)

            f.update_record(table_content, content_record_id, update)
            db.update_content_status(
                content_code,
                gen_status="生成失败" if fail_reason else "已生成",
            )

            # Mark prompts as 已使用
            for pr in [c_pr, i_pr]:
                if pr:
                    try:
                        f.update_record(table_prompt, pr["prompt_record_id"], {"状态": "已使用"})
                    except Exception:
                        pass

        return content_record_ids

    # ------------------------------------------------------------------
    # Upload attachment helper
    # ------------------------------------------------------------------

    def _upload_attachment(
        self, table_id: str, record_id: str, filename: str, data: bytes,
        field_name: str = "生成图片"
    ) -> str | None:
        """
        Upload bytes as a Bitable attachment.

        Flow:
          1. Upload file via drive.v1 UploadAllMediaRequest
             (parent_type="bitable_file", parent_node=base_token)
          2. Get file_token from response
          3. Append {"file_token": ..., "name": ...} to the target attachment field
        Returns the file_token on success, None on failure.
        """
        import io
        try:
            from lark_oapi.api.drive.v1 import (
                UploadAllMediaRequest,
                UploadAllMediaRequestBody,
            )

            body = (
                UploadAllMediaRequestBody.builder()
                .parent_type("bitable_file")
                .parent_node(self._feishu.base_token)
                .file_name(filename)
                .size(len(data))
                .file(io.BytesIO(data))
                .build()
            )
            resp = self._feishu._client.drive.v1.media.upload_all(
                UploadAllMediaRequest.builder().request_body(body).build()
            )
            if not resp.success():
                logger.warning(
                    "drive upload failed [%s]: %s (file=%s)", resp.code, resp.msg, filename
                )
                return None

            file_token = resp.data.file_token
            logger.debug("Uploaded %s → file_token=%s", filename, file_token)

            # Append token to record's attachment field
            rec = self._feishu.get_record(table_id, record_id)
            existing = rec["fields"].get(field_name) or []
            existing.append({"file_token": file_token, "name": filename})
            self._feishu.update_record(table_id, record_id, {field_name: existing})
            return file_token

        except Exception as exc:
            logger.warning("Attachment upload exception for %s: %s", filename, exc)
            return None


    # ------------------------------------------------------------------
    # Parse text result into title / body / tags
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_text_result(text: str) -> tuple[str, str, str]:
        import re
        sections: dict[str, str] = {}
        current = None
        lines = text.split("\n")
        buf: list[str] = []
        for line in lines:
            m = re.match(r'[【\[]?(标题|正文|标签)[】\]]?[：:]*', line.strip())
            if m:
                if current and buf:
                    sections[current] = "\n".join(buf).strip()
                current = m.group(1)
                buf = []
            elif current:
                buf.append(line)
        if current and buf:
            sections[current] = "\n".join(buf).strip()
        return sections.get("标题", ""), sections.get("正文", ""), sections.get("标签", "")

    # ------------------------------------------------------------------
    # Field value helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _text_field(value: str) -> list[dict]:
        """Feishu rich-text field format."""
        return [{"type": "text", "text": value}]
