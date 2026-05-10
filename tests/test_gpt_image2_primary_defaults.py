import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "middleware"))
sys.path.insert(0, str(ROOT / "admin-server"))

from schemas import CreatePlanRequest
from handlers.content_generation import ContentGenerationHandler
import scripts.tables.definitions as table_definitions


class _FakeFeishu:
    def get_option(self, record, field_name, default=""):
        value = record.get("fields", {}).get(field_name, default)
        if isinstance(value, list):
            return value[0] if value else default
        return value or default

    def get_options(self, record, field_name):
        return record.get("fields", {}).get(field_name, []) or []

    def get_number(self, record, field_name, default=0):
        value = record.get("fields", {}).get(field_name, default)
        return default if value in (None, "") else value


def test_create_plan_request_defaults_to_gpt_image2():
    req = CreatePlanRequest(
        sku_id=1,
        task_type="AI全创作",
        target_platforms=["小红书"],
    )

    assert req.image_model == "gpt-image-2"


def test_content_generation_parse_plan_config_defaults_to_gpt_image2():
    handler = ContentGenerationHandler(_FakeFeishu(), {}, {})

    cfg = handler._parse_plan_config({
        "任务类型": "AI全创作",
        "目标平台": ["小红书"],
    })

    assert cfg["image_model_name"] == "gpt-image-2"


def test_plan_table_image_model_options_include_gpt_image2():
    definitions = getattr(table_definitions, "TABLES", None) or getattr(table_definitions, "TABLE_DEFINITIONS", None)
    assert definitions is not None
    plan_table = next(item for item in definitions if item["name"] == "内容规划表")
    image_field = next(field for field in plan_table["fields"] if field["field_name"] == "图片模型")
    options = [opt["name"] for opt in image_field["property"]["options"]]

    assert "gpt-image-2" in options
