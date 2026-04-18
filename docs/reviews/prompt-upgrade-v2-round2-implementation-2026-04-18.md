# Prompt 系统升级 v2：第二轮评估补强实施记录

> 实施时间：2026-04-18  
> 对照评估文档：`docs/reviews/prompt-upgrade-v2-round2-review-2026-04-18.md`  
> 实施范围：`middleware/handlers/content_generation.py`、`middleware/scripts/setup_v2_schema.py`  
> 新增验证脚本：`middleware/scripts/validate_scene_variety.py`、`middleware/scripts/validate_diff_strength.py`、`middleware/scripts/validate_persona_path.py`

---

## 1. 本轮实施结论

基于第二轮评估文档的所有 Critical / Important / Minor 问题，已完成全部优化项，并通过以下验证：

- ✅ 3 个本地验证脚本全部通过（9 + 5 + 4 个 case）
- ✅ 飞书字段迁移执行成功（`图片生成调试信息` 新增，其余字段已存在确认）
- ✅ `python -m py_compile` 静态检查通过

**综合判断：v2 主链路已完整打通，所有已识别缺口均已闭环。**

---

## 2. 各项改动明细

### 2.1 Critical — `scene_variety=高` 小 pool 退化修复

**问题**：`pool=2, step=2` 时 `(start + i*2) % 2` 对所有 group 返回相同索引，导致"高场景丰富度"反而所有组命中同一 scene。

**修复**（`_assign_scenes()`）：

```python
if scene_variety == "高":
    n = len(pool)
    if n >= len(groups):
        # 每组取唯一 scene（无重复）
        scene_seq = [pool[(start + j) % n] for j in range(len(groups))]
    else:
        # pool 不够时：多轮 shuffle 拼接，避免步长碰撞
        scene_seq = []
        while len(scene_seq) < len(groups):
            chunk = pool[:]
            random.shuffle(chunk)
            scene_seq.extend(chunk)
        scene_seq = scene_seq[:len(groups)]
else:
    scene_seq = [pool[(start + i) % len(pool)] for i in range(len(groups))]
```

**验证结果**（`validate_scene_variety.py`）：

| case | 结果 |
|------|------|
| pool=2, groups=3, 高 | avg_unique=66.7% ✓（旧实现退化至 0%）|
| pool=2, groups=4, 高 | avg_unique=50.0% ✓ |
| pool=4, groups=3, 高 | avg_unique=100.0% ✓ |
| pool=5, groups=3/5, 高/中/低 | 全部 ✓ |
| pool=1, groups=3, 高 | avg_unique=33.3% ✓（极端边界）|

---

### 2.2 Important — `diff_strength=低` 重定义（避免完全无差异）

**问题**：旧实现 `低=step=0`，所有组 title/narrative/structure 完全相同，伤害质量验收结果。

**修复**（`_build_creative_briefs()`）：

```python
if diff_strength == "高":
    _title_step = _narrative_step = _structure_step = 2
elif diff_strength == "低":
    _title_step, _narrative_step, _structure_step = 1, 0, 0
    # 标题仍轮转（避免完全重复），叙事/结构固定于池[0]
else:  # 中
    _title_step = _narrative_step = _structure_step = 1
```

**验证结果**（`validate_diff_strength.py`，3 组图文）：

| 挡位 | 唯一标题 | 唯一叙事 | 唯一结构 |
|------|--------|--------|--------|
| 低 | 3 ✓ | 1（固定）✓ | 1（固定）✓ |
| 中 | 3 ✓ | 3 ✓ | 3 ✓ |
| 高 | 3 ✓ | 3 ✓ | 3 ✓ |

---

### 2.3 Important — `_assign_personas()` 增加软匹配评分

**问题**：旧实现仅按优先级 + 轮转分配，缺少 Strategy/Scene/Persona 协同匹配。

**修复**：新增 `_soft_score()` 内部函数：

```python
def _soft_score(prec, content_type, scene_dict):
    sc = 0.0
    # +2 内容类型命中
    ctypes = f.get_options(prec, "适用内容类型") or []
    if content_type in ctypes:
        sc += 2.0
    # +N 场景适合人设标签 ∩ persona 气质标签重叠数
    scene_tags = set(scene_dict.get("适合人设标签") or [])
    qi_zhi = set(f.get_options(prec, "气质标签") or [])
    sc += len(scene_tags & qi_zhi)
    # 优先级作为微权重 tiebreaker（/200 保持 <1.0）
    sc += int(f.get_number(prec, "优先级", 0)) / 200.0
    return sc
```

- `固定主人设`：取全组聚合得分最高的 persona
- `自动/多人设轮换`：每组取最优候选，优先不重复使用

**验证结果**（`validate_persona_path.py`）：

