# Prompt 系统升级 v2：第二轮评估与优化建议

> 评估时间：2026-04-18  
> 评估对象：`92a79d2` / `fe4c25b` 对应的 Windows 端补强实现  
> 对照基线：`docs/reviews/prompt-upgrade-v2-gap-analysis-and-hardening-plan-2026-04-18.md`  
> 评估范围：`middleware/handlers/content_generation.py`、`middleware/config/system.yaml`、`middleware/scripts/setup_v2_schema.py`

---

## 1. 结论摘要

本轮补强是**有效且有实质进展**的。

相较上一轮，以下关键问题已明显改善：
- `persona_assignments` 已真正进入 Prompt 构建链路
- `plan.json` 中 briefs 已在 `_fill_prompts()` 后重新落盘
- `diff_strength / consistency_strength / scene_variety` 已开始参与行为逻辑
- `正文禁忌`、`Prompt描述模板`、`动作变化要求` 已开始进入 Prompt
- `content.json.debug` 已新增 `image_prompts / image_failures`

综合判断：

**当前版本已基本补齐上一轮 P0 主缺口，可以视为“v2 主链路已打通”，但仍存在若干边界逻辑与配置治理问题，建议继续做一轮收尾优化。**

---

## 2. 本轮确认已修复 / 已明显改善的点

### 2.1 Persona 已真正进入 Prompt 链路

#### 证据
在 `handle()` 中，调用 `_fill_prompts()` 已补传 `persona_assignments`：

```python
self._fill_prompts(prompt_records, sku_fields, cfg, tags, text_adapter, scene_assignments, briefs, persona_assignments)
```

这修复了上一轮最核心的问题。

#### 结果
以下调用现在都能实际吃到 persona：
- `_build_text_prompts_from_strategy(..., persona=persona)`
- `_build_image_master_prompt(..., persona=persona)`
- `_build_image_sub_prompts(..., persona=persona)`

---

### 2.2 `plan.json` 的 briefs 已在 prompt 解析后重新落盘

#### 证据
`_fill_prompts()` 完成后增加了再次写回：

```python
self._storage.update_plan(plan_code, {"briefs": briefs})
```

#### 结果
上一轮 brief 中 `strategy_id / shotplan_id` 不完整的问题，已经有了明确修复路径。

---

### 2.3 `consistency_strength / diff_strength / scene_variety` 已开始生效

#### 已落地行为
- `scene_variety`：进入 `_assign_scenes()`，影响 scene 轮转步幅
- `diff_strength`：进入 `_build_creative_briefs()`，影响标题句式 / 叙事角度 / 结构模式的轮转步幅
- `consistency_strength`：进入图片 master prompt / sub-prompt 的一致性约束文本

#### 结果
这些字段不再只是“读入配置”，而是开始参与行为决策。

---

### 2.4 `正文禁忌` 已进入文案 system prompt

#### 证据
在 `_build_text_prompts_from_strategy()` 中：

```python
forbidden_text = f.get_text(strategy, "正文禁忌").strip()
if forbidden_text:
    system += f"\n\n【正文禁忌】以下表达绝对禁止出现：{forbidden_text}"
```

#### 结果
Strategy 的文案约束能力已增强，符合 PRD 方向。

---

### 2.5 `Prompt描述模板` 已开始真正参与 Persona 表达

#### 证据
当前实现已优先使用 `prompt_template`：
- 文案 `persona_block`
- 图片 `master prompt`
- 图片 `sub-prompt`

#### 结果
Persona 表的表达能力已比上一轮更接近“模板驱动”，而不是纯字段拼接。

---

### 2.6 `动作变化要求` 已进入 sub-prompt

#### 证据
当前 `_build_image_sub_prompts()` 已组合：
- `动作变化要求`
- `禁止重复镜头`

输出为：

```text
【构图约束】动作变化：...；禁止重复：...
```

#### 结果
上一轮明确缺失的动作层差异化控制，已补上。

---

### 2.7 图片调试信息已增强

#### 证据
在 `_generate_content()` 图片生成阶段新增：
- `_image_prompts`
- `_image_failures`

并写入：

```python
self._storage.update_content_debug(plan_code, gid, {
    "image_prompts": _image_prompts,
    "image_failures": _image_failures,
})
```

