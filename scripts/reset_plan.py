"""
reset_plan.py — Reset a plan record in Feishu for re-triggering.
Usage: python reset_plan.py <record_id> [--image-model volcengine-seedream]

Resets 执行状态 to empty and optionally updates 图片模型.
"""
import os
import sys
from pathlib import Path

# Load .env from middleware dir
env_path = Path(__file__).parent.parent / "middleware" / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).parent.parent / "middleware"))

import lark_oapi as lark
from lark_oapi.api.bitable.v1 import (
    UpdateAppTableRecordRequest,
    AppTableRecord,
)


def reset_plan(record_id: str, image_model: str | None = None):
    app_id     = os.environ["LARK_APP_ID"]
    app_secret = os.environ["LARK_APP_SECRET"]
    base_token = os.environ["LARK_BASE_TOKEN"]
    table_id   = "tblDJ2hCvl7y4x5s"  # 表2 内容规划表

    client = lark.Client.builder() \
        .app_id(app_id) \
        .app_secret(app_secret) \
        .log_level(lark.LogLevel.WARNING) \
        .build()

    fields = {"执行状态": ""}
    if image_model:
        fields["图片模型"] = image_model

    print(f"Updating record {record_id} with fields: {fields}")

    record = AppTableRecord.builder().fields(fields).build()
    resp = client.bitable.v1.app_table_record.update(
        UpdateAppTableRecordRequest.builder()
        .app_token(base_token)
        .table_id(table_id)
        .record_id(record_id)
        .request_body(record)
        .build()
    )
    if resp.success():
        print(f"OK — 执行状态 cleared, 图片模型={image_model or '(unchanged)'}")
    else:
        print(f"FAILED [{resp.code}]: {resp.msg}")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python reset_plan.py <record_id> [image_model]")
        sys.exit(1)
    record_id   = sys.argv[1]
    image_model = sys.argv[2] if len(sys.argv) > 2 else None
    reset_plan(record_id, image_model)
