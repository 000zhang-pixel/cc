import json, subprocess, os, time

BASE_TOKEN = "Ei9jbcsHianwvvsn5xScH8ANnnb"
TABLE_ID = "tbliWlwiyA4sppgY"
LARK_CLI = r"C:\Users\carson\AppData\Roaming\npm\lark-cli.cmd"

APPEARANCE_ZH = "年轻亚洲女性，身材比例好，精致五官，自然妆感，无过度美颜"
APPEARANCE_EN_SUFFIX = ", young Asian woman, slim proportions, natural makeup, 20s"

# Records to update: (record_id, scene_code, current_base_en)
# For chain-specific scenes (SC029-SC038) with real persons, no existing 外貌风格
# Plus universal real-person scenes that already have 外貌风格 set to something else

updates = [
    # Hand-chain real-person scenes (no appearance yet)
    {
        "record_id": "recvgcrL8jqVai",  # SC029 手持手机挂链出街
        "外貌风格": APPEARANCE_ZH,
        "场景基底_英文_suffix": APPEARANCE_EN_SUFFIX,
        "场景基底_英文_current": "young woman holding phone with hanging chain strap, street background bokeh, casual chic"
    },
    {
        "record_id": "recvgcrMa150bw",  # SC031 穿搭全身链条点睛
        "外貌风格": APPEARANCE_ZH,
        "场景基底_英文_suffix": APPEARANCE_EN_SUFFIX,
        "场景基底_英文_current": "full-body or half-body outfit shot, phone chain as styling accessory detail, fashion editorial feel"
    },
    {
        "record_id": "recvgcrPUOcSSa",  # SC038 校园风链条穿搭
        "外貌风格": APPEARANCE_ZH,
        "场景基底_英文_suffix": APPEARANCE_EN_SUFFIX,
        "场景基底_英文_current": "campus or library setting, girl in preppy style holding phone with chain, matching with canvas bag, youthful fresh vibe"
    },
    # Universal real-person scenes — update 外貌风格 to include the new insight
    {
        "record_id": "recvfNMIQoLFnL",  # SC001 咖啡馆午后
        "外貌风格": APPEARANCE_ZH,
        "场景基底_英文_suffix": APPEARANCE_EN_SUFFIX,
        "场景基底_英文_current": "cozy cafe interior, wooden table with coffee cup, soft warm afternoon sunlight streaming through windows, blurred bokeh background of cafe patrons"
    },
    {
        "record_id": "recvfNMPQdrwTS",  # SC003
        "外貌风格": APPEARANCE_ZH,
        "场景基底_英文_suffix": APPEARANCE_EN_SUFFIX,
        "场景基底_英文_current": None  # will skip suffix if None
    },
    {
        "record_id": "recvfNMWzqc5mU",  # SC005
        "外貌风格": APPEARANCE_ZH,
        "场景基底_英文_suffix": APPEARANCE_EN_SUFFIX,
        "场景基底_英文_current": None
    },
    {
        "record_id": "recvfNN37l0BqL",  # SC006
        "外貌风格": APPEARANCE_ZH,
        "场景基底_英文_suffix": APPEARANCE_EN_SUFFIX,
        "场景基底_英文_current": None
    },
    {
        "record_id": "recvgc1C01avke",  # SC010
        "外貌风格": APPEARANCE_ZH,
        "场景基底_英文_suffix": APPEARANCE_EN_SUFFIX,
        "场景基底_英文_current": None
    },
    {
        "record_id": "recvgc1W3cyr9R",  # SC012
        "外貌风格": APPEARANCE_ZH,
        "场景基底_英文_suffix": APPEARANCE_EN_SUFFIX,
        "场景基底_英文_current": None
    },
    {
        "record_id": "recvgc5aLAzeho",  # SC018
        "外貌风格": APPEARANCE_ZH,
        "场景基底_英文_suffix": APPEARANCE_EN_SUFFIX,
        "场景基底_英文_current": None
    },
    {
        "record_id": "recvgc6v9eujj5",  # SC022
        "外貌风格": APPEARANCE_ZH,
        "场景基底_英文_suffix": APPEARANCE_EN_SUFFIX,
        "场景基底_英文_current": None
    },
    {
        "record_id": "recvgc6E4ZTtVY",  # SC024
        "外貌风格": APPEARANCE_ZH,
        "场景基底_英文_suffix": APPEARANCE_EN_SUFFIX,
        "场景基底_英文_current": None
    },
    {
        "record_id": "recvgc8jaTLmVZ",  # SC028
        "外貌风格": APPEARANCE_ZH,
        "场景基底_英文_suffix": APPEARANCE_EN_SUFFIX,
        "场景基底_英文_current": None
    },
    {
        "record_id": "recvfNNpvRjjgI",  # SC008
        "外貌风格": APPEARANCE_ZH,
        "场景基底_英文_suffix": APPEARANCE_EN_SUFFIX,
        "场景基底_英文_current": None
    },
]

# First get the current 场景基底_英文 for records where we don't know it
def get_record(record_id):
    result = subprocess.run(
        [LARK_CLI, "base", "+record-get",
         "--base-token", BASE_TOKEN,
         "--table-id", TABLE_ID,
         "--record-id", record_id],
        capture_output=True, encoding="utf-8", cwd="D:/AI-Content-Hub"
    )
    if result.returncode == 0:
        return json.loads(result.stdout)
    return None

for upd in updates:
    rid = upd["record_id"]
    base_en_current = upd["场景基底_英文_current"]

    # Fetch current value if not known
    if base_en_current is None:
        rec_data = get_record(rid)
        if rec_data:
            inner = rec_data.get("data", {})
            fields = inner.get("fields", [])
            row = inner.get("data", [])
            if isinstance(row, dict):
                base_en_current = row.get("场景基底_英文", "")
            else:
                # array format
                try:
                    idx = fields.index("场景基底_英文")
                    val = row[idx] if idx < len(row) else ""
                    base_en_current = val or ""
                except (ValueError, IndexError):
                    base_en_current = ""

    # Build new base_en
    base_en_new = (base_en_current or "").strip()
    suffix = upd["场景基底_英文_suffix"]
    if suffix and suffix not in base_en_new:
        base_en_new = base_en_new + suffix

    payload = {
        "外貌风格": upd["外貌风格"],
        "场景基底_英文": base_en_new
    }

    tmp_path = f"tmp/_sc_upd_{rid}.json"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

    result = subprocess.run(
        [LARK_CLI, "base", "+record-upsert",
         "--base-token", BASE_TOKEN,
         "--table-id", TABLE_ID,
         "--record-id", rid,
         "--json", f"@{tmp_path}"],
        capture_output=True, encoding="utf-8", cwd="D:/AI-Content-Hub"
    )
    os.remove(tmp_path)

    if result.returncode == 0:
        print(f"OK {rid}")
    else:
        print(f"FAIL {rid}")
        print("  stderr:", result.stderr[:300])
    time.sleep(0.3)

print("Done.")