#### 结果
本地 `content.json.debug` 的可观测性进一步增强。

---

## 3. 本轮仍然存在的问题

## Critical

### 3.1 `scene_variety=高` 在小场景池下会退化，甚至可能导致所有 group 命中同一个 scene

#### 证据
当前实现：

```python
_scene_step = 2 if scene_variety == "高" else 1
scene = pool[(start + i * _scene_step) % len(pool)]
```

#### 问题说明
当 `len(pool) == 2` 时：
- `(start + i * 2) % 2 == start % 2`
- 所有 group 都会命中同一个 scene

这意味着“高场景丰富度”在某些真实数据规模下反而降低了差异性。

#### 影响
这与“场景丰富度=高”的预期相反，是一个明确的边界逻辑缺陷。

#### 建议
改成与池长度兼容的分配策略，例如：
1. `len(pool) <= 2` 时强制 `step=1`
2. 或选择与 `len(pool)` 互质的 step
3. 或先生成一轮不重复 scene 序列，再按序取值

---

## Important

### 3.2 Persona / Scene / Strategy 的软匹配仍未真正落地

#### 代码计数验证结果
我已检查 `content_generation.py`，当前这些字段仍未被实际使用：
- `人设适配标签` → 0 次
- `适合人设标签` → 0 次
- `适合场景标签` → 0 次

#### 当前状态
`_assign_personas()` 仍主要基于：
- `适用品类`
- `优先级`
- 固定/轮换模式

#### 影响
当前 Persona 分配仍更像“优先级轮转”，而不是 PRD 期望的：
- Strategy / Scene / Persona 协同软匹配

#### 建议
在 `_assign_personas()` 中补一个候选打分机制：
- 品类匹配
- 内容类型匹配
- Strategy `人设适配标签` 命中
- Scene `适合人设标签` 命中
- Persona `适合场景标签` 命中
- Persona 优先级

建议以“最小加权评分”方式落地，不必大重构。

---

### 3.3 `setup_v2_schema.py` 在“表12已存在”时不会自动补默认 Persona 数据

#### 证据
当前逻辑：
- 若 `persona_table_id` 已存在，只执行：
  - `setup_persona_table_fields(persona_table_id)`
- 不执行：
  - `insert_persona_records(persona_table_id)`

#### 风险
如果表12已创建但为空：
- 会补字段
- 不会补 seed 数据
- 运行时 Persona 池仍可能为空
- 系统仍回退 Scene fallback

#### 建议
增加分支：
- 若表12记录数为 0，则自动写入 `PERSONA_RECORDS`
- 若已有记录，则跳过 seed

---

### 3.4 `setup_v2_schema.py` 仍使用硬编码 Windows 路径写回 `system.yaml`

#### 证据
脚本中当前写死：

```python
yaml_path = "D:/AI-Content-Hub/middleware/config/system.yaml"
```

#### 影响
该脚本只能假设仓库位于固定路径：
- 不利于目录迁移
- 不利于后续维护
- 不利于跨机器复用

#### 建议
改为 repo-relative：

```python
from pathlib import Path
yaml_path = Path(__file__).resolve().parents[1] / "config" / "system.yaml"
```

---

### 3.5 `diff_strength=低` 目前过于极端，可能伤害质量验收结果

#### 证据
当前实现：

```python
_diff_step = {"低": 0, "中": 1, "高": 2}.get(diff_strength, 1)
```

`低=0` 的结果是：
- title pattern 不轮转
- narrative angle 不轮转
- structure mode 不轮转

#### 风险
这会让“低差异化”更像“几乎无差异”，从而与以下质量目标冲突：
- 同一任务 3 组图文标题句式不完全重复
- 同一任务 3 组图文叙事角度至少有 2 组不同

#### 建议
把 `低` 调整为“较弱轮转”，而不是“完全不轮转”。
例如：
- `低`: title/narrative 仍轮转，但 scene/persona 变化更少
- `中`: 当前默认
- `高`: 强化 title/narrative/scene/persona 四维差异

---

## Minor

### 3.6 表4 仍未承接“图片生成调试信息”字段

