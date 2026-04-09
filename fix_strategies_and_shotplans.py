#!/usr/bin/env python3
"""
Fix strategy table (表8) and shotplan table (表9):
1. Delete duplicate ST021 record
2. Fix ST022-ST030: 是否启用 → '启用', write 系统提示词前缀
3. Update SP010-SP019: rewrite 角色序列 with person-first shots, fix 是否启用
"""
import os, sys, json
sys.path.insert(0, 'D:/AI-Content-Hub')

from middleware.adapters.feishu import FeishuClient

fc = FeishuClient(
    app_id=os.environ['LARK_APP_ID'],
    app_secret=os.environ['LARK_APP_SECRET'],
    base_token=os.environ['LARK_BASE_TOKEN'],
)

STRATEGY_TABLE = 'tblu2EzR78tWjYf6'
SHOTPLAN_TABLE = 'tbl0xCaqru1TjwzK'

# ── Step 1: fetch all strategy records to get names ──────────────────────────
print("=== Fetching strategy records ===")
strat_records = fc.list_records(STRATEGY_TABLE)
target_ids = {
    'ST021': None,  # good record
    'ST021_dup': 'recvgcqgJlprsD',  # duplicate to delete
    'ST022': 'recvgcqhdeo6cA',
    'ST023': 'recvgcqhVD6qRd',
    'ST024': 'recvgcqir5Vlyq',
    'ST025': 'recvgcqiUuLdb3',
    'ST026': 'recvgcqjn3fj1a',
    'ST027': 'recvgcqjRKEdlJ',
    'ST028': 'recvgcqkkoaQL4',
    'ST029': 'recvgcqkODgP6w',
    'ST030': 'recvgcqlo4kL3y',
}

strategy_info = {}
for r in strat_records:
    fields = r.get('fields', {})
    code = fields.get('策略编号', '')
    name = fields.get('策略名称', '')
    rec_id = r.get('record_id', '')
    enabled = fields.get('是否启用', '')
    prefix = fields.get('系统提示词前缀', '')
    if code in ['ST021','ST022','ST023','ST024','ST025','ST026','ST027','ST028','ST029','ST030']:
        print(f"  {code} | {rec_id} | 启用={enabled!r} | 前缀={bool(prefix)} | 名称={name}")
        strategy_info[rec_id] = {'code': code, 'name': name, 'enabled': enabled, 'prefix': prefix}

print()

