#!/usr/bin/env python3
"""
Fix SP010-SP019 shotplan records:
1. 适用内容类型: ["图文"] → real content type values matching each plan's theme
2. 适用内容形态: ["图片"] is correct (code now passes "图片") — no change needed
"""
import os, sys
sys.path.insert(0, 'D:/AI-Content-Hub')
sys.path.insert(0, 'D:/AI-Content-Hub/middleware')

# Load .env from project root (same as middleware does)
from dotenv import load_dotenv
load_dotenv('D:/AI-Content-Hub/.env', override=False)

from middleware.adapters.feishu import FeishuClient
from middleware.core.config import load_system

cfg = load_system()
fei_cfg = cfg['feishu']

fc = FeishuClient(
    app_id=fei_cfg['app_id'],
    app_secret=fei_cfg['app_secret'],
    base_token=fei_cfg['base_token'],
)

SHOTPLAN_TABLE = 'tbl0xCaqru1TjwzK'

# SP010-SP019 content type mapping, based on each plan's theme:
# SP010 - 穿搭点睛型    → 穿搭搭配, 种草推荐
# SP011 - 工艺品质型    → 深度测评, 场景展示
# SP012 - 拆箱仪式感型  → 开箱, 好物分享
# SP013 - 对比测评型    → 对比测评, 选购攻略/使用教程
# SP014 - 日常生活化型  → 日常vlog, 场景展示
# SP015 - 多款展示型    → 穿搭搭配, 好物分享
# SP016 - 礼物情感型    → 节日/活动限定, 种草推荐
# SP017 - 叠戴搭配型    → 穿搭搭配, 种草推荐
# SP018 - 美学平铺型    → 种草推荐, 好物分享
# SP019 - 校园青春型    → 场景展示, 种草推荐

SP_CONTENT_TYPES = {
    'SP010': ['穿搭搭配', '种草推荐'],
    'SP011': ['深度测评', '场景展示'],
    'SP012': ['开箱', '好物分享'],
    'SP013': ['对比测评', '选购攻略/使用教程'],
    'SP014': ['日常vlog', '场景展示'],
    'SP015': ['穿搭搭配', '好物分享'],
    'SP016': ['节日/活动限定', '种草推荐'],
    'SP017': ['穿搭搭配', '种草推荐'],
    'SP018': ['种草推荐', '好物分享'],
    'SP019': ['场景展示', '种草推荐'],
}

print("=== Fetching shotplan records ===")
records = fc.list_records(SHOTPLAN_TABLE)

plan_rec_ids = {}
for r in records:
    fields = r.get('fields', {})
    code = fields.get('方案编号', '')
    rec_id = r.get('record_id', '')
    if code in SP_CONTENT_TYPES:
        plan_rec_ids[code] = rec_id
        current_ct = fields.get('适用内容类型', '')
        current_form = fields.get('适用内容形态', '')
        print(f"  {code} | {rec_id} | 内容类型={current_ct!r} | 内容形态={current_form!r}")

print()
print("=== Updating 适用内容类型 for SP010-SP019 ===")
for code, rec_id in plan_rec_ids.items():
    new_types = SP_CONTENT_TYPES[code]
    try:
        result = fc.update_record(SHOTPLAN_TABLE, rec_id, {'适用内容类型': new_types})
        print(f"  {code} ({rec_id}): {new_types} → OK")
    except Exception as e:
        print(f"  {code} ({rec_id}): ERROR — {e}")

print("\n=== All done ===")
