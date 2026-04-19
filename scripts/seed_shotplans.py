"""
批量插入拍摄方案表（表9）新 ShotPlan 记录。
运行：cd middleware && python ../scripts/seed_shotplans.py
"""
import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "middleware"))
from adapters.feishu import FeishuClient  # noqa: E402
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "middleware", ".env"))
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

TABLE_ID = "tbl0xCaqru1TjwzK"

# ---------------------------------------------------------------------------
# ShotPlan 数据
# ---------------------------------------------------------------------------
SHOTPLANS = [
    # SP004 ──────────────────────────────────────────────────────────────────
    {
        "方案编号": "SP004",
        "方案名称": "穿搭搭配展示",
        "适用内容形态": ["图片"],
        "适用内容类型": ["穿搭搭配"],
        "适用品类": ["手机壳", "手机链"],
        "禁止重复镜头": "避免连续同款平铺、重复挂置姿态和相同服装搭配背景。",
        "动作变化要求": "需要覆盖平铺、手持、挂置、细节特写等不同呈现方式，保证搭配关系变化明显。",
        "是否启用": "启用",
        "节点数量": 5,
        "角色序列": json.dumps([
            {
                "index": 1,
                "zh": "整体穿搭平铺俯拍，展示产品与服装组合的色彩搭配关系，{scene_description}",
                "en": "Flat lay overhead shot of product styled with outfit, showing color coordination, {scene_description}",
            },
            {
                "index": 2,
                "zh": "手持产品近景，突出产品与服装材质/色彩的呼应，自然持握姿态，{scene_description}",
                "en": "Close-up hand-holding product alongside outfit, highlighting material and color echo, {scene_description}",
            },
            {
                "index": 3,
                "zh": "产品悬挂/挂置于穿搭中的自然使用状态，展示与整体着装的协调感，{scene_description}",
                "en": "Product naturally worn/hung in outfit context, showing harmony with full look, {scene_description}",
            },
            {
                "index": 4,
                "zh": "局部精致细节特写，聚焦产品与服装搭配的亮点交接处，{scene_description}",
                "en": "Detail close-up at the intersection of product and outfit, showcasing styling highlight, {scene_description}",
            },
            {
                "index": 5,
                "zh": "同款产品搭配不同风格服装的对比组合，展示百搭性，{scene_description}",
                "en": "Same product styled with different outfit aesthetics side by side, showing versatility, {scene_description}",
            },
        ], ensure_ascii=False),
        "备注": "适用于穿搭搭配类内容，突出产品与穿搭的融合感",
    },

    # SP005 ──────────────────────────────────────────────────────────────────
    {
        "方案编号": "SP005",
        "方案名称": "日常生活场景",
        "适用内容形态": ["图片"],
        "适用内容类型": ["场景展示", "日常vlog", "好物分享"],
        "适用品类": ["手机壳", "手机链", "充电宝"],
        "禁止重复镜头": "避免连续同角度正面主图、重复道具摆位和相同景别输出。",
        "动作变化要求": "每套方案至少覆盖 2 种以上构图/摆放/持握变化，避免整组画面节奏单一。",
        "是否启用": "启用",
        "节点数量": 4,
        "角色序列": json.dumps([
            {
                "index": 1,
                "zh": "宽景带产品，展示产品自然融入生活场景的全貌，环境感与生活质感兼备，{scene_description}",
                "en": "Wide lifestyle shot with product naturally integrated into the scene, capturing environment and life quality, {scene_description}",
            },
            {
                "index": 2,
                "zh": "中近景使用状态，展示产品在场景中的实际使用/放置方式，真实生活感，{scene_description}",
                "en": "Medium close-up of product in active use or natural placement within scene, authentic lifestyle feel, {scene_description}",
            },
            {
                "index": 3,
                "zh": "生活道具细节特写，产品与场景道具的细节互动，氛围感十足，{scene_description}",
                "en": "Detail close-up of product interacting with scene props, atmosphere-rich composition, {scene_description}",
            },
            {
                "index": 4,
                "zh": "情绪氛围收尾，带有光影/氛围感的整体构图，情绪饱满，余韵悠长，{scene_description}",
                "en": "Mood-closing shot with strong lighting atmosphere, emotionally resonant wide or mid composition, {scene_description}",
            },
        ], ensure_ascii=False),
        "备注": "通用生活场景方案，强调真实感和氛围感",
    },

    # SP006 ──────────────────────────────────────────────────────────────────
    {
        "方案编号": "SP006",
        "方案名称": "节日限定礼品",
        "适用内容形态": ["图片"],
        "适用内容类型": ["节日/活动限定"],
        "适用品类": ["手机壳", "手机链", "充电宝"],
        "禁止重复镜头": "避免连续同角度正面主图、重复道具摆位和相同景别输出。",
        "动作变化要求": "每套方案至少覆盖 2 种以上构图/摆放/持握变化，避免整组画面节奏单一。",
        "是否启用": "启用",
        "节点数量": 4,
        "角色序列": json.dumps([
            {
                "index": 1,
                "zh": "节日礼盒全景，产品搭配包装/丝带/节日元素的精致整体展示，仪式感满满，{scene_description}",
                "en": "Full gift display with product alongside packaging, ribbon and seasonal elements, premium presentation, {scene_description}",
            },
            {
                "index": 2,
                "zh": "礼品仪式感特写，近距离展示产品精致细节与礼品包装工艺，突出高级感，{scene_description}",
                "en": "Close-up of product and gift wrapping craftsmanship, emphasizing premium quality and thoughtfulness, {scene_description}",
            },
            {
                "index": 3,
                "zh": "节日场景自然融入，产品与花束/彩灯/节日道具自然搭配，氛围温暖浪漫，{scene_description}",
                "en": "Product naturally integrated into holiday scene with flowers, lights or seasonal props, warm and romantic, {scene_description}",
            },
            {
                "index": 4,
                "zh": "送礼收礼情感瞬间，展现送礼/惊喜场景中的情感温度与人物互动，{scene_description}",
                "en": "Emotional gifting moment shot capturing the warmth of giving/receiving, human connection, {scene_description}",
            },
        ], ensure_ascii=False),
        "备注": "节日氛围感强，突出礼品属性和情感价值",
    },

    # SP007 ──────────────────────────────────────────────────────────────────
    {
        "方案编号": "SP007",
        "方案名称": "教程攻略图解",
        "适用内容形态": ["图片"],
        "适用内容类型": ["选购攻略/使用教程", "深度测评"],
        "适用品类": ["手机壳", "手机链", "充电宝"],
        "禁止重复镜头": "避免连续同角度正面主图、重复道具摆位和相同景别输出。",
        "动作变化要求": "每套方案至少覆盖 2 种以上构图/摆放/持握变化，避免整组画面节奏单一。",
        "是否启用": "启用",
        "节点数量": 5,
        "角色序列": json.dumps([
            {
                "index": 1,
                "zh": "产品全貌总览，正面清晰展示整体外观，可配数字/文字标注各功能区域，{scene_description}",
                "en": "Full product overview with clear front view, optional numbered annotations for key functional areas, {scene_description}",
            },
            {
                "index": 2,
                "zh": "关键功能区特写，聚焦核心功能部位的精细结构，突出设计亮点与做工，{scene_description}",
                "en": "Key functional zone close-up, focusing on core feature area design and craftsmanship detail, {scene_description}",
            },
            {
                "index": 3,
                "zh": "安装/使用步骤演示，清晰呈现操作步骤或使用方法，手部动作自然流畅，{scene_description}",
                "en": "Installation/usage step demonstration with clear hand action, showing natural operation flow, {scene_description}",
            },
            {
                "index": 4,
                "zh": "使用效果展示，清晰对比使用前后或展示最终效果，突出产品价值，{scene_description}",
                "en": "Usage effect demonstration, clear before/after comparison or final result showcase highlighting product value, {scene_description}",
            },
            {
                "index": 5,
                "zh": "适用场景/人群收尾，展示产品最适合的使用场景与目标人群状态，{scene_description}",
                "en": "Target use case and audience closing shot, showing product in ideal scenario with fitting user profile, {scene_description}",
            },
        ], ensure_ascii=False),
        "备注": "攻略测评类，信息清晰优先，逻辑性强",
    },

    # SP008 ──────────────────────────────────────────────────────────────────
    {
        "方案编号": "SP008",
        "方案名称": "新品发布首秀",
        "适用内容形态": ["图片"],
        "适用内容类型": ["新品发布"],
        "适用品类": ["手机壳", "手机链", "充电宝"],
        "禁止重复镜头": "避免连续同角度正面主图、重复道具摆位和相同景别输出。",
        "动作变化要求": "每套方案至少覆盖 2 种以上构图/摆放/持握变化，避免整组画面节奏单一。",
        "是否启用": "启用",
        "节点数量": 4,
        "角色序列": json.dumps([
            {
                "index": 1,
                "zh": "主体发布全景，产品正面居中，干净简洁背景，光线强调质感，隆重登场，{scene_description}",
                "en": "Hero launch shot, product front-center on clean minimal background, lighting emphasizes texture, grand debut feel, {scene_description}",
            },
            {
                "index": 2,
                "zh": "设计亮点特写，聚焦新品最核心的设计创新点与工艺亮点，视觉冲击强，{scene_description}",
                "en": "Design highlight close-up focusing on the key innovation or craftsmanship feature of the new product, strong visual impact, {scene_description}",
            },
            {
                "index": 3,
                "zh": "首秀使用场景，新品在理想使用场景中的首次亮相，展示真实使用状态的惊艳感，{scene_description}",
                "en": "First-use lifestyle scene, new product making its debut in ideal real-world setting, showcasing its wow factor, {scene_description}",
            },
            {
                "index": 4,
                "zh": "系列/配色组合，新品全系列配色或系列产品的整体排列展示，彰显产品矩阵，{scene_description}",
                "en": "Full colorway or product family lineup arrangement, showcasing the complete new product range, {scene_description}",
            },
        ], ensure_ascii=False),
        "备注": "新品上市首发，强调仪式感和设计亮点",
    },

    # SP009 ──────────────────────────────────────────────────────────────────
    {
        "方案编号": "SP009",
        "方案名称": "种草极简风",
        "适用内容形态": ["图片"],
        "适用内容类型": ["种草推荐", "好物分享"],
        "适用品类": ["手机壳", "手机链", "充电宝"],
        "禁止重复镜头": "避免连续纯背景主图、重复手持角度和同构图裁切。",
        "动作变化要求": "从静态主图到手持细节再到创意局部，至少包含 2 种不同持握/摆放状态。",
        "是否启用": "启用",
        "节点数量": 4,
        "角色序列": json.dumps([
            {
                "index": 1,
                "zh": "极简背景主体图，产品单独居中于纯净背景，强调产品本身的设计美感，{scene_description}",
                "en": "Minimal background hero shot, product centered on pure clean background, emphasizing inherent design beauty, {scene_description}",
            },
            {
                "index": 2,
                "zh": "产品肌理近拍，极近距离捕捉材质肌理与光泽，展现高级质感，{scene_description}",
                "en": "Macro texture close-up capturing material grain and sheen at very close range, conveying premium quality, {scene_description}",
            },
            {
                "index": 3,
                "zh": "单手手持上镜，产品轻握于手中，手部姿态优雅自然，突出持握感和便携性，{scene_description}",
                "en": "One-hand held product shot, elegant natural grip posture highlighting ergonomics and portability, {scene_description}",
            },
            {
                "index": 4,
                "zh": "产品局部创意构图，打破常规视角的局部裁剪或几何构图，艺术感种草，{scene_description}",
                "en": "Creative partial composition with unconventional cropping or geometric framing, artistic and aspirational, {scene_description}",
            },
        ], ensure_ascii=False),
        "备注": "适合极简/高冷/高级感内容风格",
    },
]


def main():
    f = FeishuClient(
        os.environ["LARK_APP_ID"],
        os.environ["LARK_APP_SECRET"],
        os.environ["LARK_BASE_TOKEN"],
    )

    # 查现有编号，避免重复插入
    existing = f.list_records(TABLE_ID)
    existing_codes = set()
    for r in existing:
        for cell in (r["fields"].get("方案编号") or []):
            if isinstance(cell, dict):
                existing_codes.add(cell.get("text", ""))
            else:
                existing_codes.add(str(cell))
    logging.info("现有方案编号: %s", existing_codes)

    inserted = 0
    for sp in SHOTPLANS:
        code = sp["方案编号"]
        if code in existing_codes:
            logging.info("[跳过] %s 已存在", code)
            continue
        record_id = f.create_record(TABLE_ID, sp)
        logging.info("[创建] %s %s → %s", code, sp["方案名称"], record_id)
        inserted += 1

    logging.info("完成：新插入 %d 条，跳过 %d 条", inserted, len(SHOTPLANS) - inserted)


if __name__ == "__main__":
    main()
