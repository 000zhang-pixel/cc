"""
validate_handler_units.py — 直接调用 ContentGenerationHandler 真实方法的函数级回归测试

与 validate_scene_variety.py 等逻辑镜像脚本不同，本脚本：
  - 通过 MockFeishu + MockStorage 实例化真实 ContentGenerationHandler
  - 直接调用生产方法：_assign_scenes() / _assign_personas() / _build_creative_briefs()
  - 避免生产代码与验证实现发生偏移时脚本仍通过的风险

覆盖内容（8 个 case）：
  1. _assign_scenes: pool=2 groups=3 variety=高 → avg_unique_scenes ≥ 1.5
  2. _assign_scenes: 返回全部组，含 道具建议/适合人设标签/场景主题 字段
  3. _assign_personas: strategy+scene 标签命中时 PS001 胜出（新评分维度验证）
  4. _assign_personas: 3 组 3 人设各不重复（record_id 去重）
  5. _assign_personas: 固定主人设 → 3 组使用相同 persona
  6. _build_creative_briefs: 低 → 标题有差异，叙事/结构固定
  7. _build_creative_briefs: 中 → 标题/叙事均有差异
  8. _build_creative_briefs: 高 叙事差异度 ≥ 中

运行：
  cd middleware && python scripts/validate_handler_units.py
"""
import sys
import os
import types

# Fix Windows GBK stdout encoding
if sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 路径设置 ──────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── 注入空 db 模块（避免模块级 import 触发 DB 连接）────────────────────────────
_mock_db = types.ModuleType("db")
for _fn in ("mark_plan_started", "mark_plan_failed", "log_exc"):
    setattr(_mock_db, _fn, lambda *a, **kw: None)
sys.modules.setdefault("db", _mock_db)

# ── 导入真实 Handler ──────────────────────────────────────────────────────────
from handlers.content_generation import ContentGenerationHandler


# ── MockFeishu ────────────────────────────────────────────────────────────────

class MockFeishu:
    """
    Lightweight stand-in for FeishuClient.
    Implements only the methods called by the tested handler methods.
    filter_str in list_records is intentionally ignored (all records returned).
    """

    def __init__(self, table_data: dict):
        self._table_data = table_data

    def get_field(self, record: dict, field: str, default=None):
        return record.get("fields", {}).get(field, default)

    def get_text(self, record: dict, field: str, default: str = "") -> str:
        val = self.get_field(record, field)
        if val is None:
            return default
        if isinstance(val, list):
            return "".join(seg.get("text", "") for seg in val if isinstance(seg, dict))
        return str(val)

    def get_option(self, record: dict, field: str, default: str = "") -> str:
        val = self.get_field(record, field)
        if val is None:
            return default
        if isinstance(val, dict):
            return val.get("text", default)
        return str(val)

    def get_options(self, record: dict, field: str) -> list:
        val = self.get_field(record, field)
        if not val:
            return []
        if isinstance(val, list):
            return [v.get("text", "") if isinstance(v, dict) else str(v) for v in val]
        return []

    def get_number(self, record: dict, field: str, default: float = 0) -> float:
        val = self.get_field(record, field)
        if val is None:
            return default
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    def list_records(self, table_id: str, filter_str=None, page_size: int = 100) -> list:
        return list(self._table_data.get(table_id, []))

    def update_record(self, table_id, record_id, fields):
        pass  # no-op in tests

    def create_record(self, table_id, fields):
        return "mock_rec"

    def get_record(self, table_id, record_id):
        for r in self._table_data.get(table_id, []):
            if r.get("record_id") == record_id:
                return r
        return {"record_id": record_id, "fields": {}}


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _opt(text: str) -> dict:
    return {"text": text}


def _scene(rec_id: str, code: str, theme: str, persona_tags: list, weight: int = 10) -> dict:
    return {
        "record_id": rec_id,
        "fields": {
            "场景编号":    code,
            "场景基底_英文": f"{code}_en",
            "场景描述_中文": f"{code} 场景",
            "风格基调词":  "自然",
            "排除描述":    "",
            "人物类型":    "亚洲女性",
            "性别倾向":    "女",
            "年龄段":      "22-26",
            "外貌风格":    "自然妆容",
            "姿态倾向":    "自然持握",
            "时段光境":    _opt("午间"),
            "空间感":      _opt("中"),
            "光线方向":    _opt("正面"),
            "色温":        _opt("暖"),
            "景深感":      _opt("中"),
            "镜头感":      _opt("中"),
            "道具建议":    "手拿奶茶",
            "适合人设标签": [_opt(t) for t in persona_tags],
            "场景主题":    _opt(theme),
            "适用品类":    [],   # 空=通用
            "权重":        weight,
            "是否启用":    "启用",
        },
    }


