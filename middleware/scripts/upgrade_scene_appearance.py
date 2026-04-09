# -*- coding: utf-8 -*-
"""
将表10中11条使用旧版外貌风格描述的有人物场景记录升级为新版描述。
旧版：年轻亚洲女性，身材比例好，精致五官，自然妆感，无过度美颜
新版：年轻亚洲女性，时尚性感，身材好曲线自然，精致五官，表情自然真实，轻妆或自然妆，无过度美颜无过度修图
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from middleware.adapters.feishu import FeishuClient
from middleware.core.config import load_system

sys_cfg = load_system()
f_cfg = sys_cfg["feishu"]
feishu = FeishuClient(f_cfg["app_id"], f_cfg["app_secret"], f_cfg["base_token"])
scene_table = f_cfg["tables"].get("scene", "")
print(f"scene_table: {scene_table}")

NEW_APPEAR = "年轻亚洲女性，时尚性感，身材好曲线自然，精致五官，表情自然真实，轻妆或自然妆，无过度美颜无过度修图"

# 11条旧描述的有人物场景：SC001,003,005,006,008,010,012,018,022,024,028
upgrades = [
    ("recvfNMIQoLFnL", "SC001", {"外貌风格": NEW_APPEAR}),
    ("recvfNMPQdrwTS", "SC003", {"外貌风格": NEW_APPEAR}),
    ("recvfNMWzqc5mU", "SC005", {"外貌风格": NEW_APPEAR}),
    ("recvfNN37l0BqL", "SC006", {"外貌风格": NEW_APPEAR}),
    ("recvfNNpvRjjgI", "SC008", {"外貌风格": NEW_APPEAR}),
    ("recvgc1C01avke", "SC010", {"外貌风格": NEW_APPEAR}),
    ("recvgc1W3cyr9R", "SC012", {"外貌风格": NEW_APPEAR}),
    ("recvgc5aLAzeho", "SC018", {"外貌风格": NEW_APPEAR}),
    ("recvgc6v9eujj5", "SC022", {"外貌风格": NEW_APPEAR}),
    ("recvgc6E4ZTtVY", "SC024", {"外貌风格": NEW_APPEAR}),
    # SC028: 28-35岁成熟 -> 改为 22-28岁，同时升级外貌
    ("recvgc8jaTLmVZ", "SC028", {"外貌风格": NEW_APPEAR, "年龄段": "22-28岁"}),
]

print(f"准备升级 {len(upgrades)} 条场景记录...")
success, failed = 0, []
for rid, code, fields in upgrades:
    try:
        feishu.update_record(scene_table, rid, fields)
        success += 1
        print(f"  OK  {code} ({rid})")
    except Exception as e:
        failed.append((code, rid, str(e)))
        print(f"  FAIL {code} ({rid}): {e}")

print(f"\n完成：成功 {success}，失败 {len(failed)}")
for code, rid, e in failed:
    print(f"  失败: {code} {rid} -- {e}")
