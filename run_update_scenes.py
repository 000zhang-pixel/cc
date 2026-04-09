#!/usr/bin/env python3
"""
Update SC030, SC032, SC034, SC036 in Feishu 表10 — remove 特写/微距 from
场景名称, 场景类型, 景别, 场景描述_中文, 场景基底_英文, 排除描述, 备注.
"""
import sys
sys.path.insert(0, 'D:/AI-Content-Hub')
from dotenv import load_dotenv
load_dotenv('D:/AI-Content-Hub/.env', override=False)
from middleware.core.config import load_system
from middleware.adapters.feishu import FeishuClient

cfg = load_system()
fei_cfg = cfg['feishu']
fc = FeishuClient(
    app_id=fei_cfg['app_id'],
    app_secret=fei_cfg['app_secret'],
    base_token=fei_cfg['base_token'],
)

SCENE_TABLE = 'tbliWlwiyA4sppgY'

scene_updates = {
    'SC030': {
        '场景名称': '腕部链条手持近景',
        '场景类型': '产品展示',
        '场景描述_中文': '手腕自然弯曲，手机链挂在手腕或手指上，链条垂坠形态优美，侧光营造金属光泽感，保持链条整体可见',
        '场景基底_英文': 'hand and wrist with decorative phone chain, natural drape, soft side lighting, metallic gloss, full chain visible',
        '排除描述': '不要过度PS，不要假手模型，不要黑暗背景，不要极近裁切导致链条不完整',
        '景别': '近景',
        '备注': '手机链专属核心场景：手部持机近景展示链条垂坠形态与质感，保持链条整体可见',
    },
    'SC032': {
        '场景名称': '链条光影桌面平铺',
        '场景类型': '静物展示',
        '场景描述_中文': '手机链铺展在浅色桌面或大理石台面上，利用窗边自然光制造链条阴影与光斑，完整展示链条形态，极简高级',
        '场景基底_英文': 'phone chain arranged on marble or light wood surface, natural window light creating shadows and highlights, full chain visible, minimalist luxury',
        '排除描述': '不要杂乱道具，不要人工打光过重，不要颜色过多，不要截取局部导致链条不完整',
        '景别': '近景',
        '备注': '手机链专属：产品静物平铺场景，强调材质光影美学，整条链条完整展示',
    },
    'SC034': {
        '景别': '近景',
    },
    'SC036': {
        '场景名称': '链条整体悬挂展示',
        '场景类型': '产品展示',
        '场景描述_中文': '手持或悬挂状态下展示完整链条，精准控制光线展现金属质感与工艺细节，保持链条整体形态清晰可见',
        '场景基底_英文': 'full phone chain hanging or held up, controlled lighting to reveal metallic texture and craftsmanship, complete chain visible',
        '排除描述': '不要失焦，不要过曝，不要背景干扰，不要截取导致链条不完整',
        '景别': '近景',
        '备注': '手机链专属：完整链条展示，呈现整体工艺质感，适合品质背书内容',
    },
}

print("=== Fetching scene records ===")
records = fc.list_records(SCENE_TABLE)
scene_rec_ids = {}
for r in records:
    fields = r.get('fields', {})
    code = fields.get('场景编号', '')
    rec_id = r.get('record_id', '')
    if code in scene_updates:
        scene_rec_ids[code] = rec_id
        print(f"  {code} | {rec_id} | {fields.get('场景名称', '')}")

print(f"\nFound {len(scene_rec_ids)} records to update\n")

for code, rec_id in scene_rec_ids.items():
    fields_to_update = scene_updates[code]
    try:
        result = fc.update_record(SCENE_TABLE, rec_id, fields_to_update)
        print(f"  {code} ({rec_id}): OK")
    except Exception as e:
        print(f"  {code} ({rec_id}): ERROR — {e}")

print("\n=== All done ===")