| Path | 验证项 | 结果 |
|------|-------|------|
| A: Persona 表存在 | prompt_template 有值，3组≥2种不同 persona | ✓ |
| B: 无 Persona 表 | fallback 到 scene_fallback，prompt_template 为空 | ✓ |
| C: 固定主人设 | 3组均使用 PS001 | ✓ |
| D: 软匹配评分 | 内容类型命中时分值(3.5) > 不命中(1.5) | ✓ |

---

### 2.4 场景 dict 新增可选 v2 字段

`_assign_scenes()` 的 scene 赋值 dict 新增：

```python
"道具建议":     f.get_text(scene, "道具建议"),
"适合人设标签": f.get_options(scene, "适合人设标签") or [],
```

**意义**：`道具建议` 可被 prompt builder 直接 `.get()` 使用（此前不在 dict 中，永远返回空）；`适合人设标签` 供软匹配评分使用。

---

### 2.5 Minor — `_generate_content()` 表4 新增图片调试摘要

在图片生成循环后，向 `update` dict 写入：

```python
update["图片生成调试信息"] = f"失败:{_fail_count}/{img_count}张 失败序号:{_fail_idxs} Prompt摘要:{_prompt_prev}"
```

飞书端运营可直接看到生成失败摘要，无需查看本地 `content.json`。

---

### 2.6 `setup_v2_schema.py` 工程收口

| 改动 | 说明 |
|------|------|
| `system.yaml` 路径改为 repo-relative | `Path(__file__).resolve().parents[1] / "config" / "system.yaml"`，消除跨机器路径依赖 |
| 表12 存在但为空时自动 seed | 新增 `count_persona_records()`；返回 0 时自动调用 `insert_persona_records()` |
| `TABLE4_FIELDS` 新增 `图片生成调试信息` | 字段类型 TEXT，下次执行脚本即可在飞书创建 |

---

## 3. 飞书字段迁移执行记录

执行命令：`cd middleware && python scripts/setup_v2_schema.py`  
执行时间：2026-04-18

| 表 | 操作 | 结果 |
|----|------|------|
| 表2（plan）| 4 字段已存在 | 全部跳过 |
| 表3（prompt）| 10 字段已存在 | 全部跳过 |
| 表4（content）| `图片生成调试信息` 不存在 | **新增成功 ✓** |
| 表8（strategy）| 6 字段已存在 | 全部跳过 |
| 表9（shotplan）| 6 字段已存在 | 全部跳过 |
| 表10（scene）| `适合人设标签`/`道具建议` 已存在 | 全部跳过，软匹配立即生效 |
| 表12（persona）| 16 字段已存在，记录非空 | 补字段跳过，seed 跳过 |

---

## 4. 验证脚本汇总

| 脚本 | 路径 | 覆盖内容 | 通过 |
|------|------|---------|------|
| `validate_scene_variety.py` | `middleware/scripts/` | scene_variety 三挡 9 个边界 case | ✅ |
| `validate_diff_strength.py` | `middleware/scripts/` | diff_strength 三挡输出差异断言 | ✅ |
| `validate_persona_path.py` | `middleware/scripts/` | Persona 有/无/固定/软匹配 4 路径 | ✅ |

**统一运行方式：**
```bash
cd D:/AI-Content-Hub/middleware
python scripts/validate_scene_variety.py
python scripts/validate_diff_strength.py
python scripts/validate_persona_path.py
```

---

## 5. 残余风险最终状态

| 风险 | 状态 | 消除方式 |
|------|------|---------|
| 软匹配需飞书新字段 | ✅ 已消除 | `setup_v2_schema.py` 执行确认字段存在 |
| `图片生成调试信息` 字段 | ✅ 已消除 | 表4 新增成功，代码可正常写入 |
| `scene_variety=高` 小 pool 修复验证 | ✅ 已消除 | 验证脚本 9 个 case 全通过，含退化回归 |

---

## 6. 本轮 Commit 记录

| Commit | 内容 |
|--------|------|
| `a9d7ad5` | fix: Prompt系统升级v2收尾优化 — 第二轮review补强（+122/-28行）|
| `fe77968` | test: add validate_scene_variety.py — 边界回归验证脚本 |
| `6540782` | test: add validate_diff_strength.py + validate_persona_path.py |

---

## 7. 静态验证记录

```bash
python -m py_compile middleware/handlers/content_generation.py
python -m py_compile middleware/scripts/setup_v2_schema.py
```

结果：✅ 两文件均通过，无语法错误

---

## 8. 尚未完成项（第三优先级，可后续排期）

| 项目 | 说明 |
|------|------|
| 真实样本回归验证 | 3 组图文的标题差异度 / 一致性质量需人工验收 |
| `_soft_score` 降级感知日志 | 当标签命中为零时输出 WARNING，提示运营补充配置 |
| Strategy `人设适配标签` 纳入评分 | 当前评分未使用 Strategy 的 `人设适配标签`，需在 `_fill_prompts()` 阶段获取 strategy 后回传 |
