#!/usr/bin/env python3
"""
Upgrade 视觉场景表 (表10) in three passes:
  1. Create 3 new fields: 服装风格, 身体展示重点, 着装禁忌
  2. Rename 首图->人物 in 场景名称 and 场景类型 for SC042-SC091
  3. Populate new fields + enrich 场景基底_英文 for all 50 人物 scenes
"""
import sys, time
sys.path.insert(0, 'D:/AI-Content-Hub')
from dotenv import load_dotenv
load_dotenv('D:/AI-Content-Hub/.env', override=False)
from middleware.core.config import load_system
from middleware.adapters.feishu import FeishuClient
import lark_oapi as lark
from lark_oapi.api.bitable.v1 import (
    CreateAppTableFieldRequest,
    AppTableField,
)

cfg = load_system()
fei = cfg['feishu']
fc = FeishuClient(app_id=fei['app_id'], app_secret=fei['app_secret'], base_token=fei['base_token'])
SCENE_TABLE = 'tbliWlwiyA4sppgY'

# ─────────────────────────────────────────────
# PASS 1: Create new fields (if not exist)
# ─────────────────────────────────────────────
NEW_FIELDS = [
    {"field_name": "服装风格",     "type": 1},  # 1 = 文本
    {"field_name": "身体展示重点", "type": 1},
    {"field_name": "着装禁忌",     "type": 1},
]

print("=== PASS 1: Creating new fields ===")
_client = fc._client
for fld in NEW_FIELDS:
    body = AppTableField.builder().field_name(fld["field_name"]).type(fld["type"]).build()
    resp = _client.bitable.v1.app_table_field.create(
        CreateAppTableFieldRequest.builder()
        .app_token(fei['base_token'])
        .table_id(SCENE_TABLE)
        .request_body(body)
        .build()
    )
    if resp.success():
        print(f"  Created: {fld['field_name']}")
    else:
        # code 1254038 = field already exists
        if resp.code == 1254038:
            print(f"  Already exists: {fld['field_name']}")
        else:
            print(f"  WARN [{resp.code}] {fld['field_name']}: {resp.msg}")
    time.sleep(0.3)

# ─────────────────────────────────────────────
# Scene data: name rename + new field values + 英文 enrichment
# Keys: sc_code -> dict of field updates
# ─────────────────────────────────────────────