def _persona(
    rec_id: str, code: str, name: str,
    qi_zhi: list, scene_themes: list, ctypes: list, priority: int = 100
) -> dict:
    return {
        "record_id": rec_id,
        "fields": {
            "人设编号":        code,
            "人设名称":        name,
            "是否启用":        "启用",
            "适用品类":        [],   # 空=通用
            "优先级":          priority,
            "适用内容类型":    [_opt(t) for t in ctypes],
            "气质标签":        [_opt(t) for t in qi_zhi],
            "适合场景标签":    [_opt(t) for t in scene_themes],
            "性别倾向":        _opt("女"),
            "年龄段":          _opt("22-26"),
            "外貌风格":        "长黑发微卷",
            "穿搭风格":        "休闲通勤",
            "动作倾向":        "自然持握",
            "Prompt描述模板":  f"Asian girl, {name}",
            "一致性锚点模板":  f"同一女生，{name}特征",
        },
    }


def _strategy(rec_id: str, ctypes: list, persona_adapt_tags: list, priority: int = 80) -> dict:
    return {
        "record_id": rec_id,
        "fields": {
            "是否启用":    "启用",
            "适用内容类型": [_opt(t) for t in ctypes],
            "适用平台":    [],   # 空=通用
            "适用品类":    [],   # 空=通用
            "人设适配标签": [_opt(t) for t in persona_adapt_tags],
            "优先级":      priority,
        },
    }


# ── 共用 fixtures ─────────────────────────────────────────────────────────────

SCENES_5 = [
    _scene("sc01", "S001", "商场",  ["甜酷", "精致"]),
    _scene("sc02", "S002", "校园",  ["青春"]),
    _scene("sc03", "S003", "咖啡馆", ["清冷", "甜酷"]),
    _scene("sc04", "S004", "街头",  ["精致", "松弛"]),
    _scene("sc05", "S005", "居家",  ["松弛", "清冷"]),
]

PERSONAS_3 = [
    _persona("pr01", "PS001", "甜酷通勤女生",
             qi_zhi=["甜酷"],
             scene_themes=["商场", "通勤", "街头"],
             ctypes=["种草推荐", "穿搭搭配"],
             priority=100),
    _persona("pr02", "PS002", "清冷文艺女生",
             qi_zhi=["清冷"],
             scene_themes=["咖啡馆", "居家", "校园"],
             ctypes=["种草推荐", "场景展示"],
             priority=95),
    _persona("pr03", "PS003", "青春校园女生",
             qi_zhi=["青春"],
             scene_themes=["校园", "街头", "咖啡馆"],
             ctypes=["种草推荐", "穿搭搭配", "场景展示"],
             priority=90),
]

STRATEGIES = [
    _strategy("strat01",
              ctypes=["种草推荐"],
              persona_adapt_tags=["甜酷"],
              priority=80),
]

GROUPS = [
    {"group_id": "g01", "type": "img", "content_type": "种草推荐",  "img_per_piece": 4},
    {"group_id": "g02", "type": "img", "content_type": "穿搭搭配",  "img_per_piece": 4},
    {"group_id": "g03", "type": "img", "content_type": "场景展示",  "img_per_piece": 4},
]

SKU_FIELDS = {"品类": _opt("通用")}

CFG_BASE = {
    "diff_strength":        "中",
    "persona_mode":         "自动",
    "consistency_strength": "强",
    "scene_variety":        "中",
    "platforms":            ["小红书"],
    "_category":            "通用",
}

TABLES = {
    "scene":    "tbl_scene",
    "persona":  "tbl_persona",
    "strategy": "tbl_strategy",
    "plan":     "tbl_plan",
    "prompt":   "tbl_prompt",
    "content":  "tbl_content",
    "tag":      "tbl_tag",
    "shotplan": "tbl_shotplan",
}