# ── Step 2: Define prefixes for each strategy ────────────────────────────────
# These are all 手机链 strategies — each prefix guides the LLM on tone/angle
prefixes = {
    'ST021': """你是一位时尚穿搭博主，专注手机链配饰内容创作。
本次创作主题：穿搭点睛型手机链内容。
核心目标：展示手机链如何成为整套造型的点睛之笔，传递"一条链子让穿搭升级"的直观感受。
写作要求：
- 强调手机链对整体造型的提升感，用细节描述（颜色搭配、材质光泽、悬挂质感）
- 场景化描述：通勤、约会、逛街等具体场景中链子与服装的配合
- 语气自然亲切，像朋友分享穿搭心得
- 突出"小配饰大作用"的惊喜感""",

    'ST022': """你是一位深谙社交媒体传播规律的内容策略师，专注手机链配饰内容。
本次创作主题：社交货币展示型内容。
核心目标：让用户觉得拥有这条手机链会提升自己在社交圈中的形象和话题度。
写作要求：
- 建构"稀缺感"和"品味圈层"认知，让读者产生"有眼光的人才懂"的认同
- 引用博主、KOL、明星同款等社交认可信号
- 强调产品的"被看见"属性：背着走在路上会被人问在哪买
- 制造话题性，触发分享欲""",

    'ST023': """你是一位专注产品细节评测的内容创作者，擅长手机链材质与工艺鉴赏。
本次创作主题：工艺细节深度展示型内容。
核心目标：通过细腻的材质描述和工艺解析，建立产品的高品质感知，支撑定价。
写作要求：
- 精准描述材质：925银、黄铜镀金、钛钢、珍珠、玛瑙等的真实触感与视觉表现
- 强调工艺点：抛光工艺、焊接工艺、电镀层厚度、链环精度等
- 用专业但不晦涩的语言，让普通消费者也能感知到"贵"和"值"
- 可与快消品对比，突出耐用性与性价比""",

    'ST024': """你是一位生活方式博主，专注将配饰融入日常场景的内容创作。
本次创作主题：场景生活化沉浸型内容。
核心目标：让用户代入真实生活场景，感受手机链在日常中的实用美感。
写作要求：
- 构建具体生活场景：咖啡馆下午茶、地铁通勤、周末市集、健身后逛超市
- 描述链子在场景中的自然状态：晃动的声音、阳光下的反光、与手机握持的手感
- 强调"实用+好看"双属性，消除"配饰只是摆设"的顾虑
- 语气日记感、真实感，避免广告腔""",

    'ST025': """你是一位情感化内容创作者，专注挖掘配饰背后的情感价值。
本次创作主题：情感价值共鸣型内容。
核心目标：触发用户"买来送人/自己值得被宠爱"的情感决策。
写作要求：
- 挖掘手机链的礼物属性：生日、纪念日、闺蜜节、自我奖励
- 描述收到礼物时的惊喜感和被珍视感
- 刻画情感记忆点：第一次见面时对方挂着这条链、每次看到链子想起某人
- 语气温柔感性，制造情感共鸣，让读者自动对号入座""",

    'ST026': """你是一位专业的多平台内容运营专家，深谙得物、小红书、抖音各平台调性。
本次创作主题：平台适配爆款文案型内容。
核心目标：生成符合目标平台算法偏好和用户习惯的高互动文案。
写作要求：
- 标题需带强吸引力：疑问句、数字、情绪词（"这条链我挂了3年！""你的手机链在帮你劝退相亲对象？"）
- 正文结构清晰：问题/场景 → 产品引入 → 细节佐证 → 行动引导
- 埋互动钩子：提问、选择题、"评论区告诉我"
- 关键词自然植入，提升搜索曝光""",

    'ST027': """你是一位懂趋势的时尚内容创作者，专注手机链的潮流属性挖掘。
本次创作主题：潮流趋势引领型内容。
核心目标：将产品与当下时尚趋势绑定，制造"不买就会落伍"的紧迫感。
写作要求：
- 关联当季流行趋势：Y2K复古、多巴胺配色、暗黑系、纯欲风等
- 提及时尚博主/明星同款趋势（通用化表达）
- 强调"今年流行用手机链替代手链"等趋势认知
- 制造时间窗口感：当季、限量、季节性推荐""",

    'ST028': """你是一位产品性价比测评博主，擅长为消费者做选购决策参考。
本次创作主题：选购决策辅助型内容。
核心目标：帮用户快速完成"选这条/选这款"的决策，减少选择焦虑。
写作要求：
- 提供清晰的选购维度：适合脸型、风格、肤色、手机尺寸的建议
- 对比不同款式的差异：细链vs粗链、金色vs银色、简约vs繁复
- 给出明确推荐：适合XX人群的最佳选择
- 语气像专业导购，实用、直接、有依据""",

    'ST029': """你是一位专注用户真实体验的UGC式内容创作者。
本次创作主题：真实使用体验分享型内容。
核心目标：模拟真实用户的购买→使用→复购心路历程，建立信任感。
写作要求：
- 以第一人称叙述：从"当初为什么买"到"用了之后的真实感受"
- 包含真实的瑕疵/注意事项（如"容易打结需要定期整理"），增加可信度
- 强调"回购/推荐给朋友"的行为，说明产品经得起长期考验
- 避免过度完美化，保持真实口吻""",

    'ST030': """你是一位专注手机配件领域的内容创作者，深耕手机链这一细分赛道。
本次创作主题：品类教育种草型内容。
核心目标：为尚未意识到手机链价值的潜在用户进行品类教育，创造需求。
写作要求：
- 从"为什么要用手机链"切入：防摔、好看、解放双手等实用理由
- 对比有链vs无链的使用体验差异
- 普及手机链的多种玩法：单挂、叠戴、交叉链等
- 语气像行业内行人分享冷知识，激发"原来还能这样"的新鲜感""",
}

