# Prompt 系统升级 v2：最终更新评估与针对性建议

> 评估时间：2026-04-18  
> 评估对象：最新 `origin/main`（HEAD: `ddf1010`）  
> 上轮参考：`docs/reviews/prompt-upgrade-v2-latest-review-2026-04-18.md`、`docs/reviews/prompt-upgrade-v2-final-implementation-2026-04-18.md`  
> 本轮重点：验证 Prompt v2 最终收口是否真正完成三方协同匹配、函数级测试补强，以及识别残余工程风险

---

## 1. 结论摘要

本轮更新是**有效且关键的最终收口**。

当前已确认：
- `strategy.人设适配标签` 已接入 Persona 评分
- `persona.适合场景标签` 已接入 Persona 评分
- Persona 批内去重已从 `id(r)` 改为 `record_id`
- 已新增直接调用真实 `ContentGenerationHandler` 方法的函数级回归测试
- `setup_v2_schema.py` 的 `system.yaml` 写回逻辑已从固定字符串替换升级为 regex 容错写回
- 既有逻辑镜像测试与新增函数级测试在合适解释器下均通过

综合判断：

**Prompt v2 的主链路、三方协同匹配、以及基础测试闭环已基本完成，当前版本已经达到“可用、可回归、可做真实样本验收”的状态。**

但需要明确：

**当前仍存在一个明确的工程兼容性问题：新增函数级测试脚本在 Python 3.9 环境下不可运行，因此项目的 Python 版本要求需要被显式声明并统一。**

---

## 2. 本轮已确认完成的关键改进

## 2.1 `strategy → persona` 标签评分已真实进入生产逻辑

### 代码事实
在 `middleware/handlers/content_generation.py` 的 `_assign_personas()` 中：
- 新增 `_strategy_tag_cache`
- 新增 `_get_strategy_tags(content_type)`
- 通过 `_lookup_strategy(content_type, platform, category)` 拉取 Strategy
- 将 `strategy.人设适配标签` 与 `persona.气质标签` 的交集计入 `_soft_score()`

关键逻辑：

```python
strategy_tags = _get_strategy_tags(content_type)
sc += len(strategy_tags & qi_zhi)
```

### 影响
这意味着 Strategy 配置现在不再只是文档层字段，而会真实影响 Persona 选择。

### 评估
这是上一轮 review 中最关键的未闭环项之一；本轮已实质完成。

---

## 2.2 `persona → scene` 场景适配已进入生产逻辑

### 代码事实
`_assign_scenes()` 现在会向 scene dict 写入：

```python
"场景主题": f.get_option(scene, "场景主题")
```

随后 `_soft_score()` 中新增：

```python
scene_theme = scene_dict.get("场景主题", "")
if scene_theme:
    persona_scene_tags = set(f.get_options(prec, "适合场景标签") or [])
    if scene_theme in persona_scene_tags:
        sc += 1.0
```

### 影响
当前评分已具备：
- scene → persona 的适配
- persona → scene 的反向适配

### 评估
三方协同匹配比上一轮明显更接近 PRD 目标，不再是单向弱匹配。

---

## 2.3 Persona 去重已改为基于业务主键 `record_id`

### 代码事实
旧逻辑：

```python
_used_ids.append(id(chosen))
```

新逻辑：

```python
_used_rec_ids.add(chosen.get("record_id"))
```

候选筛选也同步改为基于 `record_id`。

### 影响
- 语义更清晰
- 不依赖 Python 对象内存身份
- 批内去重更符合业务对象模型

### 评估
这是一个正确且必要的小修，提升了可维护性与行为可解释性。

---

## 2.4 已新增真实 Handler 方法级回归测试

### 代码事实
新增脚本：
- `middleware/scripts/validate_handler_units.py`

该脚本通过：
- `MockFeishu`
- `MockStorage`
- 注入空 `db` 模块

直接实例化真实 `ContentGenerationHandler`，并调用：
- `_assign_scenes()`
- `_assign_personas()`
- `_build_creative_briefs()`

### 与上一轮的差异
上一轮脚本主要是“逻辑镜像验证”，本轮新增脚本属于“真实函数回归验证”。

### 评估
这是本轮工程价值最高的改进之一，因为它显著提高了验证可信度。

---

## 2.5 `setup_v2_schema.py` 的写回健壮性继续提升

### 代码事实
旧逻辑依赖固定字符串替换：

```python
content.replace('persona:      ""', ...)
```

新逻辑改为 `re.subn(...)`：

```python
new_content, n_subs = re.subn(
    r'(persona:\s*)(["\']?\s*["\']?)\s*$',
    rf'\g<1>{persona_table_id}',
    content,
    flags=re.MULTILINE,
)
```

若未匹配成功，还会输出 warning。

### 评估
虽然还不是 YAML 解析级写回，但已明显优于上一版的脆弱替换方式。

---

## 3. 本轮验证记录

## 3.1 在 Python 3.11 环境下的验证

已执行：

```bash
cd /Users/carson/workspace/ai-content-hub
python --version
python -m py_compile middleware/handlers/content_generation.py \
  middleware/scripts/setup_v2_schema.py \
  middleware/scripts/validate_handler_units.py

cd middleware
python scripts/validate_handler_units.py
python scripts/validate_scene_variety.py
python scripts/validate_diff_strength.py
python scripts/validate_persona_path.py
```