# clothing data per scene
SCENE_DATA = {
    # ── SC042-SC061 原首图场景 ──
    "SC042": {
        "场景名称":   "人物·黄金时段街头侧逆光持机",
        "场景类型":   "人物场景",
        "服装风格":   "修身连衣裙/紧身上衣搭配短裙，展现腰部和腿部线条",
        "身体展示重点": "腰部曲线，腿部线条，肩颈轮廓",
        "着装禁忌":   "不要宽松卫衣，不要大廓形外套遮挡身材，不要运动休闲风",
        "场景基底_英文": "young Asian woman 3/4 angle on city street during golden hour, backlit warm orange glow, holding phone with decorative chain, chain catching golden light, blurred city bokeh background, wearing fitted dress or crop top with mini skirt showing waist and leg curves, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC043": {
        "场景名称":   "人物·咖啡厅坐姿链条自然垂落",
        "场景类型":   "人物场景",
        "服装风格":   "露肩/V领上衣或修身针织衫，展现锁骨和肩部线条",
        "身体展示重点": "锁骨，肩颈线条，手臂线条",
        "着装禁忌":   "不要高领毛衣遮挡颈部，不要宽松休闲服，不要厚重大衣",
        "场景基底_英文": "young Asian woman sitting at cafe window seat, one hand holding phone with chain draping naturally onto table, warm cream window light, cozy lifestyle atmosphere, wearing off-shoulder or V-neck knit top revealing collarbone and shoulder curves, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC044": {
        "场景名称":   "人物·行走动态链条摇曳",
        "场景类型":   "人物场景",
        "服装风格":   "修身短裙或紧身裤搭配上衣，行走中展现腿部线条",
        "身体展示重点": "腿部线条，臀部曲线，行走姿态",
        "着装禁忌":   "不要宽松阔腿裤遮挡腿型，不要厚重外套，不要运动套装",
        "场景基底_英文": "young Asian woman walking on city street or mall corridor, holding phone with swaying chain, chain in natural motion, blurred background showing movement, candid dynamic feel, wearing fitted mini skirt or slim pants showing leg lines and curves, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC045": {
        "场景名称":   "人物·公园草地阳光清新站姿",
        "场景类型":   "人物场景",
        "服装风格":   "吊带裙/短裙或修身连衣裙，展现手臂和腿部线条",
        "身体展示重点": "手臂线条，腿部比例，整体身材比例",
        "着装禁忌":   "不要厚重外套，不要宽松连衣裙遮挡腰身，不要运动装",
        "场景基底_英文": "young Asian woman standing in park with green lawn or dappled tree shade, facing camera holding phone with chain, natural sunlight filtering through leaves creating bokeh, fresh and bright atmosphere, wearing slip dress or fitted sundress revealing arms and legs, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC046": {
        "场景名称":   "人物·极简白色背景正面亮相",
        "场景类型":   "人物场景",
        "服装风格":   "修身连衣裙或紧身上衣配高腰短裙，突出腰臀比例",
        "身体展示重点": "腰臀比例，整体身材曲线，正面站姿比例",
        "着装禁忌":   "不要白色服装与白色背景融合，不要宽松休闲服，不要图案复杂遮挡身材",
        "场景基底_英文": "young Asian woman standing face-on against pure white or light grey minimal background, holding phone with chain clearly visible and draping, clean commercial look with strong visual focus on person and chain, wearing fitted bodycon dress or crop top with high-waist mini skirt showing waist-hip ratio, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC047": {
        "场景名称":   "人物·夜景霓虹灯光持机",
        "场景类型":   "人物场景",
        "服装风格":   "紧身皮质/亮面短裙或修身连体衣，夜间光感搭配",
        "身体展示重点": "腿部线条，腰部曲线，夜间性感气质",
        "着装禁忌":   "不要全黑暗沉遮挡身材轮廓，不要休闲运动服，不要颜色与霓虹灯撞色混乱",
        "场景基底_英文": "young Asian woman at night in front of neon city lights, holding phone with chain reflecting colorful neon glow, chain catching vibrant metallic shimmer, blurred night city background, trendy and edgy atmosphere, wearing fitted leather-look or shiny mini skirt/bodysuit showing leg curves, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC048": {
        "场景名称":   "人物·窗边室内侧光含蓄持机",
        "场景类型":   "人物场景",
        "服装风格":   "V领/斜肩上衣或修身针织连衣裙，侧光勾勒身材轮廓",
        "身体展示重点": "侧颜，肩颈线条，腰部曲线轮廓",
        "着装禁忌":   "不要高领遮挡颈部，不要宽松款式模糊身材轮廓",
        "场景基底_英文": "young Asian woman near indoor window, 3/4 angle, holding phone with chain, natural side window light sculpting her profile, chain showing metallic texture in sidelight, quiet sophisticated indoor mood, wearing V-neck or off-shoulder fitted knit dress with side light contouring her silhouette, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC049": {
        "场景名称":   "人物·穿搭全身链条整体亮相",
        "场景类型":   "人物场景",
        "服装风格":   "完整时尚穿搭——上衣/外套+短裙/紧身裤，链条作为点睛配件",
        "身体展示重点": "整体身材比例，全身穿搭搭配，链条与穿搭的配合",
        "着装禁忌":   "不要穿搭过于随意遮挡体型，不要链条被服装完全遮挡",
        "场景基底_英文": "young Asian woman full body outfit shot, holding phone with chain or chain hanging naturally at side, complete styled look with chain as key accessory, clean or city bokeh background, fashion editorial feel, wearing fashionable coordinated outfit — fitted top/jacket with mini skirt or slim pants showing full figure proportions, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC050": {
        "场景名称":   "人物·台阶坐姿自然感持机",
        "场景类型":   "人物场景",
        "服装风格":   "短裙/修身裤搭配上衣，坐姿展现腿部线条",
        "身体展示重点": "腿部线条，坐姿身材曲线，自然放松感",
        "着装禁忌":   "不要宽松长裙遮挡腿型，不要厚重外套，不要坐姿发生走光",
        "场景基底_英文": "young Asian woman casually sitting on outdoor steps or stone bench, relaxed natural pose, holding phone with chain draping to side, authentic street lifestyle feel, wearing mini skirt or slim pants with top revealing leg lines in sitting pose, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC051": {
        "场景名称":   "人物·书店文艺场景持机",
        "场景类型":   "人物场景",
        "服装风格":   "修身针织衫/polo领/斜肩上衣配短裙或修身裤，文艺精致感",
        "身体展示重点": "锁骨，腰部，整体精致气质",
        "着装禁忌":   "不要过于宽松casual，不要颜色与书架背景融合，不要厚重大衣",
        "场景基底_英文": "young Asian woman standing by bookstore shelves, holding phone with decorative chain, chain hanging naturally, warm bokeh bookshelf background, literary and refined atmosphere, wearing fitted knit or polo-neck sweater with mini skirt showing elegant figure, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC052": {
        "场景名称":   "人物·花卉场景链条柔美亮相",
        "场景类型":   "人物场景",
        "服装风格":   "碎花/纯色吊带裙或薄纱连衣裙，柔美少女感",
        "身体展示重点": "手臂，锁骨，腿部，柔美曲线",
        "着装禁忌":   "不要花纹太复杂与花卉背景混乱，不要厚重外套，不要运动装",
        "场景基底_英文": "young Asian woman standing in front of flower shop or flower field, holding phone with chain, chain color complementing floral tones, soft blurred floral background, feminine and elegant lifestyle, wearing floral or pastel slip dress or sheer dress showing arms, collarbone and leg silhouette, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC053": {
        "场景名称":   "人物·商场扶梯俯视链条亮相",
        "场景类型":   "人物场景",
        "服装风格":   "修身连衣裙或高腰短裙配上衣，俯视角度突出腰臀腿比例",
        "身体展示重点": "俯视角度下腰臀腿比例，整体修长感",
        "着装禁忌":   "不要宽松外套遮挡腰线，不要颜色与商场背景太相近",
        "场景基底_英文": "young Asian woman standing or leaning on escalator or railing in shopping mall, holding phone with chain toward camera, chain clearly draping, blurred mall interior background, slightly top-down angle showing slim proportions, trendy urban feel, wearing fitted bodycon dress or high-waist skirt with top highlighting waist-hip-leg ratio from above, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC054": {
        "场景名称":   "人物·雨天撑伞单手持机链条摇曳",
        "场景类型":   "人物场景",
        "服装风格":   "修身风衣/防水薄外套或修身连衣裙，雨天气质感",
        "身体展示重点": "腰部轮廓，腿部线条，雨天文艺气质",
        "着装禁忌":   "不要厚重臃肿外套，不要全身被雨衣遮挡，不要运动装",
        "场景基底_英文": "young Asian woman holding umbrella in rainy weather, other hand holding phone with decorative chain hanging naturally, blurred rainy city background, moody artistic atmosphere with rain bokeh, wearing fitted trench coat or slim rain jacket with visible waist and leg lines, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC055": {
        "场景名称":   "人物·地铁/站台通勤持机",
        "场景类型":   "人物场景",
        "服装风格":   "职场修身装——合身西装外套/修身衬衫配短裙或修身裤",
        "身体展示重点": "职场女性身材曲线，腰臀比，精致通勤感",
        "着装禁忌":   "不要过于宽松休闲服，不要荧光色服装，不要厚重长款大衣遮挡全身",
        "场景基底_英文": "young Asian woman standing on subway platform or inside metro car, holding phone with chain, chain hanging naturally, blurred subway background, stylish daily commute feel, wearing fitted office-style blazer or slim shirt with mini skirt or slim trousers showing professional yet sexy figure, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC056": {
        "场景名称":   "人物·侧脸轮廓光持机展示",
        "场景类型":   "人物场景",
        "服装风格":   "一字肩/斜肩或细肩带上衣，突出颈肩侧脸线条",
        "身体展示重点": "侧脸轮廓，颈部，肩线，锁骨",
        "着装禁忌":   "不要高领遮挡颈肩，不要宽松上衣，不要花纹复杂干扰侧颜美感",
        "场景基底_英文": "young Asian woman in full side profile, holding phone with chain in front of chest, chain draping down, rim light highlighting facial profile, clean simple background, elegant side profile aesthetic with chain, wearing off-shoulder or spaghetti strap top revealing neck, collarbone and shoulder lines, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC057": {
        "场景名称":   "人物·跳跃欢快动态链条飞扬",
        "场景类型":   "人物场景",
        "服装风格":   "短裙/吊带裙，跳跃中裙摆飞扬展现腿部",
        "身体展示重点": "腿部线条，跳跃中的身材比例，活力感",
        "着装禁忌":   "不要厚重外套，不要跳跃时走光，不要宽松裤装遮挡腿型",
        "场景基底_英文": "young Asian woman doing a light jump or tiptoe motion outdoors, holding phone with chain flying through the air, chain in energetic motion mid-jump, bright open background, youthful and cheerful energy, wearing mini skirt or slip dress with skirt lifting in the jump showing leg lines, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC058": {
        "场景名称":   "人物·双人闺蜜同框持机链条展示",
        "场景类型":   "人物场景",
        "服装风格":   "两人穿搭风格协调但有差异，各自修身穿搭展现各自特色",
        "身体展示重点": "两人整体气质，修长比例，闺蜜默契感",
        "着装禁忌":   "不要两人穿搭风格完全冲突，不要宽松服装遮挡身材，不要颜色搭配混乱",
        "场景基底_英文": "two young Asian women standing together or leaning close, each holding phone with decorative chain, chains clearly visible on both, matching energy and style, city or simple bokeh background, friendship sharing same-style accessory vibe, wearing coordinated yet individual fitted outfits — mini skirts or slim pants showing their figures, young Asian women, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC059": {
        "场景名称":   "人物·冬日保暖穿搭持机",
        "场景类型":   "人物场景",
        "服装风格":   "修身羊毛大衣/皮草领外套，内搭短裙或紧身裤，冬季性感感",
        "身体展示重点": "腿部线条（短裙内搭），腰部轮廓，冬季时髦感",
        "着装禁忌":   "不要过于臃肿羽绒服完全遮挡身材，不要厚重宽松完全没有腰线",
        "场景基底_英文": "young Asian woman wearing cozy winter coat or sweater outfit, holding phone with chain, chain creating visual contrast against winter clothes, outdoor winter or warm indoor background, stylish cold-weather look with chain as accessory highlight, wearing fitted wool coat with mini skirt or slim pants showing leg lines, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC060": {
        "场景名称":   "人物·镜前自拍角度模拟持机",
        "场景类型":   "人物场景",
        "服装风格":   "修身上衣/吊带/细肩带，自拍视角突出锁骨和上身曲线",
        "身体展示重点": "锁骨，上身曲线，脸部至上半身整体",
        "着装禁忌":   "不要宽松大码上衣遮挡上身线条，不要高领遮挡颈部，不要花纹复杂干扰自拍感",
        "场景基底_英文": "young Asian woman holding phone up in selfie pose toward camera, chain hanging down naturally from hand, phone and chain clearly visible with person's upper body in frame, intimate daily selfie vibe, wearing fitted crop top or spaghetti strap showing collarbone and upper body curves in selfie angle, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC061": {
        "场景名称":   "人物·艺术涂鸦墙背景持机",
        "场景类型":   "人物场景",
        "服装风格":   "街头风——紧身皮裤/格纹短裙配简洁上衣，个性感强",
        "身体展示重点": "腿部，腰臀，街头个性感",
        "着装禁忌":   "不要颜色与涂鸦背景完全融合，不要宽松卫衣穿搭失去个性感",
        "场景基底_英文": "young Asian woman standing in front of colorful street art graffiti wall, holding phone with metallic chain, chain contrasting with vibrant mural colors, edgy street art personality, wearing slim leather pants or plaid mini skirt with simple top showing waist and leg lines against the vivid backdrop, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    # ── SC062-SC071 户外场景 ──
    "SC062": {
        "场景名称":   "人物·海边沙滩链条阳光亮相",
        "场景类型":   "人物场景",
        "服装风格":   "比基尼/沙滩短裙/度假吊带裙，展现海边度假身材",
        "身体展示重点": "肩部，腿部，度假身材线条，海边度假气质",
        "着装禁忌":   "不要厚重服装，不要全身遮挡，不要与度假氛围格格不入",
        "场景基底_英文": "young Asian woman on sandy beach with ocean background, sea breeze in hair, holding phone with chain shining in bright sunlight, chain catching metallic glint, blurred blue sky and waves bokeh, vacation chic atmosphere, wearing bikini top with beach skirt or vacation slip dress showing sun-kissed shoulders and legs, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC063": {
        "场景名称":   "人物·山顶/高处俯瞰持机",
        "场景类型":   "人物场景",
        "服装风格":   "修身户外穿搭——紧身裤/运动短裙配轻薄外套，户外时髦感",
        "身体展示重点": "整体身材比例，俯瞰视角下的修长感，户外气质",
        "着装禁忌":   "不要过于臃肿户外装，不要宽松外套遮挡腰身",
        "场景基底_英文": "young Asian woman standing at mountain top, rooftop or high vantage point, holding phone with chain, expansive panoramic city or nature background in deep bokeh, chain clearly visible, elevated and liberating atmosphere, wearing slim outdoor outfit — fitted hiking pants or active skirt with light jacket showing figure, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC064": {
        "场景名称":   "人物·秋日落叶街道持机",
        "场景类型":   "人物场景",
        "服装风格":   "秋日修身穿搭——高腰短裙/修身毛衣裙，秋色与身材呼应",
        "身体展示重点": "腿部，腰部，秋日时髦感",
        "着装禁忌":   "不要过厚臃肿外套，不要与秋日暖色完全不搭的冷色调",
        "场景基底_英文": "young Asian woman walking on autumn street covered in fallen leaves, holding phone with chain, warm orange autumnal tones, chain colors complementing the autumn palette, blurred leaf bokeh background, cozy seasonal atmosphere, wearing fitted knit mini dress or high-waist skirt with sweater showing waist and leg lines in autumn warmth, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC065": {
        "场景名称":   "人物·樱花/花海户外盛放背景",
        "场景类型":   "人物场景",
        "服装风格":   "粉色/白色吊带裙或轻薄连衣裙，与樱花色系呼应",
        "身体展示重点": "手臂，锁骨，腿部，浪漫柔美身材气质",
        "着装禁忌":   "不要深色厚重服装，不要花纹与樱花背景混乱",
        "场景基底_英文": "young Asian woman standing under cherry blossom tree or in flower field, holding phone with chain, soft pink petals in blurred background, metallic chain contrasting with pastel floral tones, romantic spring atmosphere, wearing pink or white slip dress or light floral dress harmonizing with sakura backdrop, showing arms, collarbone and leg silhouette, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC066": {
        "场景名称":   "人物·骑行/单车旁持机",
        "场景类型":   "人物场景",
        "服装风格":   "运动短裙/自行车短裤配修身上衣，运动休闲感",
        "身体展示重点": "腿部线条，腰部，运动活力感",
        "着装禁忌":   "不要过于宽松运动装，不要车手服遮挡全身，不要链条被运动手套遮挡",
        "场景基底_英文": "young Asian woman cycling or standing next to bicycle, holding phone with chain hanging naturally, blurred outdoor road or park background, sporty casual chic energy with chain as styling detail, wearing fitted cycling shorts or sports mini skirt with crop top showing legs and waist, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC067": {
        "场景名称":   "人物·市集/露天集市逛街持机",
        "场景类型":   "人物场景",
        "服装风格":   "休闲时髦——短裙/吊带+薄外套，逛街轻松感",
        "身体展示重点": "腿部，腰部，休闲时髦感",
        "着装禁忌":   "不要颜色与市集背景完全融合，不要宽松棉麻长裙遮挡身材",
        "场景基底_英文": "young Asian woman browsing at weekend market or outdoor bazaar, holding phone with chain, colorful market stall background blurred, vibrant lifestyle feel with phone chain as fashion accent, wearing casual chic mini skirt or slip dress with light jacket showing legs and waist, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC068": {
        "场景名称":   "人物·城市天桥/过街桥持机",
        "场景类型":   "人物场景",
        "服装风格":   "都市修身穿搭——修身上衣配短裙或紧身裤，都市职场感",
        "身体展示重点": "腿部，腰部，都市女性气质",
        "着装禁忌":   "不要过于宽松休闲服，不要运动装，不要厚重外套",
        "场景基底_英文": "young Asian woman standing on city overpass or pedestrian bridge, holding phone with chain, city street and traffic lights bokeh below, urban rhythm atmosphere with chain as key detail, wearing fitted city-chic outfit — slim pants or mini skirt with fitted top showing urban feminine figure, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC069": {
        "场景名称":   "人物·户外草坪野餐持机",
        "场景类型":   "人物场景",
        "服装风格":   "碎花连衣裙/格纹短裙配上衣，野餐清新感",
        "身体展示重点": "坐姿曲线，腿部，野餐度假氛围",
        "着装禁忌":   "不要厚重外套，不要深色暗沉服装，不要过于严肃的职场装",
        "场景基底_英文": "young Asian woman sitting or lying on picnic blanket on green lawn, holding phone with chain glinting in sunlight, picnic props around, blurred green grass background, carefree outdoor lifestyle, wearing floral dress or plaid mini skirt with top showing a relaxed natural silhouette on the grass, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC070": {
        "场景名称":   "人物·户外楼梯/台阶侧坐持机",
        "场景类型":   "人物场景",
        "服装风格":   "短裙/牛仔短裤配上衣，台阶坐姿展现腿部",
        "身体展示重点": "腿部线条，坐姿臀部曲线，随性街头感",
        "着装禁忌":   "不要坐姿走光，不要宽松长裙遮挡腿型",
        "场景基底_英文": "young Asian woman casually sitting sideways on outdoor stone steps or concrete stairs, natural relaxed pose, holding phone with chain draping beside leg, blurred street or building background, authentic street life feel, wearing denim shorts or mini skirt with fitted top showing leg lines in relaxed sitting pose, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC071": {
        "场景名称":   "人物·户外自拍手持镜头前推",
        "场景类型":   "人物场景",
        "服装风格":   "修身上衣/吊带/细肩带，自拍角度突出上身曲线",
        "身体展示重点": "锁骨，肩膀，上身线条，自拍亲近感",
        "着装禁忌":   "不要宽松大码上衣，不要高领遮挡颈部",
        "场景基底_英文": "young Asian woman outdoors pushing phone with chain toward camera in selfie gesture, chain naturally draping as arm extends, phone chain and person's face/upper body in frame, outdoor blurred background, authentic selfie moment, wearing fitted crop top or spaghetti strap showing collarbone and upper body curves in selfie angle, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    # ── SC072-SC091 lifestyle场景 ──
    "SC072": {
        "场景名称":   "人物·健身房镜前持机自拍",
        "场景类型":   "人物场景",
        "服装风格":   "运动内衣/Sports bra配瑜伽裤，展现健身身材",
        "身体展示重点": "腰腹部，健身身材线条，侧腰曲线",
        "着装禁忌":   "不要宽松健身外套遮挡身材，不要棉T配棉裤，不要过于暴露引发争议",
        "场景基底_英文": "young Asian woman in gym workout outfit standing in front of full-length mirror, holding phone with chain in mirror selfie pose, chain clearly visible in reflection, gym equipment blurred background, sporty chic energy, wearing sports bra and yoga pants or fitted gym set showing toned midriff and curves, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC073": {
        "场景名称":   "人物·健身房哑铃区休息持机",
        "场景类型":   "人物场景",
        "服装风格":   "修身运动套装/运动内衣配紧身裤，健身间隙展现身材",
        "身体展示重点": "坐姿腿部线条，腰腹部，运动紧致感",
        "着装禁忌":   "不要宽松运动套装，不要全程遮挡身材，不要外套完全遮挡",
        "场景基底_英文": "young Asian woman sitting on gym bench during workout rest, holding phone with chain naturally draping, athletic outfit showing body curves, blurred dumbbell rack background, refined active lifestyle, wearing fitted gym set or sports bra with high-waist leggings showing toned legs and waist, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC074": {
        "场景名称":   "人物·瑜伽垫旁瑜伽裤持机",
        "场景类型":   "人物场景",
        "服装风格":   "瑜伽裤配运动内衣/修身运动上衣，展现腿部和腰腹",
        "身体展示重点": "腿部曲线，腰腹，柔软健康体态",
        "着装禁忌":   "不要宽松上衣遮挡腰腹，不要运动外套遮挡全身",
        "场景基底_英文": "young Asian woman in yoga pants sitting or standing near yoga mat, holding phone with chain, metallic chain contrasting with smooth yoga pants fabric, blurred yoga studio or indoor background, mindful healthy lifestyle, wearing high-waist yoga pants with fitted sports bra or crop top showing waist, hips and leg silhouette, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC075": {
        "场景名称":   "人物·瑜伽裤户外伸展动作持机",
        "场景类型":   "人物场景",
        "服装风格":   "瑜伽裤配运动内衣，户外伸展展现身材柔韧性",
        "身体展示重点": "全身柔韧比例，腿部，腰腹，伸展美感",
        "着装禁忌":   "不要厚重外套，不要遮挡伸展动作的身体线条",
        "场景基底_英文": "young Asian woman in yoga pants doing stretch pose outdoors in park, holding or wrist-wearing phone with chain in dynamic position, chain in natural motion, blurred green nature background, free active energy, wearing high-waist yoga leggings with sports bra showing flexible full-body silhouette and curves in stretch pose, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC076": {
        "场景名称":   "人物·迷你裙街头行走持机",
        "场景类型":   "人物场景",
        "服装风格":   "迷你裙配修身上衣/吊带，展现腿部，短裙随步伐摆动",
        "身体展示重点": "腿部线条，腰臀比，行走动态美",
        "着装禁忌":   "不要短裙太短引发不适，不要搭配宽松上衣破坏比例",
        "场景基底_英文": "young Asian woman in mini skirt walking on fashionable street, holding phone with swaying chain, chain and mini skirt creating trendy girl aesthetic, blurred urban street background, chic street style energy, wearing fitted mini skirt with crop top or camisole revealing waist and legs in motion, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC077": {
        "场景名称":   "人物·迷你裙咖啡厅坐姿持机",
        "场景类型":   "人物场景",
        "服装风格":   "迷你裙配精致上衣/丝绸衬衫，坐姿展现腿部，精致约会感",
        "身体展示重点": "腿部，坐姿身材曲线，精致优雅气质",
        "着装禁忌":   "不要坐姿走光，不要与咖啡厅暖色调冲突，不要运动装",
        "场景基底_英文": "young Asian woman in mini skirt sitting elegantly cross-legged at cafe, holding phone with chain draping on table edge, warm cafe bokeh background, sophisticated urban girl aesthetic, wearing mini skirt with silk blouse or fitted top showing elegant leg lines and feminine silhouette in cafe setting, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC078": {
        "场景名称":   "人物·迷你裙户外台阶坐姿",
        "场景类型":   "人物场景",
        "服装风格":   "迷你裙配上衣，台阶坐姿展现腿部，阳光随性感",
        "身体展示重点": "腿部线条，台阶坐姿自然曲线",
        "着装禁忌":   "不要坐姿走光，不要厚重外套破坏轻盈感",
        "场景基底_英文": "young Asian woman in mini skirt sitting naturally on outdoor stone steps, holding phone with chain draping beside leg, sunlight, blurred urban or architectural background, effortlessly chic street style, wearing mini skirt with fitted crop top or camisole showing natural leg and waist lines in relaxed outdoor sitting pose, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC079": {
        "场景名称":   "人物·户外跑步后手持机",
        "场景类型":   "人物场景",
        "服装风格":   "运动短裙/紧身跑步短裤配运动上衣，展现跑步后身材",
        "身体展示重点": "腿部，腰腹，跑步后自然健康感",
        "着装禁忌":   "不要过于宽松运动装，不要全身遮挡，不要跑后过于狼狈",
        "场景基底_英文": "young Asian woman after outdoor run on road or park path, natural breathing post-workout, holding phone with chain in gentle motion, athletic outfit, blurred green outdoor background, authentic active lifestyle, wearing running shorts or sports mini skirt with fitted athletic top showing toned legs and waist post-run, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC080": {
        "场景名称":   "人物·跑步机上持机动态",
        "场景类型":   "人物场景",
        "服装风格":   "运动内衣配紧身跑步裤，跑步机上展现健身身材",
        "身体展示重点": "跑步动态腿部，腰腹部线条，运动活力感",
        "着装禁忌":   "不要宽松运动服遮挡身材，不要厚重外套",
        "场景基底_英文": "young Asian woman jogging on treadmill, holding phone with chain swaying rhythmically with running motion, gym background blurred, modern multitasking active lifestyle, wearing sports bra with high-waist running tights showing toned midriff, legs and athletic curves in motion, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC081": {
        "场景名称":   "人物·小轿车内驾驶座持机",
        "场景类型":   "人物场景",
        "服装风格":   "修身通勤装/连衣裙，车内坐姿展现上身曲线",
        "身体展示重点": "上身曲线，锁骨，都市精致感",
        "着装禁忌":   "不要宽松运动服，不要厚重外套，不要颜色过暗与车内融合",
        "场景基底_英文": "young Asian woman in car driver seat holding phone with chain hanging naturally near center console, blurred city scenery through window, urban commute daily life feel, wearing fitted dress or slim office outfit with visible collarbone and upper body curves in car seat, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC082": {
        "场景名称":   "人物·小轿车副驾座窗边自拍",
        "场景类型":   "人物场景",
        "服装风格":   "修身上衣/吊带/细肩带，车内自拍展现上身和锁骨",
        "身体展示重点": "锁骨，肩膀，上身线条，车内性感气质",
        "着装禁忌":   "不要宽松服装遮挡上身线条，不要颜色过重与车内融合",
        "场景基底_英文": "young Asian woman sitting in car passenger seat leaning toward window, holding phone with chain in selfie position, chain catching metallic sheen from window side lighting, blurred scenery outside, road trip chic feeling, wearing fitted camisole or off-shoulder top revealing collarbone, shoulders and upper body curves in car selfie, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC083": {
        "场景名称":   "人物·车内后座链条展示",
        "场景类型":   "人物场景",
        "服装风格":   "优雅连衣裙或修身套装，后座坐姿展现精致出行感",
        "身体展示重点": "坐姿腿部，上身曲线，精致出行气质",
        "着装禁忌":   "不要宽松休闲服，不要颜色过暗",
        "场景基底_英文": "young Asian woman in back seat of car, holding phone with chain resting on lap naturally, soft side light from window, blurred city or landscape through car window, refined travel lifestyle, wearing elegant fitted dress or tailored suit showing polished leg and upper body lines in car back seat, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC084": {
        "场景名称":   "人物·健身房出入口持机亮相",
        "场景类型":   "人物场景",
        "服装风格":   "修身运动套装/Sports bra配高腰瑜伽裤，展现健身女孩气质",
        "身体展示重点": "整体健身身材比例，腰腹，精致运动感",
        "着装禁忌":   "不要宽松健身外套完全遮挡，不要颜色与健身房背景融合",
        "场景基底_英文": "young Asian woman at gym entrance with gym bag on shoulder, holding phone with chain clearly visible, blurred gym glass door or logo background, polished fitness girl aesthetic, wearing fitted athletic set or sports bra with high-waist leggings showing toned athletic figure, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC085": {
        "场景名称":   "人物·瑜伽裤镜前全身展示",
        "场景类型":   "人物场景",
        "服装风格":   "瑜伽裤配运动内衣，镜前全身展现健康美好身材",
        "身体展示重点": "全身比例，腿部，腰腹，健康自信气质",
        "着装禁忌":   "不要宽松上衣遮挡腰腹，不要镜面让服装不清晰",
        "场景基底_英文": "young Asian woman in yoga pants full body pose in front of floor mirror, holding phone with chain clearly visible, full proportions on display, clean background, body confidence and stylish healthy lifestyle, wearing high-waist yoga leggings with sports bra or fitted crop top showing full toned figure — waist, hips and legs, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC086": {
        "场景名称":   "人物·跑步道路侧面动态",
        "场景类型":   "人物场景",
        "服装风格":   "运动短裙/紧身跑步裤配运动上衣，侧面动态展现腿部",
        "身体展示重点": "侧面跑步腿部线条，运动曲线，动态美",
        "着装禁忌":   "不要宽松运动装模糊腿型，不要颜色过暗",
        "场景基底_英文": "young Asian woman running from side angle on city track or park path, holding phone with chain flying in motion, athletic outfit visible, speed-blurred road or green background, youthful energetic vibe, wearing fitted running shorts or sport mini skirt with athletic top showing leg lines and curves in running motion from the side, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC087": {
        "场景名称":   "人物·迷你裙商场购物持机",
        "场景类型":   "人物场景",
        "服装风格":   "迷你裙配精致上衣/购物装扮，商场逛街展现时髦感",
        "身体展示重点": "腿部线条，购物时髦感，腰臀比",
        "着装禁忌":   "不要宽松购物袋装扮，不要服装与商场灯光冲突",
        "场景基底_英文": "young Asian woman in mini skirt shopping in mall, holding phone with chain, shopping bag in other hand, chain clearly visible, blurred glamorous mall lighting background, stylish shopping girl aesthetic, wearing mini skirt with chic fitted top or blazer showing fashionable leg lines and waist while shopping, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC088": {
        "场景名称":   "人物·车内等待低头刷机链条垂落",
        "场景类型":   "人物场景",
        "服装风格":   "修身通勤装/连衣裙，车内低头展现上身曲线",
        "身体展示重点": "上身曲线，低头颈肩线条，精致日常感",
        "着装禁忌":   "不要宽松休闲服，不要低头角度过大让脸消失",
        "场景基底_英文": "young Asian woman in car looking down at phone, chain hanging naturally onto lap from hand, side rim light or interior car light highlighting chain metallic texture, intimate fragmented time aesthetic, wearing fitted dress or slim top with visible neckline and shoulder curves in car interior light, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC089": {
        "场景名称":   "人物·健身后更衣室持机出镜",
        "场景类型":   "人物场景",
        "服装风格":   "健身后换上修身休闲装/运动上衣，展现健身后状态",
        "身体展示重点": "健身后精致状态，腰部，运动满足感",
        "着装禁忌":   "不要更衣室背景有不雅元素，不要服装过于暴露",
        "场景基底_英文": "young Asian woman post-workout in gym locker room, holding phone with chain, chain contrasting with clean locker room background, satisfied and polished post-gym energy, wearing fitted casual wear or athletic top after workout showing toned arms and confident figure, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC090": {
        "场景名称":   "人物·迷你裙户外旋转动态",
        "场景类型":   "人物场景",
        "服装风格":   "飘逸迷你裙/A字裙，旋转时裙摆飞扬展现腿部",
        "身体展示重点": "旋转动态腿部，裙摆飞扬，腰部，青春活力感",
        "着装禁忌":   "不要旋转走光，不要厚重服装破坏飘逸感，不要短裙太短",
        "场景基底_英文": "young Asian woman in mini skirt doing a light spin outdoors, skirt lifting in motion, holding phone with chain flying outward, bright sunny outdoor background bokeh, youthful free-spirited chic, wearing flared mini skirt or A-line dress that lifts beautifully showing legs in spin while chain flies outward, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
    "SC091": {
        "场景名称":   "人物·车内挂链手机车载支架取机",
        "场景类型":   "人物场景",
        "服装风格":   "修身通勤装，取机动作展现手臂和上身线条",
        "身体展示重点": "手臂，上身曲线，取机动作自然感",
        "着装禁忌":   "不要宽松外套遮挡手臂，不要服装颜色与车内融合",
        "场景基底_英文": "young Asian woman's hand reaching to take phone with chain from car mount holder, chain swinging naturally in action, clean car interior, natural light from window, authentic daily driving lifestyle moment, wearing fitted sleeve or sleeveless top revealing arm curves and upper body in natural reaching gesture, young Asian woman, fashionable sexy, natural curves, natural makeup, 20s",
    },
}

# ─────────────────────────────────────────────
# PASS 2 & 3: Fetch all records, then update
# ─────────────────────────────────────────────
print("\n=== PASS 2+3: Fetch records and apply updates ===")
records = fc.list_records(SCENE_TABLE)
print(f"Total records: {len(records)}")

target_codes = set(SCENE_DATA.keys())
to_update = {}
for r in records:
    fields = r.get('fields', {})
    code = fields.get('场景编号', '')
    if code in target_codes:
        to_update[code] = r['record_id']

print(f"Matched {len(to_update)} target records\n")

ok_count = 0
fail_count = 0
for code, rec_id in sorted(to_update.items()):
    updates = dict(SCENE_DATA[code])  # copy
    try:
        fc.update_record(SCENE_TABLE, rec_id, updates)
        print(f"  OK  {code} -> {updates.get('场景名称', '')}")
        ok_count += 1
    except Exception as e:
        print(f"  FAIL {code}: {e}")
        fail_count += 1
    time.sleep(0.4)

print(f"\n=== Done: {ok_count} OK, {fail_count} FAIL ===")
