# Prompt 系统升级 v2：最终收口实施记录

> 实施时间：2026-04-18  
> 对照评估文档：`docs/reviews/prompt-upgrade-v2-latest-review-2026-04-18.md`  
> 实施范围：`middleware/handlers/content_generation.py`、`middleware/scripts/setup_v2_schema.py`  
> 新增验证脚本：`middleware/scripts/validate_handler_units.py`

---

## 1. 本轮实施结论

基于最新评估文档的全部 Important / Minor 建议，已完成所有优先级 1、2 改动，并通过：

- ✅ `validate_handler_units.py` 8 个函数级 case 全部通过（直接调用真实 Handler 方法）
- ✅ `python -m py_compile` 静态检查通过（3 个文件）
- ✅ 已有 3 个逻辑镜像脚本（validate_scene_variety / diff_strength / persona_path）不受影响

**综合判断：PRD 级三方协同匹配已全量落地，测试层从"逻辑镜像"升级为"真实函数回归"。**

---

## 2. 各项改动明细

### 2.1 Important — 将 `strategy.人设适配标签` 接入 Persona 评分

**问题**：旧版 `_soft_score` 未使用 Strategy 表的 `人设适配标签`，导致策略配置对人设选择无影响。

**修复**（`_assign_personas()` 内部）：

新增 `_strategy_tag_cache` + `_get_strategy_tags()` 辅助：

```python
_strategy_tag_cache: dict = {}
_platform = (cfg.get("platforms") or [""])[0]
_category = cfg.get("_category", "")

def _get_strategy_tags(ct: str) -> set:
    if ct not in _strategy_tag_cache:
        try:
            strat = self._lookup_strategy(ct, _platform, _category)
            tags = set(f.get_options(strat, "人设适配标签") or []) if strat else set()
        except Exception:
            tags = set()
        _strategy_tag_cache[ct] = tags
    return _strategy_tag_cache[ct]
```

`_soft_score` 新增评分项：
```python
# +1 per strategy 人设适配标签 that overlaps with persona 气质标签
strategy_tags = _get_strategy_tags(content_type)
sc += len(strategy_tags & qi_zhi)
```

**策略缓存设计**：相同 content_type 只查一次飞书，避免重复 API 调用。失败时静默 fallback（返回空集合），不阻断任务。

---

### 2.2 Important — 将 `persona.适合场景标签` 接入 Persona 评分

**问题**：旧版评分只使用 `scene.适合人设标签 ∩ persona.气质标签`，未利用 `persona.适合场景标签`，忽略了人设对场景的主动适配。

**修复**（`_soft_score` 内部）：

```python
# +1 if persona 适合场景标签 contains the scene's 场景主题
scene_theme = scene_dict.get("场景主题", "")
if scene_theme:
    persona_scene_tags = set(f.get_options(prec, "适合场景标签") or [])
    if scene_theme in persona_scene_tags:
        sc += 1.0
```

同时，`_assign_scenes()` 现在向 scene dict 写入 `"场景主题"` 字段：

```python
"场景主题": f.get_option(scene, "场景主题"),
```

---

### 2.3 完整更新后的 `_soft_score` 评分逻辑（5 维）

| 评分项 | 分值 | 说明 |
|--------|------|------|
| 内容类型命中 | +2.0 | persona.适用内容类型 含 content_type |
| scene→persona 气质重叠 | +N | scene.适合人设标签 ∩ persona.气质标签 |
| persona→scene 场景命中 | +1.0 | scene.场景主题 in persona.适合场景标签 |
| strategy→persona 气质重叠 | +N | strategy.人设适配标签 ∩ persona.气质标签 |
| 优先级微权重 | +0~1 | int(优先级) / 200.0，作为 tiebreaker |

---

### 2.4 Minor — Persona 去重从 `id(r)` 改为 `record_id`

**问题**：旧版使用 Python 对象 `id(r)` 跟踪已使用人设，依赖对象身份，语义不稳定。

**修复**：

```python
# 旧
_used_ids: list = []
candidates = [r for r in persona_pool if id(r) not in _used_ids] or persona_pool
_used_ids.append(id(chosen))

# 新
_used_rec_ids: set = set()
candidates = [r for r in persona_pool if r.get("record_id") not in _used_rec_ids] or persona_pool
_used_rec_ids.add(chosen.get("record_id"))
```

使用 `set` 替代 `list` 提升查找效率；用业务 ID 而非内存地址标识对象。

---

### 2.5 Minor — `setup_v2_schema.py` YAML 写回改为 regex

**问题**：旧版用字符串替换写回 `system.yaml`，格式变化时会静默失败。

**修复**：