def _make_handler(scene_recs=None, persona_recs=None, strategy_recs=None) -> ContentGenerationHandler:
    table_data = {
        "tbl_scene":    scene_recs    if scene_recs    is not None else SCENES_5,
        "tbl_persona":  persona_recs  if persona_recs  is not None else PERSONAS_3,
        "tbl_strategy": strategy_recs if strategy_recs is not None else STRATEGIES,
    }
    return ContentGenerationHandler(
        feishu=MockFeishu(table_data),
        tables=TABLES,
        model_params={},
        local_storage=None,
    )


# ── Test runner ───────────────────────────────────────────────────────────────

_PASS = 0
_FAIL = 0


def run_test(name: str, fn):
    global _PASS, _FAIL
    try:
        fn()
        print(f"  ✓ {name}")
        _PASS += 1
    except Exception as exc:
        print(f"  ✗ {name}: {exc}")
        _FAIL += 1


# ═══════════════════════════════════════════════════════════════════
print("=" * 60)
print("  ContentGenerationHandler 函数级回归测试")
print("=" * 60)


# ── Test 1 & 2: _assign_scenes ────────────────────────────────────────────────
print("\n[_assign_scenes]")


def test_assign_scenes_high_variety_small_pool():
    """pool=2, groups=3, variety=高 — avg unique scene count per run should be ≥ 1.5."""
    h = _make_handler(scene_recs=[
        _scene("sc01", "S001", "商场", ["甜酷"]),
        _scene("sc02", "S002", "校园", ["青春"]),
    ])
    unique_counts = []
    for _ in range(300):
        result = h._assign_scenes(GROUPS, SKU_FIELDS, "PLAN_001", scene_variety="高")
        scene_ids = [v["scene_id"] for v in result.values()]
        unique_counts.append(len(set(scene_ids)))
    avg = sum(unique_counts) / len(unique_counts)
    assert avg >= 1.5, f"pool=2 groups=3 高: avg_unique={avg:.2f} < 1.5"


run_test("_assign_scenes: pool=2 groups=3 variety=高 avg_unique_scenes≥1.5", test_assign_scenes_high_variety_small_pool)


def test_assign_scenes_fields_present():
    """
    Returned scene dicts should include the v2 fields:
    道具建议, 适合人设标签, 场景主题.
    """
    h = _make_handler()
    result = h._assign_scenes(GROUPS, SKU_FIELDS, "PLAN_001", scene_variety="中")
    assert len(result) == len(GROUPS), f"Expected {len(GROUPS)} assignments, got {len(result)}"
    for gid, sd in result.items():
        assert "scene_id"       in sd, f"{gid}: missing scene_id"
        assert "道具建议"       in sd, f"{gid}: missing 道具建议"
        assert "适合人设标签"   in sd, f"{gid}: missing 适合人设标签"
        assert "场景主题"       in sd, f"{gid}: missing 场景主题"


run_test("_assign_scenes: 返回全部组，含 道具建议/适合人设标签/场景主题", test_assign_scenes_fields_present)


# ── Test 3–5: _assign_personas ────────────────────────────────────────────────
print("\n[_assign_personas]")


def test_persona_strategy_scene_scoring():
    """
    g01: content_type=种草推荐, scene={适合人设标签:["甜酷"], 场景主题:"商场"}
    Strategy for 种草推荐 has 人设适配标签=["甜酷"].
    PS001 (甜酷, scenes=["商场",...]) expected score breakdown:
      +2 content type match
      +1 scene 适合人设标签 甜酷 ∩ qi_zhi 甜酷
      +1 persona 适合场景标签 contains 商场
      +1 strategy 人设适配标签 甜酷 ∩ qi_zhi 甜酷
      +0.5 priority (100/200)
      = 5.5  — clearly beats PS002 (2.475) and PS003 (0.45)
    """
    h = _make_handler()
    scene_assignments = {
        "g01": {"适合人设标签": ["甜酷"], "场景主题": "商场"},
        "g02": {"适合人设标签": [],        "场景主题": "校园"},
        "g03": {"适合人设标签": ["清冷"],  "场景主题": "咖啡馆"},
    }
    cfg = {**CFG_BASE, "persona_mode": "自动"}
    result = h._assign_personas(GROUPS, SKU_FIELDS, cfg, scene_assignments)
    g01 = result.get("g01")
    assert g01 is not None, "g01 should receive a persona"
    assert g01["persona_id"] == "PS001", (
        f"g01 should get PS001 (strategy+scene tags align); got {g01['persona_id']}"
    )