### 结果
- `python` = `3.11.15`
- `py_compile` ✅
- `validate_handler_units.py` ✅（8/8）
- `validate_scene_variety.py` ✅
- `validate_diff_strength.py` ✅
- `validate_persona_path.py` ✅

---

## 3.2 在 Python 3.9 环境下的兼容性检查

已执行：

```bash
python3 --version
cd /Users/carson/workspace/ai-content-hub
python3 -m py_compile middleware/handlers/content_generation.py \
  middleware/scripts/setup_v2_schema.py \
  middleware/scripts/validate_handler_units.py

cd middleware
python3 scripts/validate_handler_units.py
```

### 结果
- `python3` = `3.9.6`
- `py_compile` 可通过部分文件，但运行 `validate_handler_units.py` 失败
- 失败根因：导入链中的 `middleware/adapters/feishu.py` 使用 `str | None` 注解，Python 3.9 不支持

错误特征：

```text
TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'
```

---

## 4. 仍然存在的问题

## Important

### 4.1 Python 版本要求未显式统一，导致新增函数级测试脚本在部分环境不可运行

### 事实
当前本机环境中：
- `python` → 3.11.15
- `python3` → 3.9.6

而新增函数级测试脚本依赖的导入链使用了 Python 3.10+ 才支持的类型注解语法。

### 影响
如果文档或执行习惯使用：

```bash
python3 scripts/validate_handler_units.py
```

则在 Python 3.9 环境会失败。

### 风险
这会造成：
- 文档命令与实际运行结果不一致
- 测试脚本在不同机器上的可执行性不稳定
- 团队成员可能误判为代码逻辑问题，实则是解释器版本问题

### 建议
建议按以下顺序处理：
1. 在项目文档中显式声明最低 Python 版本（建议 3.11）
2. 所有验证命令统一改为 `python` 或显式 `python3.11`
3. 若确实要求兼容 3.9，则需要对相关类型注解做兼容改造（例如 `Optional[...]` 或 `from __future__ import annotations`）

### 评估
这不是业务逻辑 bug，但它是一个**明确且可复现的工程兼容性问题**，应该被纳入收尾清单。

---

## Minor

### 4.2 `setup_v2_schema.py` 仍不是严格 YAML 解析写回

### 事实
当前写回方式已从字符串替换升级为 regex，但仍不是通过 YAML 解析器进行结构化修改。

### 影响
当前方案在本轮范围内是够用的，但长期看仍有边界风险。

### 建议
若脚本后续会持续维护，建议未来升级为 YAML 读写；若短期只需稳定收尾，则当前优先级不高。

---

### 4.3 函数级测试仍不等于 Feishu 端到端集成测试

### 事实
`validate_handler_units.py` 使用的是 `MockFeishu`，并未访问真实 Feishu API。

### 影响
当前测试能证明 Handler 内部逻辑正确，但不能证明：
- 真实飞书字段状态完全一致
- API 分页 / 权限 / 网络异常处理无问题
- 真实端到端链路稳定

### 建议
若准备做最终验收，下一步仍需要补一轮：
- 真实 Feishu 联调
- 真实样本生成回归

---

## 5. 综合结论

### 已达到
- Prompt v2 主链路基本完成
- 三方协同匹配已实质落地
- 测试可信度已从“镜像逻辑”提升到“真实函数回归”
- 批内 persona 去重与 schema 写回健壮性进一步增强

### 尚未完全达到
- Python 版本要求尚未工程化收口
- 仍未完成真实 Feishu / 真实样本级最终验收

### 工程判断
**当前版本可以判定为“功能闭环基本完成，工程上进入最终验收前状态”。**

如果只从代码与本地验证层面判断，Prompt v2 已具备较高可信度；
如果从交付层面判断，下一步最重要的不是再改核心逻辑，而是：
- 统一 Python 版本要求
- 做真实样本回归
- 做真实 Feishu 联调确认

---

## 6. 针对性建议（按优先级）

### 第一优先级
1. 在仓库文档中显式声明最低 Python 版本（建议 3.11）
2. 将所有验证命令统一为 `python` 或 `python3.11`
3. 做一轮真实 Feishu + 真实样本回归

### 第二优先级
4. 若需要兼容 Python 3.9，统一处理 `| None` 等 3.10+ 语法
5. 为 `_soft_score` 的低命中情况增加可观测性日志，帮助运营识别配置不足

### 第三优先级
6. 视脚本长期维护需求，决定是否将 `setup_v2_schema.py` 升级为 YAML 解析写回

---

## 7. 建议给执行端的下一步任务定义

可直接转发：

> 请基于 `docs/reviews/prompt-upgrade-v2-final-review-2026-04-18.md` 继续完成 Prompt 系统升级 v2 的最终验收前收口。  
> 当前目标不是再改主逻辑，而是补齐运行环境与交付验证。  
> 请优先处理：  
> 1. 在仓库文档中明确最低 Python 版本（建议 3.11）；  
> 2. 统一所有验证命令，避免 `python3` 指向 3.9 导致脚本失败；  
> 3. 做一轮真实 Feishu 联调验证；  
> 4. 做一轮真实样本回归，重点检查标题差异度、叙事角度、人物一致性和 Persona 命中质量；  
> 5. 若要求兼容 Python 3.9，再评估类型注解兼容改造。  
> 每项改动或验证都必须附带：改动文件、关键 diff、验证命令、验证结果、残余风险。