```python
import re

new_content, n_subs = re.subn(
    r'(persona:\s*)(["\']?\s*["\']?)\s*$',
    rf'\g<1>{persona_table_id}',
    content,
    flags=re.MULTILINE,
)
if n_subs == 0:
    print(f"\n  ⚠ system.yaml 中未找到空 persona 条目，请手动更新 persona: {persona_table_id}")
else:
    with open(_yaml_path, "w", encoding="utf-8") as f_:
        f_.write(new_content)
    print(f"\n  ✓ system.yaml 已更新 persona: {persona_table_id}")
```

- 容忍空格、引号格式变化
- 替换失败时输出明确警告，而非静默写错

---

### 2.6 新增函数级回归测试脚本 `validate_handler_units.py`

**问题**：已有 3 个验证脚本均为"逻辑镜像验证"，若生产代码偏离脚本实现，脚本仍可通过。

**修复**：新增 `middleware/scripts/validate_handler_units.py`，通过 `MockFeishu` + `MockStorage` 实例化真实 `ContentGenerationHandler`，直接调用生产方法。

**MockFeishu 设计**：
- 实现与 `FeishuClient` 相同的 `get_text / get_option / get_options / get_number / list_records` API
- `list_records` 从本地 `table_data` 字典返回数据（忽略 filter_str）
- `update_record / create_record` 为 no-op，不影响测试

**db 模块处理**：通过 `sys.modules` 注入空 `db` 模块，避免 import 触发 DB 连接。

---

## 3. 验证结果

### 3.1 函数级回归测试（新增）

```bash
cd middleware && python scripts/validate_handler_units.py
```

| Case | 验证项 | 结果 |
|------|--------|------|
| 1 | `_assign_scenes`: pool=2 groups=3 variety=高 avg_unique≥1.5 | ✓ |
| 2 | `_assign_scenes`: 返回全部组，含 道具建议/适合人设标签/场景主题 | ✓ |
| 3 | `_assign_personas`: strategy+scene 标签命中时 PS001 胜出 | ✓ |
| 4 | `_assign_personas`: 3 组 3 人设各不重复（record_id 去重） | ✓ |
| 5 | `_assign_personas`: 固定主人设 → 3 组相同 | ✓ |
| 6 | `_build_creative_briefs`: 低 → 标题有差异，叙事/结构固定 | ✓ |
| 7 | `_build_creative_briefs`: 中 → 标题/叙事均有差异 | ✓ |
| 8 | `_build_creative_briefs`: 高 叙事差异度 ≥ 中 | ✓ |

**全部通过 ✓（8/8）**

### 3.2 静态检查

```bash
python -m py_compile middleware/handlers/content_generation.py
python -m py_compile middleware/scripts/setup_v2_schema.py
python -m py_compile middleware/scripts/validate_handler_units.py
```

结果：✅ 三文件均通过，无语法错误

### 3.3 已有逻辑镜像脚本（不受影响）

| 脚本 | 通过 |
|------|------|
| `validate_scene_variety.py` | ✅（9 case）|
| `validate_diff_strength.py` | ✅（5 case）|
| `validate_persona_path.py`  | ✅（4 case）|

---

## 4. 残余风险最终状态

| 风险 | 状态 | 消除方式 |
|------|------|---------|
| strategy→persona 标签未接入评分 | ✅ 已消除 | `_get_strategy_tags()` + 评分项新增 |
| persona→scene 标签未接入评分 | ✅ 已消除 | `场景主题` 写入 scene_dict，`_soft_score` 新增评分项 |
| 测试仅为逻辑镜像，缺真实函数层 | ✅ 已消除 | `validate_handler_units.py` 直接调用生产方法 |
| Persona 去重依赖 `id(r)` | ✅ 已消除 | 改为 `record_id` + `set` 去重 |
| YAML 写回字符串替换易失效 | ✅ 已消除 | 改为 regex + 失败警告 |

---

## 5. 尚未完成项（第三优先级，可后续排期）

| 项目 | 说明 |
|------|------|
| 真实样本回归验证 | 3 组图文的标题差异度 / 一致性质量需人工验收 |
| `_soft_score` 降级感知日志 | 当标签命中为零时输出 WARNING，提示运营补充配置 |
| 真实 Feishu 端到端集成测试 | MockFeishu 不覆盖网络层；需 staging 环境跑完整链路 |

---

## 6. 本轮 Commit 记录

| Commit | 内容 |
|--------|------|
| 本次 | feat: Prompt v2 最终收口 — strategy/persona 标签评分 + 函数级测试 + 工程健壮性 |

### 改动文件汇总

| 文件 | 改动类型 | 行数变化 |
|------|----------|----------|
| `middleware/handlers/content_generation.py` | fix/feat | +38/-6 |
| `middleware/scripts/setup_v2_schema.py` | fix | +9/-5 |
| `middleware/scripts/validate_handler_units.py` | test | +270（新建）|
