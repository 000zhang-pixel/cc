"""
MaterialAnalysisHandler — when 表6 触发分析=是,
analyzes the material using AI and writes results back.

Analysis steps:
  1. Parse source platform from URL
  2. AI text analysis → content form, category, type, title formula, etc.
  3. AI image analysis (if attachment present) → composition, tone, props
  4. Write all results + 分析状态=已完成
"""
import logging
import re
from datetime import datetime

from adapters.feishu import FeishuClient
from adapters.ai_models import TextModelAdapter, build_text_adapter
from core.task import Task

logger = logging.getLogger(__name__)


class MaterialAnalysisHandler:
    def __init__(self, feishu: FeishuClient, tables: dict, model_params: dict):
        self._feishu = feishu
        self._tables = tables
        self._model_params = model_params

    def __call__(self, task: Task):
        record_id = task.record_id
        table_material = self._tables["material"]
        f = self._feishu

        try:
            self._run(record_id)
        except Exception as exc:
            logger.exception("MaterialAnalysis failed for record %s", record_id)
            f.update_record(table_material, record_id, {
                "分析状态": "分析失败",
            })

    def _run(self, record_id: str):
        f = self._feishu
        table_material = self._tables["material"]

        rec = f.get_record(table_material, record_id)

        url = f.get_text(rec, "素材链接").strip()
        title = f.get_text(rec, "原始标题").strip()
        body = f.get_text(rec, "原始正文").strip()
        has_attachment = bool(rec["fields"].get("素材附件"))

        # 1. Identify source platform from URL
        platform = self._detect_platform(url)

        # 2. Use default text model (first available provider)
        text_model_name = list(
            self._model_params["text_model"]["providers"].keys()
        )[0]
        adapter = build_text_adapter(text_model_name, self._model_params)

        # 3. Text analysis
        text_analysis = self._analyze_text(adapter, title, body)

        # 4. Image analysis (placeholder — real implementation needs attachment download)
        image_analysis: dict = {}
        if has_attachment:
            image_analysis = self._analyze_image_placeholder()

        # 5. Write results
        now_ms = int(datetime.now().timestamp() * 1000)
        update: dict = {
            "来源平台": platform,
            "分析状态": "已完成",
            "收录时间": now_ms,
        }

        # Text analysis fields
        field_map = {
            "内容形态": "content_form",
            "品类": "category",
            "内容类型": "content_type",
            "标题公式": "title_formula",
            "正文结构": "body_structure",
            "卖点提炼方式": "selling_point_style",
            "标签组合策略": "tag_strategy",
        }
        for feishu_field, key in field_map.items():
            val = text_analysis.get(key, "")
            if val:
                if feishu_field in ("内容形态", "品类", "内容类型", "卖点提炼方式"):
                    update[feishu_field] = val
                else:
                    update[feishu_field] = val

        # Emotion triggers — multi-select
        emotions = text_analysis.get("emotions", [])
        if emotions:
            update["情绪触发点"] = emotions

        # Image analysis fields
        for feishu_field, key in [("构图风格", "composition"), ("色调氛围", "tone"), ("场景道具", "props")]:
            val = image_analysis.get(key, "")
            if val:
                update[feishu_field] = val

        f.update_record(table_material, record_id, update)
        logger.info("MaterialAnalysis complete for record %s (platform=%s)", record_id, platform)

    # ------------------------------------------------------------------

    @staticmethod
    def _detect_platform(url: str) -> str:
        if "dewu" in url or "poizon" in url:
            return "得物"
        if "xiaohongshu" in url or "xhslink" in url or "rednote" in url:
            return "小红书"
        return "其他"

    def _analyze_text(self, adapter: TextModelAdapter, title: str, body: str) -> dict:
        system = (
            "你是一名电商内容分析专家，擅长分析种草内容的结构和技巧。"
            "请严格按照JSON格式输出分析结果，不要有其他文字。"
        )
        user = (
            f"请分析以下电商种草内容，输出JSON格式分析结果：\n\n"
            f"标题：{title}\n\n"
            f"正文：{body}\n\n"
            "输出格式（严格JSON，所有字段必须有值）：\n"
            "{\n"
            '  "content_form": "单图文|图文|视频",\n'
            '  "category": "手机壳|手机挂架|通用",\n'
            '  "content_type": "种草推荐|好物分享|深度测评|对比测评|穿搭搭配|场景展示|日常vlog|开箱|买家秀/晒单|节日/活动限定|新品发布|选购攻略/使用教程",\n'
            '  "title_formula": "痛点疑问句|数字列表|对比式|悬念式|利益点前置|其他（简要说明）",\n'
            '  "body_structure": "痛点→卖点→CTA|场景带入→产品→效果|问题→解决方案→推荐|其他（简要说明）",\n'
            '  "emotions": ["焦虑", "共鸣"],\n'
            '  "selling_point_style": "功能型|场景型|情感型",\n'
            '  "tag_strategy": "标签使用规律简要描述"\n'
            "}"
        )
        try:
            raw = adapter.complete(system, user)
            return self._parse_json(raw)
        except Exception as exc:
            logger.warning("Text analysis AI call failed: %s", exc)
            return {}

    @staticmethod
    def _parse_json(text: str) -> dict:
        import json
        # Extract first JSON object from the response
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {}

    @staticmethod
    def _analyze_image_placeholder() -> dict:
        """
        Real image analysis would require:
        1. Download the attachment from Feishu (needs drive API)
        2. Send to a vision-capable model

        For now return empty — field will stay blank until this is implemented.
        """
        return {}
