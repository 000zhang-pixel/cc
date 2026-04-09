import json, subprocess, os, time

BASE_TOKEN = "Ei9jbcsHianwvvsn5xScH8ANnnb"
TABLE_ID = "tbliWlwiyA4sppgY"
LARK_CLI = r"C:\Users\carson\AppData\Roaming\npm\lark-cli.cmd"

scenes = [
    {
        "场景编号": "SC029",
        "场景名称": "手持手机挂链出街",
        "场景类型": "生活场景",
        "场景描述_中文": "女生单手持手机自然下垂，手机链垂坠摇晃，街头背景虚化，传递随性日常的时髦感",
        "场景基底_英文": "young woman holding phone with hanging chain strap, street background bokeh, casual chic",
        "风格基调词": "街头随性,日常时髦,真实感",
        "排除描述": "避免摆拍感过重，不要纯白背景，不要产品浮空",
        "适用品类": "手机链",
        "适用平台": "得物",
        "是否启用": True,
        "权重": 9,
        "景别": "中景/近景",
        "拍摄角度": "平视/略俯",
        "人物类型": "真人出镜",
        "姿态倾向": "自然持机",
        "性别倾向": "女",
        "年龄段": "18-28岁",
        "备注": "手机链专属：手持手机场景是链条最自然的展示方式"
    },
    {
        "场景编号": "SC030",
        "场景名称": "腕部链条手持近景",
        "场景类型": "产品展示",
        "场景描述_中文": "手腕自然弯曲，手机链挂在手腕或手指上，链条垂坠形态优美，侧光营造金属光泽感，保持链条整体可见",
        "场景基底_英文": "hand and wrist with decorative phone chain, natural drape, soft side lighting, metallic gloss, full chain visible",
        "风格基调词": "精致细腻,金属光感,高质感",
        "排除描述": "不要过度PS，不要假手模型，不要黑暗背景，不要极近裁切导致链条不完整",
        "适用品类": "手机链",
        "适用平台": "得物",
        "是否启用": True,
        "权重": 10,
        "景别": "近景",
        "光源类型": "侧光",
        "拍摄角度": "45度侧俯",
        "人物类型": "局部入镜（手部）",
        "备注": "手机链专属核心场景：手部持机近景展示链条垂坠形态与质感，保持链条整体可见"
    },
    {
        "场景编号": "SC031",
        "场景名称": "穿搭全身链条点睛",
        "场景类型": "穿搭场景",
        "场景描述_中文": "全身或半身穿搭照，手机挂在身侧或手持，链条作为穿搭细节自然呈现，时装感强",
        "场景基底_英文": "full-body or half-body outfit shot, phone chain as styling accessory detail, fashion editorial feel",
        "风格基调词": "时装感,搭配感,整体美学",
        "排除描述": "不要遮挡链条，不要把链条放在主体之外，避免过于生活随拍",
        "适用品类": "手机链",
        "适用平台": "得物",
        "是否启用": True,
        "权重": 8,
        "景别": "全景/中景",
        "拍摄角度": "平视",
        "人物类型": "真人出镜",
        "姿态倾向": "站立展示",
        "性别倾向": "女",
        "年龄段": "18-28岁",
        "备注": "手机链专属：穿搭整体感展示，链条作为点睛单品"
    },
    {
        "场景编号": "SC032",
        "场景名称": "链条光影桌面平铺",
        "场景类型": "静物展示",
        "场景描述_中文": "手机链铺展在浅色桌面或大理石台面上，利用窗边自然光制造链条阴影与光斑，完整展示链条形态，极简高级",
        "场景基底_英文": "phone chain arranged on marble or light wood surface, natural window light creating shadows and highlights, full chain visible, minimalist luxury",
        "风格基调词": "极简高级,光影美学,材质展示",
        "排除描述": "不要杂乱道具，不要人工打光过重，不要颜色过多，不要截取局部导致链条不完整",
        "适用品类": "手机链",
        "适用平台": "得物",
        "是否启用": True,
        "权重": 8,
        "景别": "近景",
        "光源类型": "自然光（窗边）",
        "拍摄角度": "俯拍",
        "人物类型": "无人物",
        "备注": "手机链专属：产品静物平铺场景，强调材质光影美学，整条链条完整展示"
    },
    {
        "场景编号": "SC033",
        "场景名称": "咖啡厅手机链随拍",
        "场景类型": "生活场景",
        "场景描述_中文": "咖啡厅木质桌面，手持咖啡杯的另一只手轻搭手机，链条自然垂落，背景奶油色调柔和虚化",
        "场景基底_英文": "cafe wooden table, hand resting on phone with hanging chain, warm cream toned background, lifestyle",
        "风格基调词": "奶油感,生活质感,精致日常",
        "排除描述": "不要拥挤背景，不要强对比打光，避免链条被遮挡",
        "适用品类": "手机链",
        "适用平台": "得物",
        "是否启用": True,
        "权重": 8,
        "景别": "近景",
        "光源类型": "自然光",
        "拍摄角度": "45度俯拍",
        "人物类型": "局部入镜（手部）",
        "备注": "手机链专属：咖啡厅是链条日常使用感最自然的展示场景"
    },
    {
        "场景编号": "SC034",
        "场景名称": "礼盒开箱仪式感",
        "场景类型": "开箱场景",
        "场景描述_中文": "精致礼盒半开状态，手机链盘卷其中，背景干净，道具简约，整体传递高级礼物仪式感",
        "场景基底_英文": "elegant gift box half-opened with phone chain inside, clean background, gift unboxing ceremony feel",
        "风格基调词": "仪式感,礼物质感,精致包装",
        "排除描述": "不要凌乱，不要快递填充物入镜，不要廉价感包装",
        "适用品类": "手机链",
        "适用平台": "得物",
        "是否启用": True,
        "权重": 7,
        "景别": "近景",
        "光源类型": "柔光",
        "拍摄角度": "45度俯拍/平拍",
        "人物类型": "可无人物",
        "备注": "手机链专属：礼物场景，节日前后重点推送"
    },
    {
        "场景编号": "SC035",
        "场景名称": "多链叠戴手持对比",
        "场景类型": "产品对比",
        "场景描述_中文": "一只手持多部挂不同链条的手机，或手腕并排展示多条链条，突出款式差异与叠搭层次感",
        "场景基底_英文": "hand holding multiple phones each with different chain styles, or wrist with layered chains, showcase variety",
        "风格基调词": "对比展示,多款丰富,选择感",
        "排除描述": "不要过于混乱，确保每条链条都能看清楚，避免遮挡",
        "适用品类": "手机链",
        "适用平台": "得物",
        "是否启用": True,
        "权重": 7,
        "景别": "近景",
        "拍摄角度": "平视/略俯",
        "人物类型": "局部入镜（手部）",
        "备注": "手机链专属：多款对比场景，适合刺激连带购买"
    },
    {
        "场景编号": "SC036",
        "场景名称": "链条整体悬挂展示",
        "场景类型": "产品展示",
        "场景描述_中文": "手持或悬挂状态下展示完整链条，精准控制光线展现金属质感与工艺细节，保持链条整体形态清晰可见",
        "场景基底_英文": "full phone chain hanging or held up, controlled lighting to reveal metallic texture and craftsmanship, complete chain visible",
        "风格基调词": "工艺感,材质细节,品质背书",
        "排除描述": "不要失焦，不要过曝，不要背景干扰，不要截取导致链条不完整",
        "适用品类": "手机链",
        "适用平台": "得物",
        "是否启用": True,
        "权重": 8,
        "景别": "近景",
        "光源类型": "环形灯/侧光",
        "拍摄角度": "平拍/微仰",
        "人物类型": "无人物",
        "备注": "手机链专属：完整链条展示，呈现整体工艺质感，适合品质背书内容"
    },
    {
        "场景编号": "SC037",
        "场景名称": "节日场景链条展示",
        "场景类型": "节日场景",
        "场景描述_中文": "圣诞/情人节/生日等节日氛围布景，手机链作为礼物主角展示，配合彩带、鲜花、蜡烛等节日道具",
        "场景基底_英文": "holiday themed scene (Christmas/Valentine) with phone chain as gift, flowers or candles as props, warm festive mood",
        "风格基调词": "节日氛围,温暖情感,礼物感",
        "排除描述": "不要道具喧宾夺主，链条必须清晰可见，不要过于拥挤",
        "适用品类": "手机链",
        "适用平台": "得物",
        "是否启用": True,
        "权重": 6,
        "景别": "近景",
        "光源类型": "暖光",
        "拍摄角度": "45度俯拍",
        "人物类型": "可无人物/手部入镜",
        "备注": "手机链专属：节日限时场景，配合营销节点使用"
    },
    {
        "场景编号": "SC038",
        "场景名称": "校园风链条穿搭",
        "场景类型": "穿搭场景",
        "场景描述_中文": "校园或图书馆背景，穿着学院风的女生手持手机，链条与书包/帆布袋搭配，青春清新感",
        "场景基底_英文": "campus or library setting, girl in preppy style holding phone with chain, matching with canvas bag, youthful fresh vibe",
        "风格基调词": "学院风,青春感,清新自然",
        "排除描述": "不要过度精修，不要成熟妆容，避免与风格不符的配饰",
        "适用品类": "手机链",
        "适用平台": "得物",
        "是否启用": True,
        "权重": 7,
        "景别": "中景",
        "光源类型": "自然光",
        "拍摄角度": "平视",
        "人物类型": "真人出镜",
        "姿态倾向": "自然站立/行走",
        "性别倾向": "女",
        "年龄段": "16-24岁",
        "备注": "手机链专属：校园/学院风场景，覆盖年轻用户群"
    }
]

for s in scenes:
    tmp_path = f"tmp/_sc_{s['场景编号']}.json"
    with open(tmp_path, 'w', encoding='utf-8') as f2:
        json.dump(s, f2, ensure_ascii=False)

    cmd = [
        LARK_CLI, "base", "+record-upsert",
        "--base-token", BASE_TOKEN,
        "--table-id", TABLE_ID,
        "--json", f"@{tmp_path}"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', cwd="D:/AI-Content-Hub")
    code = s["场景编号"]
    if result.returncode == 0:
        print(f"OK {code} {s['场景名称']}")
    else:
        print(f"FAIL {code} {s['场景名称']}")
        print("  stderr:", result.stderr[:300])

    os.remove(tmp_path)
    time.sleep(0.5)

print("Done.")
