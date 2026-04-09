#!/usr/bin/env python3
"""
Push corrected SP010-SP019 角色序列 (no 特写/微距) to Feishu 表9.
Uses middleware config loader instead of raw os.environ.
"""
import sys, json
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

SHOTPLAN_TABLE = 'tbl0xCaqru1TjwzK'

shotplan_sequences = {
    'SP010': json.dumps([
        {"index": 1, "shot": "首图人物全身", "desc": "模特全身出镜，手持手机，手机链自然垂落；穿搭完整，链子颜色与服装呼应；室内/户外自然光"},
        {"index": 2, "shot": "人物上半身持机", "desc": "模特上半身，手机握持姿势，链子在手间自然摇曳，重点展示链子与整体造型的协调感"},
        {"index": 3, "shot": "穿搭搭配细节", "desc": "服装局部+链子入镜，展示穿搭点睛效果，色彩和谐感；链子保持自然垂落状态"},
        {"index": 4, "shot": "中景持机展示", "desc": "模特手持手机中景，手机链自然下垂，重点展示链子整体垂坠感与材质光泽，避免极近镜头"},
        {"index": 5, "shot": "生活场景应用", "desc": "模特在咖啡馆/街头等真实场景中自然使用手机，链子随动作自然入镜"},
        {"index": 6, "shot": "全景场景收尾", "desc": "模特与场景的全景镜头，链子作为造型亮点自然融入画面，展示整体时尚感"}
    ], ensure_ascii=False),
    'SP011': json.dumps([
        {"index": 1, "shot": "首图人物手部持机", "desc": "模特手部出镜，手握手机，手机链绕手腕或自然垂落；背景干净，展示手与链子的整体品质感"},
        {"index": 2, "shot": "人物上半身持机", "desc": "模特半身，手持手机，链子自然下垂展示整体品质感和佩戴状态"},
        {"index": 3, "shot": "链子悬挂中景", "desc": "手机链悬挂垂落，中景展示整体链型、金属光泽和垂坠质感；保持完整链条可见而非极近截取"},
        {"index": 4, "shot": "白背景整体平铺", "desc": "链子平铺在纯色/大理石背景上，完整展示整体链型设计，清晰呈现整条链子的造型"},
        {"index": 5, "shot": "人物持机对比", "desc": "模特手持不同材质/款式的手机链，中景对比展示链条整体外观和搭配效果"},
        {"index": 6, "shot": "整体佩戴感", "desc": "模特完整持机姿势，展示链子在真实使用状态下的垂坠感和品质感"}
    ], ensure_ascii=False),
    'SP012': json.dumps([
        {"index": 1, "shot": "首图人物拆箱", "desc": "模特手部出镜，正在打开精致礼盒，链子初露一角；制造惊喜感和礼物仪式感"},
        {"index": 2, "shot": "取出链子展示", "desc": "模特双手捧出手机链，链子在手心完整展示，呈现整条链子的形态和质感"},
        {"index": 3, "shot": "包装全貌", "desc": "礼盒+链子+配件完整展示，包装精美度、品牌感"},
        {"index": 4, "shot": "安装过程人手", "desc": "模特将链子连接到手机的过程，手部中景，展示安装简便性和使用状态"},
        {"index": 5, "shot": "佩戴成品效果", "desc": "链子安装后，模特手持手机全貌，展示开箱后的使用效果"},
        {"index": 6, "shot": "整体使用场景", "desc": "模特手持挂好链子的手机，在真实场景中展示成品效果，链子自然垂落入镜"}
    ], ensure_ascii=False),
    'SP013': json.dumps([
        {"index": 1, "shot": "首图人物对比持机", "desc": "模特双手分别握两款不同手机链的手机，直观对比；构图清晰，差异明显"},
        {"index": 2, "shot": "人物半身展示", "desc": "模特半身，展示当前测评款链子的佩戴整体效果"},
        {"index": 3, "shot": "两款平铺对比", "desc": "两款链子并排平铺，相同背景下对比材质、粗细、长度、设计风格"},
        {"index": 4, "shot": "人物持机对比展示", "desc": "同一模特/相似角度，分别展示两款链子挂在手机上的整体外观，中景对比，保持链子完整可见"},
        {"index": 5, "shot": "佩戴效果对比", "desc": "同一模特/相似角度，分别展示两款链子的佩戴效果"},
        {"index": 6, "shot": "最终推荐人物", "desc": "模特手持推荐款，给出明确推荐姿态，增强说服力"}
    ], ensure_ascii=False),
    'SP014': json.dumps([
        {"index": 1, "shot": "首图人物日常场景", "desc": "模特在真实日常场景（咖啡馆/书桌/街头），自然使用手机，链子在画面中自然呈现；非摆拍感"},
        {"index": 2, "shot": "通勤场景", "desc": "地铁/公交/步行中，模特手机链自然摇动，展示日常携带的实用美感"},
        {"index": 3, "shot": "工作场景", "desc": "桌面场景，链子随手机放在桌上或握在手中，轻松自然"},
        {"index": 4, "shot": "休闲场景", "desc": "购物/逛街/约会场景，链子与整体日常装扮的搭配"},
        {"index": 5, "shot": "链子自然状态", "desc": "日常使用后的链子自然垂落状态，光泽真实，整体链条可见，不做极近放大"},
        {"index": 6, "shot": "人物总结镜头", "desc": "模特最后一个自然的拿机姿势，链子清晰入镜，真实感收尾"}
    ], ensure_ascii=False),
    'SP015': json.dumps([
        {"index": 1, "shot": "首图人物多款展示", "desc": "模特全身或半身，展示当天穿搭+手机链，作为多款展示的开场人物镜头"},
        {"index": 2, "shot": "款式一人物展示", "desc": "模特搭配第一款链子，展示整体穿搭效果，突出该款与服装风格的匹配"},
        {"index": 3, "shot": "款式二人物展示", "desc": "模特更换第二款链子，展示不同风格搭配（如：换了更休闲的装束）"},
        {"index": 4, "shot": "款式三人物展示", "desc": "模特搭配第三款，展示不同场景/风格的搭配可能性"},
        {"index": 5, "shot": "多款平铺汇总", "desc": "三款链子一起平铺展示，便于选购对比"},
        {"index": 6, "shot": "模特最爱推荐", "desc": "模特手持最推荐款，给出个人偏好建议"}
    ], ensure_ascii=False),
    'SP016': json.dumps([
        {"index": 1, "shot": "首图人物送礼场景", "desc": "模特（送礼方）手持精美礼盒，或两人之间的递接礼物瞬间；营造温馨礼物氛围"},
        {"index": 2, "shot": "收礼人惊喜反应", "desc": "收礼人打开礼盒发现链子的惊喜表情/动作（可只拍手部和部分面部）"},
        {"index": 3, "shot": "礼盒包装展示", "desc": "精美礼盒+链子+赠品（如贺卡）完整展示，强调送礼仪式感"},
        {"index": 4, "shot": "礼盒链子中景展示", "desc": "手机链从礼盒中取出，中景展示链子整体样貌与礼盒包装，链条完整可见"},
        {"index": 5, "shot": "使用效果人物", "desc": "收礼人将链子装上手机，展示佩戴效果，表情满意"},
        {"index": 6, "shot": "温馨合影/单人", "desc": "收礼人手持装好链子的手机，展示最终礼物使用效果"}
    ], ensure_ascii=False),
    'SP017': json.dumps([
        {"index": 1, "shot": "首图人物叠戴全貌", "desc": "模特手腕/手部出镜，展示手机链+手链/手环的叠戴整体效果；构图美观，层次丰富"},
        {"index": 2, "shot": "叠戴整体近景", "desc": "手腕近景展示手机链与手链/手环的叠戴整体效果，层次丰富，保持链条整体可见"},
        {"index": 3, "shot": "分层展示", "desc": "逐步叠加的过程镜头：先戴手链，再加手机链，展示叠搭逻辑"},
        {"index": 4, "shot": "不同叠戴组合", "desc": "展示2-3种叠戴方案：金+银、繁+简、粗+细等对比"},
        {"index": 5, "shot": "链子平铺组合", "desc": "手机链+常见搭配手链的平铺展示，提供搭配参考"},
        {"index": 6, "shot": "人物整体造型", "desc": "模特半身，展示叠戴效果在整体穿搭中的层次感"}
    ], ensure_ascii=False),
    'SP018': json.dumps([
        {"index": 1, "shot": "首图人物手部平铺引导", "desc": "模特手自然放在平铺背景旁，手机链摆在手边，人手入镜赋予平铺温度感；非纯静物"},
        {"index": 2, "shot": "美学平铺主图", "desc": "手机链与搭配道具（花瓣/复古小物/香薰/胶卷）精心平铺，构图美观，色调统一"},
        {"index": 3, "shot": "整体平铺展示", "desc": "完整链条平铺，全链可见，展示整体链型、材质光泽和工艺；避免局部放大截取"},
        {"index": 4, "shot": "人物手持展示", "desc": "模特从平铺中拿起链子，手持展示链子垂坠效果"},
        {"index": 5, "shot": "佩戴效果人物", "desc": "模特将链子连接手机，展示从平铺美学到实际使用的过渡"},
        {"index": 6, "shot": "场景整体氛围", "desc": "稍微拉远，展示平铺道具+模特手的整体构图美感"}
    ], ensure_ascii=False),
    'SP019': json.dumps([
        {"index": 1, "shot": "首图校园人物全身", "desc": "模特穿校园日常装（卫衣/运动/学院风），手持手机，链子清晰可见；校园场景背景（走廊/操场/图书馆门口）"},
        {"index": 2, "shot": "背包+链子组合", "desc": "模特背着书包，手机链与书包同框，展示校园场景中链子的日常搭配"},
        {"index": 3, "shot": "课桌场景", "desc": "课桌上手机+链子自然摆放，教材/笔记本入镜，展示校园使用场景"},
        {"index": 4, "shot": "户外校园场景", "desc": "操场/草坪/走廊，模特自然拿机，链子随动作摇动，青春动感"},
        {"index": 5, "shot": "人物+校园元素组合", "desc": "模特手持手机，链子与校园元素（书包/课本/校徽贴纸）自然同框，突出校园专属氛围"},
        {"index": 6, "shot": "闺蜜/同学场景", "desc": "两个人一起展示（如有），或模特独自摆出青春感十足的姿势，活力收尾"}
    ], ensure_ascii=False),
}

print("=== Fetching shotplan records ===")
records = fc.list_records(SHOTPLAN_TABLE)
plan_rec_ids = {}
for r in records:
    fields = r.get('fields', {})
    code = fields.get('方案编号', '')
    rec_id = r.get('record_id', '')
    if code in shotplan_sequences:
        plan_rec_ids[code] = rec_id
        print(f"  {code} | {rec_id}")

print(f"\nFound {len(plan_rec_ids)} records to update")
print()
for code, rec_id in plan_rec_ids.items():
    fields_to_update = {
        '是否启用': '启用',
        '角色序列': shotplan_sequences[code],
    }
    try:
        result = fc.update_record(SHOTPLAN_TABLE, rec_id, fields_to_update)
        print(f"  {code} ({rec_id}): OK")
    except Exception as e:
        print(f"  {code} ({rec_id}): ERROR — {e}")

print("\n=== All done ===")