# ── Step 3: Delete duplicate ST021 ──────────────────────────────────────────
print("=== Deleting duplicate ST021 (recvgcqgJlprsD) ===")
try:
    result = fc.delete_record(STRATEGY_TABLE, 'recvgcqgJlprsD')
    print(f"  Deleted: {result}")
except Exception as e:
    print(f"  Delete failed (may already be gone): {e}")

# ── Step 4: Update ST021 (good record) — ensure 启用, add prefix if missing ──
print("\n=== Updating ST021 good record ===")
# Find ST021 good record id
st021_good = None
for r in strat_records:
    fields = r.get('fields', {})
    if fields.get('策略编号') == 'ST021' and r.get('record_id') != 'recvgcqgJlprsD':
        st021_good = r.get('record_id')
        current_prefix = fields.get('系统提示词前缀', '')
        current_enabled = fields.get('是否启用', '')
        print(f"  Found good ST021: {st021_good}, enabled={current_enabled!r}, has_prefix={bool(current_prefix)}")
        break

if st021_good:
    update_fields = {'是否启用': '启用'}
    # Only update prefix if empty
    for r in strat_records:
        if r.get('record_id') == st021_good:
            if not r.get('fields', {}).get('系统提示词前缀'):
                update_fields['系统提示词前缀'] = prefixes['ST021']
            break
    result = fc.update_record(STRATEGY_TABLE, st021_good, update_fields)
    print(f"  Updated ST021: {result}")

# ── Step 5: Update ST022-ST030 ───────────────────────────────────────────────
print("\n=== Updating ST022-ST030 ===")
code_to_recid = {
    'ST022': 'recvgcqhdeo6cA',
    'ST023': 'recvgcqhVD6qRd',
    'ST024': 'recvgcqir5Vlyq',
    'ST025': 'recvgcqiUuLdb3',
    'ST026': 'recvgcqjn3fj1a',
    'ST027': 'recvgcqjRKEdlJ',
    'ST028': 'recvgcqkkoaQL4',
    'ST029': 'recvgcqkODgP6w',
    'ST030': 'recvgcqlo4kL3y',
}
for code, rec_id in code_to_recid.items():
    fields_to_update = {
        '是否启用': '启用',
        '系统提示词前缀': prefixes[code],
    }
    try:
        result = fc.update_record(STRATEGY_TABLE, rec_id, fields_to_update)
        print(f"  {code} ({rec_id}): OK")
    except Exception as e:
        print(f"  {code} ({rec_id}): ERROR — {e}")

# ── Step 6: Update shotplan table (SP010-SP019) ──────────────────────────────
print("\n=== Updating shotplan 角色序列 for SP010-SP019 ===")

