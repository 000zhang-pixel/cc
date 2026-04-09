"""
ContentGenerationHandler — processes a 表2 内容规划表 record.

Full pipeline:
  1. Validate SKU completeness & 上架状态
  2. Read config fields from 表2
  3. Fetch TOP N tags from 表7 by platform + category
  4. For each img/vid group: create 表3 Prompt records
  5. Call Prompt engine to fill Prompts in 表3
  6. Call AI APIs to generate content
  7. Write results to 表4 内容生成表
  8. Update 表2 execution status
"""
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
        scene_assignments = self._assign_scenes(groups, sku_fields, plan_code)

        # --- 6. Create Prompt records in 表3 ---
        prompt_records = self._create_prompt_records(record_id, groups, plan_fields, sku_fields, cfg)

        # --- 7. Generate Prompts via Prompt engine ---
        text_adapter = build_text_adapter(cfg["text_model_name"], self._model_params)
        self._fill_prompts(prompt_records, sku_fields, cfg, tags, text_adapter, scene_assignments)

        # --- 8. Mark all prompts 已确认 ---
        for pr in prompt_records:
            f.update_record(self._tables["prompt"], pr["prompt_record_id"], {"状态": "已确认"})

        # --- 9. Generate content (call AI APIs) ---
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
        form_matched = [
            r for r in records
            if content_form in (self._feishu.get_options(r, "适用内容形态") or [])
        ]
        candidates = form_matched if form_matched else records
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
        self, groups: list[dict], sku_fields: dict, plan_code: str
    ) -> dict:
        """
        Assign one distinct Scene per group (best-effort round-robin if scenes < groups).
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

        # Random start offset so the first group doesn't always get the top-weighted scene
        start = random.randrange(len(pool))
        assignments: dict = {}
        for i, g in enumerate(groups):
            scene = pool[(start + i) % len(pool)]
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
            }

        if self._storage:
            try:
                self._storage.update_plan(plan_code, {"scene_assignments": assignments})
            except Exception:
                logger.warning("_assign_scenes: failed to write plan.json", exc_info=True)

        return assignments

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
    ) -> tuple[str, str]:
        """Build (system_prompt, user_prompt) using a Strategy record from 表8."""
        f = self._feishu
        system = f.get_text(strategy, "系统提示词前缀").strip() or (
            "你是一名专业的电商种草文案策划，擅长为得物/小红书平台创作高转化率内容。"
        )
        nodes_raw = f.get_text(strategy, "文案叙事节点").strip()
        try:
            nodes = json.loads(nodes_raw) if nodes_raw else []
        except json.JSONDecodeError:
            nodes = []

        if nodes:
            node_lines = "\n".join(
                f"{n['index']}. 【{n.get('zh', n.get('node', ''))}】{n.get('guidance', '')}"
                for n in nodes
            )
        else:
            node_lines = "（按内容类型的常规结构展开）"

        platform_str = "、".join(platforms)
        word_count = "50-200字" if group_type == "vid" else "300-800字"

        # Build scene context block if scene info is available
        scene_block = ""
        if scene:
            scene_desc = scene.get("场景描述_中文", "")
            scene_style = scene.get("风格基调词", "")
            parts = [p for p in [scene_desc, scene_style] if p]
            if parts:
                scene_block = f"\n\n场景设定（请将内容植入此场景氛围中）：{'｜'.join(parts)}"

        # Title guidance from strategy record (optional field)
        title_guide = f.get_text(strategy, "标题写作指南").strip()
        title_instruction = (
            f"<标题（≤20字）>\n参考方向：{title_guide}" if title_guide else "<标题（≤20字）>"
        )

        user = (
            f"请为以下产品生成「{content_type}」类型的完整内容（标题+正文）。\n\n"
            f"目标平台：{platform_str}\n"
            f"内容类型：{content_type}\n\n"
            f"产品信息：\n{sku_summary}{scene_block}\n\n"
            f"叙事结构（请按顺序展开）：\n{node_lines}\n\n"
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
        self, strategy: dict | None, sku_fields: dict, scene: dict
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

        # Person fields from scene record
        person_type = scene.get("人物类型", "").strip()
        gender      = scene.get("性别倾向", "").strip()
        age_range   = scene.get("年龄段", "").strip()
        appearance  = scene.get("外貌风格", "").strip()
        posture     = scene.get("姿态倾向", "").strip()

        # Technical parameter fields (single-select, may be empty)
        tech_params = [
            scene.get(k, "").strip() for k in self._TECH_PARAM_KEYS if scene.get(k, "").strip()
        ]

        emotion_zh = f.get_option(strategy, "情绪基调") if strategy else ""
        mood_zh    = self._EMOTION_ZH.get(emotion_zh, "自然真实")

        # --- build core sections (always included) ---
        core_parts = [
            f"【产品】{product_desc}",
            "",
            f"【场景】{scene_zh}" if scene_zh else "",
            f"风格：{style_words}。情绪：{mood_zh}。" if style_words else f"情绪：{mood_zh}。",
        ]

        person_part: list[str] = []
        if person_type and person_type not in ("无人物",):
            person_attrs = [x for x in [gender, age_range, appearance, posture] if x]
            person_line = person_type
            if person_attrs:
                person_line += "，" + "，".join(person_attrs)
            person_part = ["", f"【人物】{person_line}"]

        consistency_part = [
            "",
            "【一致性要求】",
            "- 所有图片保持完全相同的产品外观（颜色、材质、细节）",
            "- 同一人物（同一人、同套服装、同款发型）",
            "- 统一光线和色彩风格贯穿始终",
        ]

        # Optional sections, dropped first when over budget
        exclude_part = ["", f"【避免】{exclude}"] if exclude else []
        tech_part    = ["", f"【技术参数】{'、'.join(tech_params)}"] if tech_params else []

        def _join(parts_list: list[list[str]]) -> str:
            merged = []
            for p in parts_list:
                merged.extend(p)
            return "\n".join(x for x in merged if x is not None)

        # Try full prompt first
        full = _join([core_parts, person_part, tech_part, consistency_part, exclude_part])
        if len(full) <= self._MASTER_PROMPT_MAX:
            return full

        # Drop tech params
        reduced = _join([core_parts, person_part, consistency_part, exclude_part])
        if len(reduced) <= self._MASTER_PROMPT_MAX:
            return reduced

        # Trim exclude to first clause (up to first Chinese comma/period)
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
            core_parts[2] = f"【场景】{scene_zh[:60]}"
        return _join([core_parts, person_part, consistency_part])

    def _build_image_sub_prompts(
        self, shotplan: dict | None, scene: dict, img_count: int
    ) -> list[str]:
        """Build per-shot sub-prompts in Chinese from ShotPlan + Scene."""
        f = self._feishu
        scene_zh = scene.get("场景描述_中文", "").strip()
        scene_suffix = f"，{scene_zh}" if scene_zh else ""

        # Build person suffix for shots that should include real people
        person_type = scene.get("人物类型", "").strip()
        _no_person_types = {"无人物", "纯产品", ""}
        if person_type and person_type not in _no_person_types:
            gender    = scene.get("性别倾向", "").strip()
            age       = scene.get("年龄段", "").strip()
            appear    = scene.get("外貌风格", "").strip()
            posture   = scene.get("姿态倾向", "").strip()
            person_attrs = "、".join(x for x in [gender, age, appear, posture] if x)
            person_suffix = f"，画面中有{person_type}" + (f"（{person_attrs}）" if person_attrs else "")
            # Consistency anchor: all shots in the same group must feature the identical person
            consistency_note = (
                "，【一致性约束】本组所有图片为同一人物："
                "保持完全相同的服装（颜色/款式/细节）、相同发型、相同面孔特征，禁止更换服装或人物"
            )
        else:
            person_suffix = ""
            consistency_note = ""

        def _default_shot(idx: int) -> str:
            role = self._DEFAULT_SHOT_ROLES[idx % len(self._DEFAULT_SHOT_ROLES)]
            return f"第{idx + 1}张：{role}{scene_suffix}{person_suffix}{consistency_note}"

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

                zh_text = zh_text.replace("{scene_description}", scene_zh)
                if zh_text:
                    result.append(f"第{i + 1}张：{zh_text}{scene_suffix}{person_suffix}{consistency_note}")
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
    ):
        f = self._feishu
        table_prompt = self._tables["prompt"]

        sku_summary = self._build_sku_summary(sku_fields)
        tag_str = " ".join(tags)
        category = f.get_option({"fields": sku_fields}, "品类")
        if scene_assignments is None:
            scene_assignments = {}

        for pr in prompt_records:
            g = pr["group"]
            suffix = pr["suffix"]
            prompt_type = pr["prompt_type"]
            record_id = pr["prompt_record_id"]
            content_type = g["content_type"]
            platforms = cfg["platforms"]
            gid = g["group_id"]

            if suffix == "C":
                # Text/copy prompt — use Strategy if available, else hardcoded
                scene = scene_assignments.get(gid, {})
                strategy = self._lookup_strategy(
                    content_type, platforms[0] if platforms else "", category
                )
                if strategy:
                    _system_prompt, user_prompt = self._build_text_prompts_from_strategy(
                        strategy, sku_summary, platforms, content_type, g["type"], scene=scene
                    )
                    # Store the prompt instructions only; actual AI content generation
                    # happens in _generate_content() (step 9) to keep 表3 prompt-only.
                    f.update_record(table_prompt, record_id, {"总Prompt": user_prompt})
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
                    master = self._build_image_master_prompt(strategy, sku_fields, scene)
                    subs = self._build_image_sub_prompts(shotplan, scene, img_count)
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

        for g in groups:
            gid = g["group_id"]
            content_code = f"{plan_code}_{gid}"
            is_img = g["type"] == "img"

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

            update: dict = {}
            fail_reason = None

            if task_type in ("AI全创作", "图片实拍+AI文案", "视频实拍+AI文案"):
                # --- Generate text (title + body + tags) ---
                try:
                    text_adapter = build_text_adapter(cfg["text_model_name"], self._model_params)
                    text_result = text_adapter.complete(
                        "你是专业的电商种草文案撰写者，请严格按照Prompt要求生成内容。"
                        "输出格式：\n【标题】\n<标题>\n\n【正文】\n<正文>",
                        c_prompt_text,
                    )
                    title, body, _ = self._parse_text_result(text_result)
                    tags_text = " ".join(tags) if tags else ""
                    update["标题"] = title
                    update["正文"] = body
                    update["标签"] = tags_text
                    # Save text locally
                    if self._storage:
                        try:
                            self._storage.update_text(plan_code, gid, title, body, tags_text)
                        except Exception:
                            logger.warning("LocalStorage update_text failed for %s", gid, exc_info=True)
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
                        sub_p = sub_prompts[idx]
                        try:
                            if is_nanobanana:
                                combined = f"{i_prompt_text}\n\n---\n\n{sub_p}"
                                img_bytes = img_adapter.generate(combined, ref_images=ref_images or None)
                            else:
                                img_bytes = img_adapter.generate(sub_p)
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
                                    self._storage.add_file(plan_code, gid, f"img_{idx+1:02d}.jpg", img_bytes)
                                    logger.info("Image %d saved locally for %s", idx+1, gid)
                                except Exception:
                                    logger.error("LocalStorage add_file failed for img %d of %s", idx+1, gid, exc_info=True)
                        except Exception as exc:
                            failed_count += 1
                            logger.warning("Image %d failed for %s: %s", idx+1, gid, exc)

                    if not fail_reason and not attachment_tokens:
                        fail_reason = f"图片生成全部失败（{img_count}张）"
                    elif not fail_reason and failed_count > 0:
                        update["失败原因"] = f"部分图片失败：{failed_count}/{img_count} 张未生成"
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
