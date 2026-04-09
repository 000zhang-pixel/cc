#!/usr/bin/env python3
"""
Update 拍摄方案表 SP010-SP039 角色序列 guidance:
  Principle: 手机链挂在手机上才体现真正产品效果。
  手机+链条一起展示应是主流方向，减少链条单独拍摄次数。

  Changes applied:
  - All "链条整体近景展示" → "手持挂链手机近景，链条完整入镜，展示金属光泽与整体形态"
  - All "链条整体展示" (standalone) → "手持挂链手机，链条完整入镜展示"
  - SP011: Quality test plan — add phone context to product shots while preserving detail focus
  - SP013: Multi-SKU comparison — all comparison shots on phone
  - SP018: Flat-lay plan — phone+chain flat lay as primary, chain-only becomes secondary layer
  - SP039: Minimal plan — "链条静物平铺" → "挂链手机极简平铺展示"
"""
import json, sys, time
sys.path.insert(0, 'D:/AI-Content-Hub')
from dotenv import load_dotenv
load_dotenv('D:/AI-Content-Hub/.env', override=False)
from middleware.core.config import load_system
from middleware.adapters.feishu import FeishuClient

cfg = load_system()
fei = cfg['feishu']
fc = FeishuClient(app_id=fei['app_id'], app_secret=fei['app_secret'], base_token=fei['base_token'])
SP_TABLE = 'tbl0xCaqru1TjwzK'

# ─────────────────────────────────────────────────────────────────────────────
# Updated 角色序列 for each plan.
# Only plans that need changes are listed; others are left untouched.
# ─────────────────────────────────────────────────────────────────────────────