run_test("_assign_personas: strategy+scene 标签命中时 PS001 胜出", test_persona_strategy_scene_scoring)


def test_persona_dedup_by_record_id():
    """3 groups, 3 personas, equal-weight scene → each group gets a distinct persona."""
    h = _make_handler()
    scene_assignments = {g["group_id"]: {"适合人设标签": [], "场景主题": ""} for g in GROUPS}
    cfg = {**CFG_BASE, "persona_mode": "自动"}
    result = h._assign_personas(GROUPS, SKU_FIELDS, cfg, scene_assignments)
    persona_ids = [result[g["group_id"]]["persona_id"] for g in GROUPS]
    assert len(set(persona_ids)) == 3, (
        f"3 groups with 3 personas should each get distinct persona; got {persona_ids}"
    )


run_test("_assign_personas: 3 组 3 人设各不重复（record_id 去重）", test_persona_dedup_by_record_id)


def test_persona_fixed_mode():
    """固定主人设 → all groups share the same persona."""
    h = _make_handler()
    scene_assignments = {
        g["group_id"]: {"适合人设标签": ["甜酷"], "场景主题": "商场"}
        for g in GROUPS
    }
    cfg = {**CFG_BASE, "persona_mode": "固定主人设"}
    result = h._assign_personas(GROUPS, SKU_FIELDS, cfg, scene_assignments)
    persona_ids = set(result[g["group_id"]]["persona_id"] for g in GROUPS)
    assert len(persona_ids) == 1, (
        f"固定主人设: all groups should use same persona; got {persona_ids}"
    )


run_test("_assign_personas: 固定主人设 → 3 组相同", test_persona_fixed_mode)


# ── Test 6–8: _build_creative_briefs ─────────────────────────────────────────
print("\n[_build_creative_briefs]")


def _briefs_for_strength(diff_strength: str) -> dict:
    h = _make_handler()
    scene_assignments = {g["group_id"]: {"适合人设标签": [], "场景主题": ""} for g in GROUPS}
    persona_assignments = {g["group_id"]: None for g in GROUPS}
    cfg = {**CFG_BASE, "diff_strength": diff_strength}
    return h._build_creative_briefs(GROUPS, cfg, scene_assignments, persona_assignments)


def test_briefs_low():
    briefs = _briefs_for_strength("低")
    titles     = [briefs[g["group_id"]]["title_pattern"]   for g in GROUPS]
    narratives = [briefs[g["group_id"]]["narrative_angle"] for g in GROUPS]
    assert len(set(titles)) > 1, f"低: titles should vary; got {titles}"
    assert len(set(narratives)) == 1, f"低: narrative should be fixed; got {narratives}"


run_test("_build_creative_briefs: 低 → 标题有差异，叙事/结构固定", test_briefs_low)


def test_briefs_mid():
    briefs = _briefs_for_strength("中")
    titles     = [briefs[g["group_id"]]["title_pattern"]   for g in GROUPS]
    narratives = [briefs[g["group_id"]]["narrative_angle"] for g in GROUPS]
    assert len(set(titles)) > 1,      f"中: titles should vary; got {titles}"
    assert len(set(narratives)) >= 2, f"中: narrative should vary; got {narratives}"


run_test("_build_creative_briefs: 中 → 标题/叙事均有差异", test_briefs_mid)


def test_briefs_high_ge_mid():
    b_mid  = _briefs_for_strength("中")
    b_high = _briefs_for_strength("高")
    mid_uniq  = len(set(b_mid[g["group_id"]]["narrative_angle"]  for g in GROUPS))
    high_uniq = len(set(b_high[g["group_id"]]["narrative_angle"] for g in GROUPS))
    assert high_uniq >= mid_uniq, (
        f"高 叙事差异度应≥中; 高={high_uniq} 中={mid_uniq}"
    )


run_test("_build_creative_briefs: 高 叙事差异度 ≥ 中", test_briefs_high_ge_mid)


# ── Summary ───────────────────────────────────────────────────────────────────
total = _PASS + _FAIL
print()
print("=" * 60)
if _FAIL == 0:
    print(f"  全部通过 ✓  ({_PASS}/{total})")
else:
    print(f"  {_PASS}/{total} 通过，{_FAIL} 失败 ✗")
print("=" * 60)

if _FAIL > 0:
    sys.exit(1)
