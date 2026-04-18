"""
validate_scene_variety.py — 本地快速验证 _assign_scenes 场景分配逻辑

不依赖飞书 API，纯数据模拟。覆盖以下边界：
  - pool < groups（之前 step=2 会退化的场景）
  - pool == groups
  - pool > groups
  - pool == 1（极端边界）

运行：
  cd middleware && python scripts/validate_scene_variety.py
"""
import sys
import random

# Fix Windows GBK stdout encoding
if sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def simulate_assign(pool_size: int, group_count: int, variety: str, n_trials: int = 500) -> float:
    """模拟 _assign_scenes 的分配逻辑，返回平均唯一场景率。"""
    pool = list(range(pool_size))

    def assign_once() -> list:
        start = random.randrange(len(pool))
        if variety == "高":
            n = len(pool)
            if n >= group_count:
                # 每个 group 取不重复的 scene
                return [pool[(start + j) % n] for j in range(group_count)]
            else:
                # pool 不够：多轮 shuffle 拼接，避免步长碰撞
                seq: list = []
                while len(seq) < group_count:
                    chunk = pool[:]
                    random.shuffle(chunk)
                    seq.extend(chunk)
                return seq[:group_count]
        else:
            return [pool[(start + i) % len(pool)] for i in range(group_count)]

    unique_rates = []
    for _ in range(n_trials):
        result = assign_once()
        unique_rates.append(len(set(result)) / len(result))

    avg = sum(unique_rates) / len(unique_rates)
    min_rate = min(unique_rates)
    return avg, min_rate


def check(pool_size: int, group_count: int, variety: str, min_avg: float = 0.5):
    avg, min_rate = simulate_assign(pool_size, group_count, variety)
    status = "✓" if avg >= min_avg else "✗"
    print(
        f"  {status} pool={pool_size:2d} groups={group_count:2d} variety={variety}: "
        f"avg_unique={avg:.1%}  min={min_rate:.1%}"
    )
    assert avg >= min_avg, (
        f"FAIL: pool={pool_size} groups={group_count} variety={variety} "
        f"avg_unique={avg:.1%} < threshold {min_avg:.0%}"
    )


print("=" * 60)
print("  scene_variety 边界验证")
print("=" * 60)

# ── 关键回归：之前 step=2 在偶数 pool 下退化的场景 ──────
print("\n[关键回归] 之前 step=2 退化场景：")
check(pool_size=2, group_count=3, variety="高", min_avg=0.60)   # pool < groups
check(pool_size=2, group_count=4, variety="高", min_avg=0.40)   # pool << groups
check(pool_size=4, group_count=3, variety="高", min_avg=0.90)   # pool > groups (可全唯一)

# ── 正常场景 ──────────────────────────────────────────────
print("\n[正常场景]")
check(pool_size=5, group_count=3, variety="高",  min_avg=0.95)  # 应全唯一
check(pool_size=5, group_count=5, variety="高",  min_avg=0.95)  # 恰好够，应全唯一
check(pool_size=5, group_count=3, variety="中",  min_avg=0.50)
check(pool_size=5, group_count=3, variety="低",  min_avg=0.50)

# ── 极端边界 ─────────────────────────────────────────────
print("\n[极端边界]")
check(pool_size=1, group_count=3, variety="高",  min_avg=0.10)  # pool=1：全部相同，唯一率=1/3
check(pool_size=1, group_count=1, variety="高",  min_avg=0.90)  # 单 group 单 scene

print()
print("=" * 60)
print("  全部通过 ✓")
print("=" * 60)