#### 当前状态
代码已把图片调试信息写入 `content.json.debug`：
- `image_prompts`
- `image_failures`

但表4目前仍未新增并写入类似：
- `图片生成调试信息`

#### 影响
开发本地排障更方便了，但运营在飞书端仍不能直接快速看到图片调试摘要。

#### 建议
如果希望飞书侧也有排障价值：
- 在表4新增 `图片生成调试信息`
- 写入摘要版而不是全量 prompt，避免字段过大

建议摘要内容：
- 失败数量
- 失败序号列表
- prompt hash 或前 120 字摘要

---

### 3.7 仍缺少真实样本与最小自动化验证

#### 当前已验证
已通过：

```bash
python3 -m py_compile middleware/handlers/content_generation.py middleware/scripts/setup_v2_schema.py middleware/core/local_storage.py
```

#### 仍未验证
- 真实 Feishu 字段存在/缺失时的 fallback 完整性
- 真实 Persona 表命中后的 prompt 实际效果
- 小样本 scene pool 下 `scene_variety` 的行为正确性
- 真实 3 组图文的差异性 / 一致性结果

#### 建议
最少增加：
1. Persona present / absent 路径验证
2. plan.json brief completeness 验证
3. `scene_variety` 小池边界验证
4. `diff_strength` 三挡输出差异验证

---

## 4. 本轮综合判断

### 4.1 已达到的层级
当前版本已经可以判断为：
- **主链路补强成功**
- **P0 主问题已基本解决**
- **Prompt v2 已具备可用性，不再只是“骨架版本”**

### 4.2 尚未完全达到的层级
仍未完全达到：
- PRD 中“配置协同驱动的人设/场景/策略软匹配”
- 小池场景下的差异化健壮性
- schema/setup 脚本的环境自适应与 seed 健壮性

### 4.3 工程结论
**可以进入“收尾优化 + 回归验证”阶段，而不是继续大改架构。**

---

## 5. 优化建议（按优先级）

### 第一优先级
1. 修复 `scene_variety=高` 在小场景池下的退化问题
2. 让 `setup_v2_schema.py` 在表12已存在但为空时自动补 seed 数据
3. 将 schema 脚本中的 `system.yaml` 路径改为 repo-relative

### 第二优先级
4. 为 `_assign_personas()` 增加软匹配打分逻辑
5. 调整 `diff_strength=低` 的定义，避免“完全无差异”
6. 给表4补“图片生成调试信息”摘要字段

### 第三优先级
7. 增加最小自动化测试 / 伪数据回归验证
8. 做一次真实样本回归，验证：
   - 3 组内容标题句式不完全重复
   - 至少 2 组 narrative angle 不同
   - 同组 5 张图人物一致性稳定

---

## 6. 建议给 Windows Claude Code 的下一步任务定义

可以直接转发下面这段：

> 请基于 `docs/reviews/prompt-upgrade-v2-round2-review-2026-04-18.md` 继续执行 Prompt 系统升级 v2 的收尾优化。  
> 当前目标不是重构，而是做边界修复与工程收口。  
> 请优先处理：  
> 1. 修复 `scene_variety=高` 在小 scene pool 下的退化问题；  
> 2. 增强 `setup_v2_schema.py`：表12已存在但为空时自动 seed 初始 Persona 数据；  
> 3. 将 schema 脚本写回 `system.yaml` 的路径改为 repo-relative；  
> 4. 继续补 Persona / Scene / Strategy 的软匹配打分逻辑；  
> 5. 重新定义 `diff_strength=低`，避免完全无差异。  
> 每项改动都必须附带：改动文件、关键 diff、验证命令、验证结果、残余风险。  
> 若飞书字段不存在，仍必须 fallback，不得阻断旧任务。

---

## 7. 本机验证记录

已执行：

```bash
cd /Users/carson/workspace/ai-content-hub
git pull --ff-only origin main
python3 -m py_compile middleware/handlers/content_generation.py middleware/scripts/setup_v2_schema.py middleware/core/local_storage.py
```

结果：
- `git pull` ✅
- `py_compile` ✅

说明：
- 本轮结论基于代码审阅 + 静态编译检查
- 未完成真实飞书写表验证
- 未完成真实模型生成质量回归验证
