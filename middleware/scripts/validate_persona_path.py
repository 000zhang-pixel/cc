"""
validate_persona_path.py — 验证 Persona present / absent 两条路径

模拟 _assign_personas 和 _extract_persona_fields 的行为：
  Path A: 有 Persona 表 → 使用 prompt_template 作为人物描述
  Path B: 无 Persona 表 → fallback 到 Scene person 字段
  Path C: 固定主人设模式 → 所有组相同 persona
  Path D: 多人设轮换模式 → 各组 persona 优先不重复

不依赖飞书，纯本地数据结构模拟。

运行：
  cd middleware && python scripts/validate_persona_path.py
"""
import sys

if sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


# ── 模拟数据 ─────────────────────────────────────────────────────────────────

MOCK_PERSONA_POOL = [
    {
        "record_id": "rec001",
        "fields": {
            "人设编号": "PS001", "人设名称": "甜酷通勤女生",
            "Prompt描述模板": "Asian girl, 22yo, wavy black hair, sweet-cool vibe",
            "一致性锚点模板": "同一女生，长黑发微卷，甜酷通勤穿搭",
            "适用内容类型": [{"text": "种草推荐"}, {"text": "穿搭搭配"}],
            "气质标签": [{"text": "甜酷"}],
            "优先级": 100,
            "适用品类": [{"text": "通用"}],
            "性别倾向": "女", "年龄段": "22-26",
            "外貌风格": "长黑发微卷", "穿搭风格": "休闲通勤",
            "动作倾向": "自然持握",
        }
    },
    {
        "record_id": "rec002",
        "fields": {
            "人设编号": "PS002", "人设名称": "清冷文艺女生",
            "Prompt描述模板": "Asian girl, 24yo, straight light-brown hair, cold-tone minimalist",
            "一致性锚点模板": "同一女生，浅棕直发，极简白黑穿搭",
            "适用内容类型": [{"text": "种草推荐"}, {"text": "场景展示"}],
            "气质标签": [{"text": "清冷"}],
            "优先级": 95,
            "适用品类": [{"text": "通用"}],
            "性别倾向": "女", "年龄段": "22-26",
            "外貌风格": "浅棕直发", "穿搭风格": "极简轻奢",
            "动作倾向": "低头看书",
        }
    },
    {
        "record_id": "rec003",
        "fields": {
            "人设编号": "PS003", "人设名称": "青春校园女生",
            "Prompt描述模板": "Asian girl, 19yo, twin tails, sweet campus style",
            "一致性锚点模板": "同一女生，双马尾，甜美清纯妆，学院风穿搭",
            "适用内容类型": [{"text": "种草推荐"}, {"text": "穿搭搭配"}, {"text": "场景展示"}],
            "气质标签": [{"text": "青春"}],
            "优先级": 90,
            "适用品类": [{"text": "通用"}],
            "性别倾向": "女", "年龄段": "18-22",
            "外貌风格": "双马尾", "穿搭风格": "学院风",
            "动作倾向": "大笑跑动",
        }
    },
]

MOCK_SCENE_FALLBACK = {
    "人物类型": "亚洲女性",
    "性别倾向": "女",
    "年龄段": "22-26",
    "外貌风格": "自然妆容",
    "姿态倾向": "自然持握",
    "适合人设标签": ["甜酷"],
}

MOCK_GROUPS = [
    {"group_id": "g01", "type": "img", "content_type": "种草推荐"},
    {"group_id": "g02", "type": "img", "content_type": "穿搭搭配"},
    {"group_id": "g03", "type": "img", "content_type": "场景展示"},
]


# ── 简化版 Feishu helper（模拟 get_text / get_option / get_options / get_number）────

def _get_text(rec: dict, field: str) -> str:
    val = rec["fields"].get(field, "")
    if isinstance(val, list):  # 富文本格式
        return "".join(seg.get("text", "") for seg in val if isinstance(seg, dict))
    return str(val) if val else ""


def _get_option(rec: dict, field: str) -> str:
    val = rec["fields"].get(field, "")
    if isinstance(val, dict):
        return val.get("text", "")
    return str(val) if val else ""