UPDATED_PLANS = {
    # SP010: 穿搭种草6图
    # Change: index 3 "链条整体近景展示" → phone+chain near shot
    "SP010": [
        {"index": 1, "zh": "穿搭整体亮相（含链条）",   "guidance": "全身或半身穿搭，手持挂链手机，链条清晰可见"},
        {"index": 2, "zh": "手部持机近景",              "guidance": "手持挂链手机，链条垂坠自然，整条链条可见"},
        {"index": 3, "zh": "手持挂链手机近景展示",      "guidance": "手持挂链手机近景，链条完整入镜，展示金属光泽与整体形态"},
        {"index": 4, "zh": "场景融入镜头",              "guidance": "在{scene_description}中自然使用手机，挂链手机可见"},
        {"index": 5, "zh": "侧面轮廓展示",              "guidance": "侧身站立，手持挂链手机，突出链条在身上的垂坠形态"},
        {"index": 6, "zh": "收尾引导镜头",              "guidance": "面向镜头，手持挂链手机，传递轻松愉悦感，引导互动"},
    ],
    # SP011: 质感测评6图
    # Quality test plan — keep detail shots but anchor with phone context
    # index 1: chain flat-lay → phone+chain together
    # index 4: hand-hold weight feel → holding the phone+chain combo
    # index 5: "上机效果" already good — keep
    # index 6: already phone+chain — keep
    "SP011": [
        {"index": 1, "zh": "挂链手机整体平铺展示",      "guidance": "手机与链条共同平铺，展示安装后的完整产品形态"},
        {"index": 2, "zh": "材质整体近景",              "guidance": "链条中近景展示纹路、金属肌理，保持链条整体可见（可在手机上拍摄）"},
        {"index": 3, "zh": "扣件与工艺细节",            "guidance": "龙虾扣/弹簧扣/手机孔周围工艺细节，展示精细做工"},
        {"index": 4, "zh": "手持挂链手机重量感",        "guidance": "手持装有链条的手机，传递整机+链条的重量感与做工品质"},
        {"index": 5, "zh": "上机效果整体展示",          "guidance": "链条安装在手机上的整体效果，多角度展示"},
        {"index": 6, "zh": "品质总结整体展示",          "guidance": "挂链手机完整入镜，从整体呈现产品品质，收尾展示"},
    ],
    # SP012: 开箱仪式5图 — already has phone context, no change needed
    # SP013: 多款对比4图
    # index 1: "多款链条并排展示" → all on phones
    # index 2: keep but clarify chain visible on phone
    # index 3: already "上机效果对比" — good
    "SP013": [
        {"index": 1, "zh": "多款挂链手机并排展示",      "guidance": "2-3款不同风格/颜色链条分别安装在手机上并排，清晰对比整体效果"},
        {"index": 2, "zh": "款式差异对比展示",          "guidance": "每款链条的特色细节分别展示，链条完整可见，保持手机+链条同框"},
        {"index": 3, "zh": "分别上机效果",              "guidance": "相同手机搭配不同链条的上机效果对比，突出款式风格差异"},
        {"index": 4, "zh": "搭配推荐收尾",              "guidance": "手持挂链手机，给出哪款更适合哪种风格的建议，引导选购"},
    ],
    # SP014: 场景日常4图 — already has phone context, index 3 needs slight fix
    "SP014": [
        {"index": 1, "zh": "出门携带场景",              "guidance": "手持挂链手机出门，链条垂落自然，真实日常感"},
        {"index": 2, "zh": "咖啡厅/室内使用",          "guidance": "在{scene_description}中自然使用挂链手机，链条可见"},
        {"index": 3, "zh": "手持挂链手机质感展示",      "guidance": "近景手持挂链手机，突出链条整体质感与垂坠，手机同框"},
        {"index": 4, "zh": "日常结语镜头",              "guidance": "轻松自然的收尾，手持挂链手机，传递每天都在用的日常感"},
    ],
    # SP015: 搭配教程6图
    # index 1: "素颜基础款展示" → phone+chain instead of bare chain
    "SP015": [
        {"index": 1, "zh": "挂链手机基础款展示",        "guidance": "展示链条安装在手机上的基础形态，建立整体审美印象"},
        {"index": 2, "zh": "通勤穿搭搭配",              "guidance": "职场/通勤风穿搭中手持挂链手机的搭配效果"},
        {"index": 3, "zh": "休闲穿搭搭配",              "guidance": "休闲/学院风穿搭中手持挂链手机的搭配效果"},
        {"index": 4, "zh": "晚装/精致穿搭",            "guidance": "晚装或精致穿搭中挂链手机的高级感呈现"},
        {"index": 5, "zh": "搭配技巧总结",              "guidance": "手持挂链手机，口播或文字总结搭配要点"},
        {"index": 6, "zh": "最终look展示",              "guidance": "完整穿搭look，手持挂链手机作为点睛配件"},
    ],
    # SP016: 礼物推荐5图
    # index 2: "链条颜值展示" → phone+chain in gift box
    "SP016": [
        {"index": 1, "zh": "节日/送礼场景引入",        "guidance": "节日氛围道具+挂链手机或链条礼盒，传递礼物感"},
        {"index": 2, "zh": "挂链手机颜值展示",          "guidance": "挂链手机放在礼盒中或手持展示，强调整体外观精致感"},
        {"index": 3, "zh": "上手佩戴效果",              "guidance": "女生收到后将链条装到手机上的使用效果"},
        {"index": 4, "zh": "开心反应镜头",              "guidance": "收礼者手持挂链手机的满意/惊喜表情（真实感优先）"},
        {"index": 5, "zh": "引导收尾",                  "guidance": "手持挂链手机总结送这款链的理由，引导下单"},
    ],
    # SP017: 叠戴混搭6图
    # Multiple chains on same phone is the core concept; guidance update for clarity
    "SP017": [
        {"index": 1, "zh": "单条基础款亮相",            "guidance": "手持单条链条挂在手机上，建立基础审美"},
        {"index": 2, "zh": "两条叠戴效果",              "guidance": "同一手机挂两条不同风格链条，展示叠戴层次感"},
        {"index": 3, "zh": "三条混搭效果",              "guidance": "同一手机挂三条链混搭，突出个性化与丰富感"},
        {"index": 4, "zh": "搭配逻辑说明",              "guidance": "手持多链手机，通过文字说明哪几条适合叠戴"},
        {"index": 5, "zh": "穿搭融合展示",              "guidance": "叠戴挂链手机配合穿搭的整体效果"},
        {"index": 6, "zh": "购买推荐收尾",              "guidance": "展示具体叠戴组合方案，引导连带购买"},
    ],
    # SP018: 美学平铺5图
    # index 1: chain-only flat lay → phone+chain flat lay
    # index 2: already phone+chain — keep as key hero shot
    # index 4: near shot still chain focused but phone present
    "SP018": [
        {"index": 1, "zh": "挂链手机主体平铺",          "guidance": "手机与链条共同平铺，构图工整，展示整体产品形态和链条造型"},
        {"index": 2, "zh": "手机加链条组合平铺",        "guidance": "手机与链条紧密组合平铺，突出使用关系与整体质感"},
        {"index": 3, "zh": "道具氛围加入",              "guidance": "挂链手机加鲜花/书本/香薰等道具，营造生活美学氛围"},
        {"index": 4, "zh": "平铺链条近景",              "guidance": "平铺图中手持挂链手机近景入镜，突出链条细节美感，保持链条整体可见"},
        {"index": 5, "zh": "完整美学收尾",              "guidance": "最终完整平铺构图，挂链手机为主体，呈现整体美学"},
    ],
    # SP019: 校园风4图
    # index 3: "链条近景质感展示" → phone+chain
    "SP019": [
        {"index": 1, "zh": "校园场景中链条亮相",        "guidance": "校园或图书馆背景，手持挂链手机，链条清晰可见"},
        {"index": 2, "zh": "学院风穿搭搭配",            "guidance": "穿着格纹/牛仔等学院风，手持挂链手机与整体搭配"},
        {"index": 3, "zh": "手持挂链手机质感展示",      "guidance": "近景手持挂链手机入镜，传递青春精致感，链条整体可见"},
        {"index": 4, "zh": "青春感收尾",                "guidance": "轻松自然的结尾，手持挂链手机，传递年轻活力感"},
    ],

    # SP020-SP039: v2 plans ───────────────────────────────────────────────────
    # Most plans have a "链条整体近景展示" or "链条整体展示" node that needs updating.
    # The pattern is consistent: → "手持挂链手机近景，链条完整入镜，展示金属光泽与整体形态"

    # SP020: 健身房场景6图
    "SP020": [
        {"index": 1, "zh": "健身房镜前全身亮相",        "guidance": "穿健身装在落地镜前展示，手持挂链手机，链条与整体运动穿搭清晰可见"},
        {"index": 2, "zh": "健身间隙手持挂链手机近景",  "guidance": "手持挂链手机近景，链条垂坠清晰，体现质感"},
        {"index": 3, "zh": "器械区使用手机场景",        "guidance": "在{scene_description}中自然使用挂链手机，链条可见，背景器械虚化"},
        {"index": 4, "zh": "手持挂链手机整体展示",      "guidance": "手持挂链手机近景，链条完整入镜，展示金属光泽与整体形态"},
        {"index": 5, "zh": "健身装束人物侧身展示",      "guidance": "穿健身装侧身站立或坐姿，手持挂链手机，链条垂坠形态优美"},
        {"index": 6, "zh": "健身收尾持机引导",          "guidance": "面向镜头，手持挂链手机，传递运动后满足感，引导互动"},
    ],
    # SP021: 瑜伽裤生活感5图
    "SP021": [
        {"index": 1, "zh": "瑜伽裤人物整体亮相",        "guidance": "全身或半身展示瑜伽裤穿搭，手持挂链手机，链条清晰可见"},
        {"index": 2, "zh": "手持挂链手机质感近景",      "guidance": "手持挂链手机近景，链条与瑜伽裤形成材质对比"},
        {"index": 3, "zh": "瑜伽垫场景使用",            "guidance": "在{scene_description}中自然使用挂链手机，瑜伽氛围感"},
        {"index": 4, "zh": "手持挂链手机整体展示",      "guidance": "手持挂链手机近景，链条完整入镜，体现精致感"},
        {"index": 5, "zh": "健康生活态度收尾",          "guidance": "展示精致健康生活感，手持挂链手机作为配件点睛，引导互动"},
    ],
    # SP022: 迷你裙街头种草6图
    "SP022": [
        {"index": 1, "zh": "迷你裙全身穿搭亮相",        "guidance": "迷你裙整体穿搭出镜，手持挂链手机，链条清晰可见，展示完整造型"},
        {"index": 2, "zh": "街头行走链条摇曳",          "guidance": "行走动态中手持挂链手机，链条摇曳，迷你裙与链条共同呈现时髦感"},
        {"index": 3, "zh": "手持挂链手机质感近景",      "guidance": "手持挂链手机近景，展示链条细节与金属光泽"},
        {"index": 4, "zh": "街头场景融入",              "guidance": "在{scene_description}中自然使用挂链手机，街头背景虚化"},
        {"index": 5, "zh": "迷你裙坐姿挂链展示",        "guidance": "坐姿中手持挂链手机，链条垂落，迷你裙与链条同框，优雅自然"},
        {"index": 6, "zh": "时髦女孩收尾引导",          "guidance": "面向镜头手持挂链手机展示最终造型，引导粉丝互动"},
    ],
    # SP023: 运动跑步场景5图
    "SP023": [
        {"index": 1, "zh": "运动装束整体亮相",          "guidance": "运动穿搭全身或半身展示，手持挂链手机，链条配合运动装束清晰可见"},
        {"index": 2, "zh": "跑步动态链条飞扬",          "guidance": "跑步动作中手持挂链手机随运动飞扬，展示动感活力"},
        {"index": 3, "zh": "手持挂链手机近景",          "guidance": "手持挂链手机近景，展示链条与运动感碰撞"},
        {"index": 4, "zh": "运动后场景休息",            "guidance": "在{scene_description}中运动后自然持机，传递真实运动感"},
        {"index": 5, "zh": "运动生活收尾",              "guidance": "展示运动健康生活态度，手持挂链手机作为潮流运动配件"},
    ],
    # SP024: 车内出行场景5图
    "SP024": [
        {"index": 1, "zh": "车内整体亮相持机",          "guidance": "在车内坐姿，手持挂链手机，链条清晰可见，车内环境整洁"},
        {"index": 2, "zh": "车内挂链手机光感近景",      "guidance": "车窗光线下手持挂链手机近景，链条金属质感展示，手机同框"},
        {"index": 3, "zh": "车内自拍场景",              "guidance": "在{scene_description}车内自拍，手持挂链手机自然呈现"},
        {"index": 4, "zh": "手持挂链手机整体展示",      "guidance": "手持挂链手机完整入镜展示，体现品质感，链条整体可见"},
        {"index": 5, "zh": "出行收尾引导",              "guidance": "手持挂链手机传递精致出行生活感，引导互动下单"},
    ],
    # SP025: 运动生活全场景6图
    "SP025": [
        {"index": 1, "zh": "运动装束整体亮相",          "guidance": "健身/瑜伽/跑步装束展示，手持挂链手机，链条与整体运动穿搭协调"},
        {"index": 2, "zh": "健身场景使用",              "guidance": "在{scene_description}中自然使用挂链手机，运动场景背景虚化"},
        {"index": 3, "zh": "手持挂链手机质感近景",      "guidance": "近景手持挂链手机，链条垂坠清晰，展示金属质感"},
        {"index": 4, "zh": "运动动态链条展示",          "guidance": "运动动作中手持挂链手机，链条呈现动感形态，传递活力"},
        {"index": 5, "zh": "休息间隙人物侧身",          "guidance": "运动间隙侧身或坐姿，手持挂链手机自然垂落，传递精致感"},
        {"index": 6, "zh": "运动生活总结收尾",          "guidance": "面向镜头，手持挂链手机，传递运动潮流生活态度"},
    ],
    # SP026: 户外探索6图
    "SP026": [
        {"index": 1, "zh": "户外整体造型亮相",          "guidance": "户外穿搭全身展示，手持挂链手机，链条清晰可见，背景自然景色虚化"},
        {"index": 2, "zh": "户外场景持机使用",          "guidance": "在{scene_description}中自然持机，挂链手机链条随户外活动呈现"},
        {"index": 3, "zh": "户外阳光挂链手机光感",      "guidance": "自然阳光下手持挂链手机近景，链条金属光泽体现材质质感"},
        {"index": 4, "zh": "户外动态行走",              "guidance": "行走或运动中手持挂链手机，链条摇曳，背景户外自然虚化"},
        {"index": 5, "zh": "户外人物侧身",              "guidance": "侧身展示手持挂链手机，链条垂坠形态，背景户外景色虚化"},
        {"index": 6, "zh": "自由户外收尾引导",          "guidance": "面向镜头，手持挂链手机，传递自由户外生活感，引导互动"},
    ],
    # SP027: 通勤日常5图
    "SP027": [
        {"index": 1, "zh": "通勤穿搭整体亮相",          "guidance": "职场/通勤穿搭全身展示，手持挂链手机，链条与整体造型清晰可见"},
        {"index": 2, "zh": "地铁/交通场景持机",         "guidance": "在{scene_description}通勤途中自然使用挂链手机，链条清晰"},
        {"index": 3, "zh": "手持挂链手机质感近景",      "guidance": "手持挂链手机近景，展示链条细节，传递精致通勤感"},
        {"index": 4, "zh": "车内等待场景",              "guidance": "车内或车站等待中，手持挂链手机，链条自然垂落，日常真实感"},
        {"index": 5, "zh": "通勤收尾引导",              "guidance": "传递每天通勤都在用的真实感，手持挂链手机，引导下单"},
    ],
    # SP028: 节日氛围5图
    "SP028": [
        {"index": 1, "zh": "节日造型整体亮相",          "guidance": "节日穿搭全身展示，手持挂链手机，链条与节日服装搭配清晰可见"},
        {"index": 2, "zh": "节日场景氛围镜头",          "guidance": "在{scene_description}节日氛围中自然持机，背景节日感"},
        {"index": 3, "zh": "挂链手机节日光感近景",      "guidance": "手持挂链手机近景，节日灯光下链条金属光泽展示"},
        {"index": 4, "zh": "节日礼物展示",              "guidance": "挂链手机作为礼物展示，礼盒氛围，传递送礼感"},
        {"index": 5, "zh": "节日收尾引导",              "guidance": "手持挂链手机传递节日时髦感，引导节日购买"},
    ],
    # SP029: 街头潮流6图
    "SP029": [
        {"index": 1, "zh": "街头潮流整体亮相",          "guidance": "街头风格穿搭全身展示，手持挂链手机作为核心配件清晰可见"},
        {"index": 2, "zh": "街头行走动态",              "guidance": "街头行走中手持挂链手机，链条摇曳，背景城市虚化，抓拍感"},
        {"index": 3, "zh": "涂鸦/街头背景持机",         "guidance": "在{scene_description}街头场景中持挂链手机，链条与背景形成对比"},
        {"index": 4, "zh": "手持挂链手机整体近景",      "guidance": "手持挂链手机完整入镜，街头光线下金属质感展示"},
        {"index": 5, "zh": "街头坐姿放松",              "guidance": "台阶或街头坐姿，手持挂链手机，链条自然垂落，随性真实感"},
        {"index": 6, "zh": "街头范儿收尾",              "guidance": "面向镜头，手持挂链手机，传递街头个性潮流感"},
    ],
    # SP030: 咖啡约会5图
    "SP030": [
        {"index": 1, "zh": "约会穿搭整体亮相",          "guidance": "精致约会穿搭展示，手持挂链手机，链条与穿搭搭配清晰可见"},
        {"index": 2, "zh": "咖啡厅窗边持机",            "guidance": "在{scene_description}咖啡厅中自然持挂链手机，链条垂落，暖色调氛围"},
        {"index": 3, "zh": "挂链手机质感近景",          "guidance": "手持挂链手机近景，窗边光线下展示链条细节与金属感"},
        {"index": 4, "zh": "人物侧面优雅展示",          "guidance": "侧身坐姿或站姿，手持挂链手机，链条垂落，传递精致约会感"},
        {"index": 5, "zh": "约会场景收尾",              "guidance": "面向镜头手持挂链手机传递精致生活感，引导互动"},
    ],
    # SP031: 旅行出游6图
    "SP031": [
        {"index": 1, "zh": "旅行穿搭整体亮相",          "guidance": "旅行穿搭全身展示，手持挂链手机，链条清晰可见，户外旅行感"},
        {"index": 2, "zh": "旅行场景持机",              "guidance": "在{scene_description}旅行景点中自然持机，背景虚化"},
        {"index": 3, "zh": "旅途中挂链手机近景",        "guidance": "手持挂链手机近景，旅途光线下链条质感展示"},
        {"index": 4, "zh": "旅途动态拍摄",              "guidance": "行走或旅途动态中手持挂链手机，链条摇曳，背景旅行场景虚化"},
        {"index": 5, "zh": "旅途侧面轮廓",              "guidance": "侧面展示手持挂链手机，链条垂坠，旅行场景背景虚化"},
        {"index": 6, "zh": "旅途收尾引导",              "guidance": "手持挂链手机传递旅行时髦感，引导互动"},
    ],
    # SP032: 夜间出行5图
    "SP032": [
        {"index": 1, "zh": "夜间穿搭整体亮相",          "guidance": "夜间出行穿搭展示，手持挂链手机，链条在灯光下金属光泽清晰可见"},
        {"index": 2, "zh": "夜间场景持机",              "guidance": "在{scene_description}夜间场景中自然持挂链手机，霓虹或夜灯背景"},
        {"index": 3, "zh": "夜间挂链手机光感近景",      "guidance": "夜间灯光下手持挂链手机近景，链条金属光泽与霓虹色感展示"},
        {"index": 4, "zh": "夜间侧身轮廓",              "guidance": "侧身或四分之三角度，夜间轮廓光勾勒，手持挂链手机可见"},
        {"index": 5, "zh": "夜间收尾引导",              "guidance": "手持挂链手机传递夜间时髦感，前卫都市风，引导互动"},
    ],
    # SP033: 闺蜜同框5图
    "SP033": [
        {"index": 1, "zh": "闺蜜双人整体亮相",          "guidance": "两人并肩展示，各自手持挂链手机，链条清晰可见，双人时髦感"},
        {"index": 2, "zh": "闺蜜场景同框",              "guidance": "在{scene_description}中两人自然同框，手持挂链手机同款展示"},
        {"index": 3, "zh": "挂链手机近景双人对比",      "guidance": "两人手持挂链手机近景对比，展示款式差异或同款魅力"},
        {"index": 4, "zh": "闺蜜互动镜头",              "guidance": "两人自然互动，挂链手机在互动中自然呈现，社交感强"},
        {"index": 5, "zh": "同款闺蜜收尾",              "guidance": "手持挂链手机传递闺蜜同款社交属性，引导拉好友一起买"},
    ],
    # SP034: 春夏季节感5图
    "SP034": [
        {"index": 1, "zh": "春夏穿搭整体亮相",          "guidance": "春夏轻薄穿搭展示，手持挂链手机，链条与轻盈服装搭配清晰可见"},
        {"index": 2, "zh": "春夏户外场景",              "guidance": "在{scene_description}樱花/公园等春夏场景中自然持挂链手机"},
        {"index": 3, "zh": "挂链手机春夏光感",          "guidance": "春日散射光或阳光下手持挂链手机，链条光泽展示，轻盈质感"},
        {"index": 4, "zh": "春夏动态行走",              "guidance": "轻盈行走或跳跃，手持挂链手机，链条随动作摇曳，传递春夏活力"},
        {"index": 5, "zh": "春夏收尾引导",              "guidance": "手持挂链手机传递春夏时髦感，链条作为季节单品，引导购买"},
    ],
    # SP035: 秋冬穿搭5图
    "SP035": [
        {"index": 1, "zh": "秋冬穿搭整体亮相",          "guidance": "秋冬厚实穿搭展示，手持挂链手机，链条与深色外套形成视觉对比"},
        {"index": 2, "zh": "秋冬户外场景",              "guidance": "在{scene_description}秋日落叶或冬日场景中自然持挂链手机"},
        {"index": 3, "zh": "挂链手机秋冬光感",          "guidance": "秋冬自然光下手持挂链手机，链条金属质感展示，暖调对比"},
        {"index": 4, "zh": "秋冬侧面轮廓",              "guidance": "厚实穿搭侧面展示，手持挂链手机，链条垂坠与穿搭整体感"},
        {"index": 5, "zh": "秋冬收尾引导",              "guidance": "手持挂链手机传递秋冬时髦感，链条作为季节配件点睛，引导购买"},
    ],
    # SP036: 自拍视角5图
    "SP036": [
        {"index": 1, "zh": "自拍视角首张亮相",          "guidance": "模拟自拍角度，手持挂链手机朝镜头，链条垂落清晰可见"},
        {"index": 2, "zh": "自拍场景链条特写",          "guidance": "自拍视角下手持挂链手机近景，展示链条垂坠与质感"},
        {"index": 3, "zh": "日常场景自拍",              "guidance": "在{scene_description}中自拍姿态，挂链手机与场景融合"},
        {"index": 4, "zh": "手持挂链手机整体自拍展示",  "guidance": "挂链手机完整入镜，自拍角度下的整体形态展示"},
        {"index": 5, "zh": "自拍收尾互动",              "guidance": "手持挂链手机传递日常自拍亲近感，引导粉丝互动"},
    ],
    # SP037: 车内出行高级5图
    "SP037": [
        {"index": 1, "zh": "车内精致造型亮相",          "guidance": "车内坐姿整体展示，精致穿搭配手持挂链手机，车窗透光"},
        {"index": 2, "zh": "车内挂链手机质感近景",      "guidance": "车内侧光下手持挂链手机近景，链条金属质感展示，工艺细节"},
        {"index": 3, "zh": "车内自拍场景",              "guidance": "在{scene_description}车内自拍姿态，挂链手机自然呈现"},
        {"index": 4, "zh": "车内等待持机展示",          "guidance": "等待或停车时低头看挂链手机，链条垂落真实感"},
        {"index": 5, "zh": "出行生活收尾",              "guidance": "手持挂链手机传递精致出行生活方式，引导互动"},
    ],
    # SP038: 黄金时段大片6图
    "SP038": [
        {"index": 1, "zh": "黄金时段整体亮相",          "guidance": "黄金时段光线下整体造型展示，手持挂链手机，暖光光晕可见"},
        {"index": 2, "zh": "逆光轮廓镜头",              "guidance": "黄金时段逆光拍摄，手持挂链手机，链条金属光晕，轮廓光勾勒"},
        {"index": 3, "zh": "挂链手机暖光近景",          "guidance": "暖橙色光线下手持挂链手机近景，链条金属质感与黄金光感展示"},
        {"index": 4, "zh": "场景融入大片感",            "guidance": "在{scene_description}中黄金时段自然持挂链手机，背景光斑虚化"},
        {"index": 5, "zh": "人物侧面剪影感",            "guidance": "侧身轮廓，黄金时段光线勾勒，手持挂链手机，链条垂坠形态"},
        {"index": 6, "zh": "大片感收尾引导",            "guidance": "手持挂链手机传递高级大片质感，引导用户代入与互动"},
    ],
    # SP039: 极简品质4图
    # index 2: "链条静物平铺" → "挂链手机极简平铺"
    "SP039": [
        {"index": 1, "zh": "极简背景人物亮相",          "guidance": "纯白或浅色极简背景，人物手持挂链手机，视觉干净"},
        {"index": 2, "zh": "挂链手机极简平铺",          "guidance": "手机与链条共同在极简背景平铺，光线精准，展示整体工艺与使用形态"},
        {"index": 3, "zh": "手持挂链手机质感展示",      "guidance": "手持挂链手机近景，极简背景下链条与手机整体细节一目了然"},
        {"index": 4, "zh": "极简收尾展示",              "guidance": "人物手持挂链手机面向镜头，极简干净，引导品质感转化"},
    ],
}

# ─────────────────────────────────────────────
# Fetch all records, update 角色序列
# ─────────────────────────────────────────────
print("\n=== Updating SP010-SP039: phone+chain guidance direction ===")
records = fc.list_records(SP_TABLE)
print(f"Total records: {len(records)}")

target_codes = set(UPDATED_PLANS.keys())
to_update = {}
for r in records:
    fields = r.get('fields', {})
    code = fields.get('方案编号', '')
    if code in target_codes:
        to_update[code] = r['record_id']

print(f"Matched {len(to_update)}/{len(target_codes)} target records\n")

ok_count = 0
fail_count = 0
for code, rec_id in sorted(to_update.items()):
    role_seq = json.dumps(UPDATED_PLANS[code], ensure_ascii=False)
    updates = {"角色序列": role_seq}
    try:
        fc.update_record(SP_TABLE, rec_id, updates)
        print(f"  OK  {code}")
        ok_count += 1
    except Exception as e:
        print(f"  FAIL {code}: {e}")
        fail_count += 1
    time.sleep(0.3)

print(f"\n=== Done: {ok_count} OK, {fail_count} FAIL ===")
