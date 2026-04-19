"""
check_nanobanana.py — 测试 runapi.co Gemini 图片接口是否恢复。
恢复时发飞书群消息通知，否则静默退出。

用法: python check_nanobanana.py
退出码: 0=恢复正常, 1=仍不可用
"""
import os
import sys
import time
from pathlib import Path
from datetime import datetime

# Load .env
env_path = Path(__file__).parent.parent / "middleware" / ".env"
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).parent.parent / "middleware"))

import httpx
from adapters.feishu import FeishuClient

API_KEY = os.environ.get("NANOBANANA_API_KEY", "")
BASE_URL = os.environ.get("NANOBANANA_BASE_URL", "https://runapi.co/v1").rstrip("/")
MODEL = os.environ.get("NANOBANANA_MODEL", "gemini-3.1-flash-image-preview")
URL = f"{BASE_URL}/models/{MODEL}:generateContent"
CHAT_ID = "oc_2a18512a232920019a216346de01379a"
TIMEOUT = float(os.environ.get("NANOBANANA_CHECK_TIMEOUT", "60"))

LOG_FILE  = Path(__file__).parent.parent / "logs" / "nanobanana_check.log"

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def check() -> bool:
    """Returns True if API is back to normal."""
    if not API_KEY:
        log("NANOBANANA_API_KEY 未配置")
        return False
    try:
        payload = {
            "contents": [{"role": "user", "parts": [{"text": "a red apple"}]}],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
                "imageConfig": {"aspectRatio": "1:1", "imageSize": "1K"},
            },
        }
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        }
        t0 = time.time()
        with httpx.Client(timeout=TIMEOUT) as client:
            resp = client.post(URL, headers=headers, json=payload)
        elapsed = time.time() - t0
        status = resp.status_code
        log(f"HTTP {status} ({elapsed:.1f}s)")
        return status == 200
    except Exception as exc:
        log(f"Error: {exc}")
        return False

def notify_feishu(msg: str):
    try:
        f = FeishuClient(
            app_id=os.environ["LARK_APP_ID"],
            app_secret=os.environ["LARK_APP_SECRET"],
            base_token=os.environ["LARK_BASE_TOKEN"],
        )
        f.send_group_text(CHAT_ID, msg)
        log("飞书通知已发送")
    except Exception as exc:
        log(f"飞书通知失败: {exc}")

if __name__ == "__main__":
    log("检测 runapi.co/Gemini 接口...")
    if check():
        msg = (
            "✅ runapi.co/Gemini 图片接口已恢复正常！\n"
            "可将飞书规划表的图片模型改回 Nanobanana 2 并重新触发任务。\n"
            f"检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        log("接口恢复！发送通知...")
        notify_feishu(msg)
        sys.exit(0)
    else:
        log("接口仍不可用，等待下次检测")
        sys.exit(1)