def _get_options(rec: dict, field: str) -> list:
    val = rec["fields"].get(field, [])
    if isinstance(val, list):
        return [item.get("text", item) if isinstance(item, dict) else item for item in val]
    return []


def _get_number(rec: dict, field: str, default=0):
    return rec["fields"].get(field, default) or default


# ── 模拟 _extract_persona_fields ───────────────────────────────────────────

def extract_persona_fields(rec: dict) -> dict:
    return {
        "persona_id":           _get_text(rec, "人设编号"),
        "persona_label":        _get_text(rec, "人设名称"),
        "gender":               _get_option(rec, "性别倾向"),
        "age":                  _get_option(rec, "年龄段"),
        "appearance":           _get_text(rec, "外貌风格"),
        "style":                _get_text(rec, "穿搭风格"),
        "action":               _get_text(rec, "动作倾向"),
        "qi_zhi_tags":          _get_options(rec, "气质标签"),
        "prompt_template":      _get_text(rec, "Prompt描述模板"),
        "consistency_template": _get_text(rec, "一致性锚点模板"),
        "source": "persona_table",
    }


# ── 模拟 _soft_score ────────────────────────────────────────────────────────

def soft_score(prec: dict, content_type: str, scene_dict: dict) -> float:
    sc = 0.0
    ctypes = _get_options(prec, "适用内容类型")
    if content_type in ctypes:
        sc += 2.0
    scene_tags = set(scene_dict.get("适合人设标签") or [])
    qi_zhi = set(_get_options(prec, "气质标签"))
    sc += len(scene_tags & qi_zhi)
    sc += int(_get_number(prec, "优先级")) / 200.0
    return sc


# ── 模拟 _assign_personas ──────────────────────────────────────────────────

def _is_no_person_scene(scene: dict) -> bool:
    person_type = str(scene.get("人物类型") or "").strip()
    return ("无人物" in person_type) or ("纯产品" in person_type)


def assign_personas(groups, pool, scene_assignments, persona_mode="自动"):
    assignments = {}
    if not pool:
        # Path B: no persona table — fallback to scene person fields
        for g in groups:
            scene = scene_assignments.get(g["group_id"], {})
            if scene.get("人物类型") and not _is_no_person_scene(scene):
                assignments[g["group_id"]] = {
                    "persona_id": None,
                    "persona_label": scene["人物类型"],
                    "gender":     scene.get("性别倾向", ""),
                    "age":        scene.get("年龄段", ""),
                    "appearance": scene.get("外貌风格", ""),
                    "prompt_template":      "",
                    "consistency_template": "",
                    "source": "scene_fallback",
                }
            else:
                assignments[g["group_id"]] = None
        return assignments

    # Soft-match scoring
    if persona_mode == "固定主人设":
        persona_groups = [g for g in groups if not _is_no_person_scene(scene_assignments.get(g["group_id"], {}))]
        best = max(pool, key=lambda r: sum(
            soft_score(r, g.get("content_type", ""), scene_assignments.get(g["group_id"], {}))
            for g in persona_groups
        )) if persona_groups else None
        for g in groups:
            assignments[g["group_id"]] = None if _is_no_person_scene(scene_assignments.get(g["group_id"], {})) else extract_persona_fields(best)
    else:
        _used_ids = []
        for g in groups:
            gid = g["group_id"]
            ct = g.get("content_type", "")
            sd = scene_assignments.get(gid, {})
            if _is_no_person_scene(sd):
                assignments[gid] = None
                continue
            candidates = [r for r in pool if id(r) not in _used_ids] or pool
            chosen = max(candidates, key=lambda r: soft_score(r, ct, sd))
            assignments[gid] = extract_persona_fields(chosen)
            _used_ids.append(id(chosen))
    return assignments


# ── 测试 ────────────────────────────────────────────────────────────────────

scene_assignments = {g["group_id"]: MOCK_SCENE_FALLBACK for g in MOCK_GROUPS}
no_person_scene_assignments = {
    **scene_assignments,
    "g01": {**MOCK_SCENE_FALLBACK, "人物类型": "无人物·纯产品"},
}

print("=" * 60)
print("  Persona present / absent 路径验证")
print("=" * 60)