# Person-first shot sequences for each plan
# Format: list of shot objects. Index 0 = 首图 (must be person shot)
shotplan_sequences = {
    'SP010': json.dumps([
        {"index": 1, "shot": "首图人物全身", "desc": "模特全身出镜，手持手机，手机链自然垂落；穿搭完整，链子颜色与服装呼应；室内/户外自然光"},
        {"index": 2, "shot": "人物上半身特写", "desc": "模特上半身，手机握持姿势，链子在手间摇曳，突出链子与手的关系"},
        {"index": 3, "shot": "穿搭细节组合", "desc": "服装局部+链子搭配细节，展示穿搭点睛效果，色彩和谐感"},
        {"index": 4, "shot": "链子工艺特写", "desc": "手机链平铺或悬挂特写，展示材质光泽、链环工艺、吊坠细节"},
        {"index": 5, "shot": "生活场景应用", "desc": "模特在咖啡馆/街头等真实场景中自然使用手机，链子入镜"},
        {"index": 6, "shot": "多角度展示", "desc": "链子不同角度：正面、侧面、背面，清晰展示全貌"}
    ], ensure_ascii=False),

    'SP011': json.dumps([
        {"index": 1, "shot": "首图人物手部特写", "desc": "模特手部出镜，手握手机，手机链绕指或自然垂落；背景干净，突出手与链子的高品质感"},
        {"index": 2, "shot": "人物上半身持机", "desc": "模特半身，手持手机，链子自然下垂展示整体品质感和佩戴状态"},
        {"index": 3, "shot": "链子材质特写", "desc": "极近镜头：链环纹理、接口工艺、金属光泽，用微距感展示材质高级感"},
        {"index": 4, "shot": "白背景平铺展示", "desc": "链子平铺在纯色/大理石背景上，展示完整链型，清晰对比材质细节"},
        {"index": 5, "shot": "品质对比展示", "desc": "链子局部放大，对比展示工艺细节：抛光面、哑光面、接口强度"},
        {"index": 6, "shot": "整体佩戴感", "desc": "模特完整持机姿势，展示链子在真实使用状态下的垂坠感和品质感"}
    ], ensure_ascii=False),

    'SP012': json.dumps([
        {"index": 1, "shot": "首图人物拆箱", "desc": "模特手部出镜，正在打开精致礼盒，链子初露一角；制造惊喜感和礼物仪式感"},
        {"index": 2, "shot": "取出链子特写", "desc": "模特双手捧出手机链，链子在手心展示，表情惊喜（如有面部出镜）"},
        {"index": 3, "shot": "包装全貌", "desc": "礼盒+链子+配件完整展示，包装精美度、品牌感"},
        {"index": 4, "shot": "安装过程人手", "desc": "模特将链子连接到手机的过程，手部特写，展示安装简便性"},
        {"index": 5, "shot": "佩戴成品效果", "desc": "链子安装后，模特手持手机全貌，展示开箱后的使用效果"},
        {"index": 6, "shot": "链子细节特写", "desc": "链子近距离展示：接口、链环、吊坠，验证品质符合预期"}
    ], ensure_ascii=False),

    'SP013': json.dumps([
        {"index": 1, "shot": "首图人物对比持机", "desc": "模特双手分别握两款不同手机链的手机，直观对比；构图清晰，差异明显"},
        {"index": 2, "shot": "人物半身展示", "desc": "模特半身，展示当前测评款链子的佩戴整体效果"},
        {"index": 3, "shot": "两款平铺对比", "desc": "两款链子并排平铺，相同背景下对比材质、粗细、长度、设计风格"},
        {"index": 4, "shot": "细节对比特写", "desc": "两款链子关键细节对比：接口方式、链环大小、吊坠设计"},
        {"index": 5, "shot": "佩戴效果对比", "desc": "同一模特/相似角度，分别展示两款链子的佩戴效果"},
        {"index": 6, "shot": "最终推荐人物", "desc": "模特手持推荐款，给出明确推荐姿态，增强说服力"}
    ], ensure_ascii=False),

    'SP014': json.dumps([
        {"index": 1, "shot": "首图人物日常场景", "desc": "模特在真实日常场景（咖啡馆/书桌/街头），自然使用手机，链子在画面中自然呈现；非摆拍感"},
        {"index": 2, "shot": "通勤场景", "desc": "地铁/公交/步行中，模特手机链自然摇动，展示日常携带的实用美感"},
        {"index": 3, "shot": "工作场景", "desc": "桌面场景，链子随手机放在桌上或握在手中，轻松自然"},
        {"index": 4, "shot": "休闲场景", "desc": "购物/逛街/约会场景，链子与整体日常装扮的搭配"},
        {"index": 5, "shot": "链子细节", "desc": "日常使用后的链子状态特写：自然的光泽、真实的使用质感"},
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
        {"index": 4, "shot": "链子特写", "desc": "手机链从礼盒中取出，展示链子精美细节"},
        {"index": 5, "shot": "使用效果人物", "desc": "收礼人将链子装上手机，展示佩戴效果，表情满意"},
        {"index": 6, "shot": "温馨合影/单人", "desc": "收礼人手持装好链子的手机，展示最终礼物使用效果"}
    ], ensure_ascii=False),

    'SP017': json.dumps([
        {"index": 1, "shot": "首图人物叠戴全貌", "desc": "模特手腕/手部出镜，展示手机链+手链/手环的叠戴整体效果；构图美观，层次丰富"},
        {"index": 2, "shot": "叠戴细节特写", "desc": "手腕叠戴细节：手机链与手链的层次关系、颜色搭配、材质对比"},
        {"index": 3, "shot": "分层展示", "desc": "逐步叠加的过程镜头：先戴手链，再加手机链，展示叠搭逻辑"},
        {"index": 4, "shot": "不同叠戴组合", "desc": "展示2-3种叠戴方案：金+银、繁+简、粗+细等对比"},
        {"index": 5, "shot": "链子平铺组合", "desc": "手机链+常见搭配手链的平铺展示，提供搭配参考"},
        {"index": 6, "shot": "人物整体造型", "desc": "模特半身，展示叠戴效果在整体穿搭中的层次感"}
    ], ensure_ascii=False),

    'SP018': json.dumps([
        {"index": 1, "shot": "首图人物手部平铺引导", "desc": "模特手自然放在平铺背景旁，手机链摆在手边，人手入镜赋予平铺温度感；非纯静物"},
        {"index": 2, "shot": "美学平铺主图", "desc": "手机链与搭配道具（花瓣/复古小物/香薰/胶卷）精心平铺，构图美观，色调统一"},
        {"index": 3, "shot": "链子细节特写", "desc": "平铺场景中链子局部放大，展示材质光泽和工艺"},
        {"index": 4, "shot": "人物手持展示", "desc": "模特从平铺中拿起链子，手持展示链子垂坠效果"},
        {"index": 5, "shot": "佩戴效果人物", "desc": "模特将链子连接手机，展示从平铺美学到实际使用的过渡"},
        {"index": 6, "shot": "场景整体氛围", "desc": "稍微拉远，展示平铺道具+模特手的整体构图美感"}
    ], ensure_ascii=False),

    'SP019': json.dumps([
        {"index": 1, "shot": "首图校园人物全身", "desc": "模特穿校园日常装（卫衣/运动/学院风），手持手机，链子清晰可见；校园场景背景（走廊/操场/图书馆门口）"},
        {"index": 2, "shot": "背包+链子组合", "desc": "模特背着书包，手机链与书包同框，展示校园场景中链子的日常搭配"},
        {"index": 3, "shot": "课桌场景", "desc": "课桌上手机+链子自然摆放，教材/笔记本入镜，展示校园使用场景"},
        {"index": 4, "shot": "户外校园场景", "desc": "操场/草坪/走廊，模特自然拿机，链子随动作摇动，青春动感"},
        {"index": 5, "shot": "链子细节+校园元素", "desc": "链子特写与校园元素（校徽/笔/书）组合，突出校园专属氛围"},
        {"index": 6, "shot": "闺蜜/同学场景", "desc": "两个人一起展示（如有），或模特独自摆出青春感十足的姿势，活力收尾"}
    ], ensure_ascii=False),
}

# Fetch shotplan records to get record IDs
print("Fetching shotplan records...")
shotplan_records = fc.list_records(SHOTPLAN_TABLE)
plan_rec_ids = {}
for r in shotplan_records:
    fields = r.get('fields', {})
    code = fields.get('方案编号', '')
    rec_id = r.get('record_id', '')
    enabled = fields.get('是否启用', '')
    if code in shotplan_sequences:
        plan_rec_ids[code] = rec_id
        print(f"  {code} | {rec_id} | 启用={enabled!r}")

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
