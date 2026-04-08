import json, subprocess, os, time

BASE_TOKEN = "Ei9jbcsHianwvvsn5xScH8ANnnb"
TABLE_ID = "tbliWlwiyA4sppgY"
LARK_CLI = r"C:\Users\carson\AppData\Roaming\npm\lark-cli.cmd"

APPEARANCE = "年轻亚洲女性，身材比例好，精致五官，自然妆感，无过度美颜"

scenes = [
    {
        "场景编号": "SC039",
        "场景名称": "首图·街头手链正面亮相",
        "场景类型": "首图专用",
        "场景描述_中文": "年轻亚洲女性正面或四分之三侧面站立，手持挂链手机，链条清晰垂坠，街头或城市背景虚化，整体传递时髦精致的第一眼印象",
        "场景基底_英文": "young Asian woman facing camera holding phone with decorative chain strap, chain clearly visible, urban street bokeh background, fashion-forward first impression, young Asian woman, slim proportions, natural makeup, 20s",
        "风格基调词": "时髦精致,视觉冲击,首图吸睛",
        "排除描述": "不要侧脸看不见正脸，不要链条被遮挡，不要背景太杂乱，不要妆容浓艳",
        "适用品类": "手机链",
        "适用平台": "得物",
        "是否启用": True,
        "权重": 10,
        "景别": "中景/半身",
        "光源类型": "自然光",
        "拍摄角度": "平视/略俯",
        "人物类型": "真人出镜",
        "外貌风格": APPEARANCE,
        "姿态倾向": "面向镜头站立",
        "性别倾向": "女",
        "年龄段": "18-26岁",
        "备注": "首图专用高权重场景：真人正面亮相+手机链，最大化得物首图点击率"
    },
    {
        "场景编号": "SC040",
        "场景名称": "首图·回眸持机链条飘逸",
        "场景类型": "首图专用",
        "场景描述_中文": "年轻亚洲女性侧身或回眸动作，手持挂链手机，链条随动作自然飘动，背景简洁或城市感虚化，传递灵动时尚的第一印象",
        "场景基底_英文": "young Asian woman looking back over shoulder holding phone with flowing chain, chain in motion, clean or city bokeh background, dynamic elegant pose, young Asian woman, slim proportions, natural makeup, 20s",
        "风格基调词": "灵动飘逸,高级感,动态美",
        "排除描述": "不要链条不可见，不要动作僵硬，不要表情平淡无神，不要背景抢眼",
        "适用品类": "手机链",
        "适用平台": "得物",
        "是否启用": True,
        "权重": 10,
        "景别": "中景/半身",
        "光源类型": "自然光",
        "拍摄角度": "平视",
        "人物类型": "真人出镜",
        "外貌风格": APPEARANCE,
        "姿态倾向": "回眸/侧身转动",
        "性别倾向": "女",
        "年龄段": "18-26岁",
        "备注": "首图专用高权重场景：动态回眸+链条飘动，制造视觉吸引力"
    },
    {
        "场景编号": "SC041",
        "场景名称": "首图·近景手链低头特写",
        "场景类型": "首图专用",
        "场景描述_中文": "年轻亚洲女性低头看手机，手机链清晰入镜，面部若隐若现，手部与链条占画面主体，背景极简或浅色虚化，精致感爆棚",
        "场景基底_英文": "young Asian woman looking down at phone with chain strap prominently featured, face partially visible showing natural beauty, hand and chain as focal point, clean minimal background, close-up lifestyle, young Asian woman, slim proportions, natural makeup, 20s",
        "风格基调词": "精致细腻,含蓄美感,高质感",
        "排除描述": "不要完全遮脸看不见任何人物特征，不要链条模糊，不要背景杂乱",
        "适用品类": "手机链",
        "适用平台": "得物",
        "是否启用": True,
        "权重": 10,
        "景别": "近景/特写",
        "光源类型": "自然光",
        "拍摄角度": "略俯",
        "人物类型": "真人出镜",
        "外貌风格": APPEARANCE,
        "姿态倾向": "低头看手机",
        "性别倾向": "女",
        "年龄段": "18-26岁",
        "备注": "首图专用高权重场景：低头持机含蓄人物感+链条特写，兼顾颜值与产品"
    }
]

for s in scenes:
    tmp_path = f"tmp/_sc_new_{s['场景编号']}.json"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False)

    result = subprocess.run(
        [LARK_CLI, "base", "+record-upsert",
         "--base-token", BASE_TOKEN,
         "--table-id", TABLE_ID,
         "--json", f"@{tmp_path}"],
        capture_output=True, encoding="utf-8", cwd="D:/AI-Content-Hub"
    )
    os.remove(tmp_path)
    code = s["场景编号"]
    if result.returncode == 0:
        print(f"OK {code} {s['场景名称']}")
    else:
        print(f"FAIL {code} {s['场景名称']}")
        print("  stderr:", result.stderr[:300])
    time.sleep(0.5)

print("Done.")
