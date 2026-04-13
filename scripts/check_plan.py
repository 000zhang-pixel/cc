"""Check current state of plan record in Feishu."""
import os, sys
from pathlib import Path

env_path = Path(__file__).parent.parent / "middleware" / ".env"
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).parent.parent / "middleware"))
from adapters.feishu import FeishuClient

f = FeishuClient(
    app_id=os.environ["LARK_APP_ID"],
    app_secret=os.environ["LARK_APP_SECRET"],
    base_token=os.environ["LARK_BASE_TOKEN"],
)
table_id = "tblDJ2hCvl7y4x5s"
record_id = "recvgDnkLM5rwj"

rec = f.get_record(table_id, record_id)
fields = rec["fields"]
print("确认执行:", f.get_option(rec, "确认执行"))
print("执行状态:", f.get_option(rec, "执行状态"))
print("图片模型:", f.get_option(rec, "图片模型"))
print("规划编号:", f.get_text(rec, "规划编号"))