# ── Path A: Persona 表存在，自动模式 ─────────────────────────────────────
print("\n[Path A] Persona 表存在 — 自动/多人设轮换")
a = assign_personas(MOCK_GROUPS, MOCK_PERSONA_POOL, scene_assignments, "自动")
for gid, p in a.items():
    tmpl = p.get("prompt_template", "")
    print(f"  {gid}: {p['persona_label']!r}  source={p['source']}  prompt_template={'有' if tmpl else '空'}")

assert all(p["source"] == "persona_table" for p in a.values()), "FAIL: source 应为 persona_table"
assert all(p.get("prompt_template") for p in a.values()), "FAIL: prompt_template 不应为空"
# 3 组应优先分配不同 persona
persona_ids = [a[g["group_id"]]["persona_id"] for g in MOCK_GROUPS]
assert len(set(persona_ids)) >= 2, f"FAIL: 3组应有至少2种不同 persona，实际={persona_ids}"
print(f"  ✓ 所有组均命中 Persona 表，prompt_template 有值，至少2种不同 persona")

# ── Path B: 无 Persona 表，fallback 到 Scene ─────────────────────────────
print("\n[Path B] 无 Persona 表 — fallback 到 Scene 字段")
b = assign_personas(MOCK_GROUPS, [], scene_assignments, "自动")
for gid, p in b.items():
    print(f"  {gid}: {p['persona_label']!r}  source={p['source']}")

assert all(p["source"] == "scene_fallback" for p in b.values()), "FAIL: source 应为 scene_fallback"
assert all(not p.get("prompt_template") for p in b.values()), "FAIL: fallback 时 prompt_template 应为空"
print(f"  ✓ fallback 成功，source=scene_fallback，prompt_template 为空（走字段拼接路径）")

# ── Path C: 固定主人设 ────────────────────────────────────────────────────
print("\n[Path C] 固定主人设")
c = assign_personas(MOCK_GROUPS, MOCK_PERSONA_POOL, scene_assignments, "固定主人设")
fixed_ids = set(c[g["group_id"]]["persona_id"] for g in MOCK_GROUPS)
assert len(fixed_ids) == 1, f"FAIL: 固定主人设应全组相同，实际={fixed_ids}"
print(f"  ✓ 所有组使用同一 persona: {list(fixed_ids)[0]}")

# ── Path D: 软匹配优先内容类型 ────────────────────────────────────────────
print("\n[Path D] 软匹配评分验证 — 种草推荐 vs 场景展示")
score_ps001_grass   = soft_score(MOCK_PERSONA_POOL[0], "种草推荐", MOCK_SCENE_FALLBACK)
score_ps002_scene   = soft_score(MOCK_PERSONA_POOL[1], "场景展示", MOCK_SCENE_FALLBACK)
score_ps001_scene   = soft_score(MOCK_PERSONA_POOL[0], "场景展示", MOCK_SCENE_FALLBACK)
print(f"  PS001 vs 种草推荐: {score_ps001_grass:.2f}")
print(f"  PS002 vs 场景展示: {score_ps002_scene:.2f}")
print(f"  PS001 vs 场景展示: {score_ps001_scene:.2f}")
# PS001 适合种草推荐，分应 > 其不适合的任务类型
assert score_ps001_grass > score_ps001_scene, \
    f"FAIL: PS001对种草推荐的分应 > 场景展示，实际 {score_ps001_grass} vs {score_ps001_scene}"
print(f"  ✓ 内容类型命中时评分更高（软匹配生效）")

# ── Path E: 纯产品场景不分配 persona ─────────────────────────────────────
print("\n[Path E] 无人物·纯产品 场景不分配 persona")
e = assign_personas(MOCK_GROUPS, MOCK_PERSONA_POOL, no_person_scene_assignments, "自动")
assert e["g01"] is None, f"FAIL: g01 应为 None，实际={e['g01']}"
assert e["g02"] is not None and e["g03"] is not None, "FAIL: 其他人物场景仍应正常分配"
print("  ✓ g01=无人物·纯产品 时不分配 persona，其余组保持正常")

print()
print("=" * 60)
print("  全部通过 ✓")
print("=" * 60)
