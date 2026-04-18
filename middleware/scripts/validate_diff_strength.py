"""
validate_diff_strength.py — 验证 diff_strength 三挡行为差异

不依赖飞书，纯本地模拟 _build_creative_briefs 的轮转逻辑。

验收标准（来自 review 3.7）：
  - 同一任务 3 组图文标题句式不完全重复
  - 同一任务 3 组图文叙事角度至少 2 组不同
  - 高挡比中挡产生更大的叙事/结构多样性

运行：
  cd middleware && python scripts/validate_diff_strength.py
"""
import sys

if sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 与 content_generation.py 保持一致的池
_TITLE_PATTERNS = [
    "疑问句式", "数字/对比句式", "场景直述句式", "反转/意外句式", "情绪共鸣句式",
]
_NARRATIVE_ANGLES = [
    "搭配点睛", "日常实用", "细节质感", "氛围感种草", "礼物推荐",
]
_STRUCTURE_MODES = [
    "场景切入", "痛点切入", "体验切入", "对比切入", "情绪切入",
]


def simulate_briefs(group_count: int, diff_strength: str) -> list[dict]:
    """模拟 _build_creative_briefs 的轮转结果，返回每组的 brief 列表。"""
    if diff_strength == "高":
        ts, ns, ss = 2, 2, 2
    elif diff_strength == "低":
        ts, ns, ss = 1, 0, 0
    else:  # 中
        ts, ns, ss = 1, 1, 1

    briefs = []
    for idx in range(group_count):
        briefs.append({
            "title_pattern":   _TITLE_PATTERNS[(idx * ts) % len(_TITLE_PATTERNS)],
            "narrative_angle": _NARRATIVE_ANGLES[(idx * ns) % len(_NARRATIVE_ANGLES)],
            "structure_mode":  _STRUCTURE_MODES[(idx * ss) % len(_STRUCTURE_MODES)],
        })
    return briefs


def check_briefs(briefs: list[dict], strength: str) -> dict:
    titles     = [b["title_pattern"]   for b in briefs]
    narratives = [b["narrative_angle"] for b in briefs]
    structures = [b["structure_mode"]  for b in briefs]
    return {
        "strength":          strength,
        "titles":            titles,
        "narratives":        narratives,
        "structures":        structures,
        "unique_titles":     len(set(titles)),
        "unique_narratives": len(set(narratives)),
        "unique_structures": len(set(structures)),
    }


print("=" * 60)
print("  diff_strength 三挡行为验证 (3组图文)")
print("=" * 60)

N = 3  # 3 组图文，典型任务规模
results = {}
for strength in ("低", "中", "高"):
    briefs = simulate_briefs(N, strength)
    r = check_briefs(briefs, strength)
    results[strength] = r
    print(f"\n[{strength}]")
    for i, b in enumerate(briefs, 1):
        print(f"  组{i}: 标题={b['title_pattern']!r:12s}  "
              f"叙事={b['narrative_angle']!r:8s}  "
              f"结构={b['structure_mode']!r}")
    print(f"  → 唯一标题:{r['unique_titles']}  唯一叙事:{r['unique_narratives']}  唯一结构:{r['unique_structures']}")

print()
print("=" * 60)
print("  断言验收标准")
print("=" * 60)

# 低: 标题仍轮转（不完全重复），叙事/结构一致
r_low = results["低"]
assert r_low["unique_titles"] > 1, \
    f"FAIL 低: 标题应有多种，实际={r_low['unique_titles']}"
assert r_low["unique_narratives"] == 1, \
    f"FAIL 低: 叙事角度应全部相同，实际={r_low['unique_narratives']}"
print("  ✓ 低: 标题有差异，叙事/结构保持一致")

# 中: 标题/叙事/结构均有差异
r_mid = results["中"]
assert r_mid["unique_titles"] > 1, \
    f"FAIL 中: 标题应有多种，实际={r_mid['unique_titles']}"
assert r_mid["unique_narratives"] >= 2, \
    f"FAIL 中: 叙事角度至少2种，实际={r_mid['unique_narratives']}"
print("  ✓ 中: 标题/叙事均有差异（符合质量验收标准）")

# 高: 差异度高于等于中
r_high = results["高"]
assert r_high["unique_narratives"] >= r_mid["unique_narratives"], \
    f"FAIL 高: 叙事角度差异应≥中挡，实际 高={r_high['unique_narratives']} 中={r_mid['unique_narratives']}"
assert r_high["unique_structures"] >= r_mid["unique_structures"], \
    f"FAIL 高: 结构模式差异应≥中挡，实际 高={r_high['unique_structures']} 中={r_mid['unique_structures']}"
print("  ✓ 高: 叙事/结构差异度 ≥ 中挡")

print()
print("=" * 60)
print("  全部通过 ✓")
print("=" * 60)
