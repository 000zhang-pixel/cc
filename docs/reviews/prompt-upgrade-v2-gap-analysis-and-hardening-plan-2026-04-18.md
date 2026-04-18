# Prompt 系统升级 v2：评估结论与补强实施方案

> 评估时间：2026-04-18  
> 评估对象：`5a68aea` / `5adeaee` 对应的 Prompt 系统升级实现  
> 评估范围：`docs/prd/prompt-system-upgrade-v1-2026-04-17.md`、`docs/system-design.md`、`middleware/handlers/content_generation.py`、`middleware/core/local_storage.py`、`middleware/config/system.yaml`

---

## 1. 结论摘要

当前实现已经完成了 **v2 的主体骨架**：
- 已引入 `Creative Brief`
- 已新增 `Persona` 表配置入口
- 已开始将命中链路写入 表3 / 表4 / 本地 JSON
- 保持了单平台、飞书驱动、轮询执行架构不变

但从 **PRD 必达目标 / 验收标准** 看，当前状态应判定为：

**“已完成方向性升级，但尚未完全达标，仍需一轮针对性补强。”**

最关键的缺口有 3 个：
1. `persona_assignments` 已生成，但没有真正进入 Prompt 构建链路
2. `plan.json` 中的 briefs 过早落盘，导致命中信息不完整
3. 多个新配置字段只是读取了，尚未参与真实决策逻辑

---

## 2. 已完成项（与 PRD 对照）

### 2.1 已满足 / 基本满足

#### A. Creative Brief 已进入主流程
代码中已新增：
- `assign_scenes()`
- `assign_personas()`
- `build_creative_briefs()`
- `fill_prompts()` 中基于 brief 构建文案/图片 prompt

对应 PRD：
- 7.1 新流程
- 10.1 功能验收第 1 条

#### B. Persona 表是可选增强项，不阻断老链路
`middleware/config/system.yaml` 已增加：
- `feishu.tables.persona`

并且实现里对未配置 Persona 表的情况做了 fallback。

对应 PRD：
- 9.兼容性要求第 1、2、3 条

#### C. 标签没有被注入 Prompt
当前主链路仍然保持“标签用于结果写回，不进入 prompt”。

对应 PRD：
- 0.执行说明第 3 条
- 7.3 文案 Prompt 生成规则第 4 条
- 10.3 回归验收第 4 条

#### D. 可观测性已开始落地
已实现：
- 表3写入创意包摘要 / 命中信息 / 标题句式 / 叙事角度 / 一致性锚点
- 表4写入部分命中链路字段
- `content.json.debug` 写入 `strategy_id / scene_id / persona_id / shotplan_id / title_pattern / narrative_angle / failed_image_indexes`

对应 PRD：
- 4.1、6.3、8.1、8.2、10.1 第 2/3 条

---

## 3. 核心缺口（必须补强）

### P0-1：Persona 实际未进入 Prompt 生成链路

#### 现象
`handle()` 中虽然生成了：
- `persona_assignments = self._assign_personas(...)`

但调用 `_fill_prompts()` 时没有传入 `persona_assignments`：

```python
self._fill_prompts(prompt_records, sku_fields, cfg, tags, text_adapter, scene_assignments, briefs)
```

而 `_fill_prompts()` 自己又会在参数缺失时置空：

```python
if persona_assignments is None:
    persona_assignments = {}
```

因此：
- `_build_text_prompts_from_strategy(..., persona=persona)` 实际拿不到 persona
- `_build_image_master_prompt(..., persona=persona)` 实际拿不到 persona
- `_build_image_sub_prompts(..., persona=persona)` 实际拿不到 persona

#### 影响
这直接导致以下 PRD 目标未真正成立：
- 文案 Prompt 的人物感觉增强
- 图片 Prompt 的 persona anchor 优先于 Scene
- Persona 一致性模板参与组内一致性控制
- “人物更丰富 / 人设更可控”的升级目标未真正兑现

#### 对应 PRD
- 2.2 必达目标第 2 / 4 条
- 7.3 第 4 条
- 7.4 第 4 条
- 10.1 第 4 / 6 条

#### 处理建议
在 `handle()` 中调用 `_fill_prompts()` 时补传 `persona_assignments`：

```python
self._fill_prompts(
    prompt_records,
    sku_fields,
    cfg,
    tags,
    text_adapter,
    scene_assignments,
    briefs,
    persona_assignments,
)
```

并补充最小回归验证：
- Persona 表存在时：Prompt 中能看到 persona 信息
- Persona 表不存在时：仍走 Scene fallback，不报错

---

### P0-2：`plan.json` 的 briefs 命中信息不完整

#### 现象
当前 `briefs` 在 `strategy_id / shotplan_id` 还没补全前就被写入 `plan.json`：

```python
self._storage.update_plan(plan_code, {"briefs": briefs})
```

而：
- `strategy_id` 在 `_fill_prompts()` 内补
- `shotplan_id` 在 `_fill_prompts()` 内补

#### 影响
`plan.json` 中的 brief 大概率缺少：
- `strategy_id`
- `shotplan_id`

这与 PRD 对本地 JSON 可观测性的要求不一致。

#### 对应 PRD
- 8.1 plan.json 新增字段
- 10.2 质量验收第 4 条

#### 处理建议
二选一：

**方案 A（推荐）**
- 在 `_fill_prompts()` 完成后，再次把更新后的 `briefs` 回写到 `plan.json`

**方案 B**
- 将 strategy / shotplan lookup 前移，在 build brief 阶段就补齐命中信息

建议优先 A：改动小，风险低。

---

### P0-3：多个关键控制字段只读取未生效

#### 已读取但未真实生效
- `diff_strength`
- `consistency_strength`
- `scene_variety`

其中：
- `persona_mode` 已有实际行为
- 其余 3 个字段仍主要停留在“读入配置 / 写入 brief”层面

#### 影响
表2 新增控制项看起来已经支持，但实际上运营很难通过这些字段调控输出行为。

#### 对应 PRD
- 6.1 表2 控制字段
- 2.2 必达目标第 3 / 4 条

#### 处理建议
至少做以下最小落地：

**`diff_strength`**
- 低：标题句式 / 叙事角度轮转步幅小
- 中：默认当前逻辑
- 高：强制优先拉开 narrative_angle + structure_mode + persona + scene

**`consistency_strength`**
- 中：保留现有一致性约束
- 强：在 image master + sub-prompt 中注入更强的一致性语句，若 persona 有 `consistency_template` 则强制优先使用

**`scene_variety`**
- 低：允许复用邻近场景风格
- 中：当前逻辑
- 高：在 `_assign_scenes()` 中尽量避免相近 scene 重复

---

## 4. 重要缺口（建议本轮一起补）

### P1-1：`动作变化要求` 已读取但未进入 sub-prompt

#### 现象
代码读取了 ShotPlan 的：
- `动作变化要求`
- `禁止重复镜头`

但真正拼进 sub-prompt 的只有：
- `禁止重复镜头`

`动作变化要求` 当前未使用。

#### 对应 PRD
- 7.4 Sub-Prompt 应包含“当前人物动作变化”
- 6.5 ShotPlan 扩展字段第 5 条

#### 处理建议
将 `动作变化要求` 拼入每张图的 sub-prompt，例如：

```text
【动作变化】持握、走动、抬手、侧转，尽量避免动作重复
```

如后续要更精细，可做按 shot index 轮转。

---

### P1-2：Strategy / Scene / Persona 的软匹配只做了很小一部分

#### 当前未落地或基本未落地的字段
- `正文禁忌`
- `人设适配标签`
- `适合人设标签`
- `适合场景标签`
- `叙事角度标签`
- `结构模式`（未基于 Strategy 真正驱动）

#### 影响
当前系统更像：
- 默认池轮转
- 少量新字段注入

而不是 PRD 期望的：
- “配置驱动的差异化系统”

#### 对应 PRD
- 6.4 / 6.6 / 6.7 的业务规则
- 7.2 / 7.3 / 7.4

#### 建议拆分实施，不必一口气做完
**本轮最低要求：**
1. `正文禁忌` 注入 text system prompt
2. Persona 选择时参考 Strategy 的 `人设适配标签`
3. Persona / Scene 匹配时参考：
   - Persona 的 `适合场景标签`
   - Scene 的 `适合人设标签`
4. 若 Strategy 提供 `叙事角度标签` / `结构模式`，Brief 优先取表内值，而不是固定默认池

---

### P1-3：`Prompt描述模板` 读取了但没真正用起来

#### 现象
Persona 表里读取了：
- `Prompt描述模板`

但实际构建 Prompt 时，主要仍是 `appearance / style / action` 拼接。

#### 影响
运营配置 Persona 的表达力没有完全传递到模型输入。

#### 建议
最小方案：
- 若 `Prompt描述模板` 有值，则优先把它作为 persona 描述主体
- `appearance / style / action` 作为补充 fallback

适用位置：
- image master prompt
- text prompt 中的 persona block

---

## 5. 可观测性补强建议

### P1-4：`content.json` / 表4 的图片调试信息还不够

#### 当前已有
- `failed_image_indexes`
- brief summary
- 命中链路字段

#### 当前缺少
- 每张图实际 sub-prompt
- master prompt 摘要或 hash
- 图片补传 / 重试信息
- 失败图片对应异常摘要

#### 对应 PRD
- 6.3 表4 中“图片生成调试信息”
- 8.2 content.json debug block 示例

#### 建议
本轮最低要求：
- `content.json.debug.image_prompts = [...]`
- `content.json.debug.image_failures = [{index, error}]`

表4 可以先不塞完整 JSON，只落：
- 图片生成调试信息（摘要版）

---

## 6. 建议实施顺序（给 Windows Claude Code）

### 阶段 1：先修功能断点（必须先做）

#### Task 1.1 让 Persona 真正进入 Prompt 构建链路
**改动点**
- `handle()` → `_fill_prompts()` 传入 `persona_assignments`
- 确认 `_build_text_prompts_from_strategy` / `_build_image_master_prompt` / `_build_image_sub_prompts` 已吃到 persona

**验收标准**
- Persona 表存在时，Prompt 文本中能看到 persona 描述或一致性模板
- Persona 表缺失时，系统仍可运行

#### Task 1.2 修复 `plan.json` briefs 命中信息不完整
**改动点**
- `_fill_prompts()` 后重新落盘 `briefs`
- 或前移 strategy/shotplan lookup

**验收标准**
- `plan.json.briefs[*]` 含 `strategy_id / scene_id / persona_id / shotplan_id / title_pattern / narrative_angle / structure_mode`

---

### 阶段 2：补齐最小可控性（建议同一轮完成）

#### Task 2.1 让 `动作变化要求` 进入 sub-prompt
**验收标准**
- ShotPlan 配了 `动作变化要求` 时，每张图的 sub-prompt 能看到相关动作提示

#### Task 2.2 让 `consistency_strength` 真正影响 prompt
**建议规则**
- `中`：现有一致性约束
- `强`：附加更明确约束：人物/服装/发型/面部/产品细节禁止漂移

**验收标准**
- 同样的输入下，`强` 比 `中` 产生更强的人物一致性提示文本

#### Task 2.3 让 `正文禁忌` 进入文案 system prompt
**验收标准**
- Strategy 配置 `正文禁忌` 后，system prompt 中可见对应禁忌项

---

### 阶段 3：补齐软匹配与差异化控制（第二优先级）

#### Task 3.1 Persona / Scene / Strategy 软匹配
**建议最小实现**
Persona 候选排序分：
- 品类匹配
- 内容类型匹配
- Strategy `人设适配标签` 命中
- Scene `适合人设标签` 命中
- Persona `适合场景标签` 命中
- Persona 优先级

**验收标准**
- 在有标签配置时，persona 分配不再只按优先级/随机轮转

#### Task 3.2 Brief 优先使用 Strategy 的 `叙事角度标签` / `结构模式`
**验收标准**
- Strategy 配置了这些字段时，brief 中优先使用表内值
- 缺失时再走默认池 fallback

#### Task 3.3 `scene_variety` / `diff_strength` 进入行为逻辑
**验收标准**
- 不同强度设置下，brief 的 scene / narrative / structure 组合有明显差异

---

### 阶段 4：补齐可观测性（建议本轮尾声完成）

#### Task 4.1 把图片 prompt 调试信息写入本地 JSON
**建议字段**
```json
{
  "debug": {
    "image_prompts": ["master + sub1", "master + sub2"],
    "image_failures": [{"index": 1, "error": "..."}]
  }
}
```

#### Task 4.2 表4 写入摘要版图片调试信息
**建议字段**
- `图片生成调试信息`

**验收标准**
- 出图失败时，能快速定位失败图序号与对应 prompt 片段

---

## 7. 建议的验证清单

### 7.1 静态验证
- `python -m py_compile middleware/handlers/content_generation.py middleware/core/local_storage.py`
- 若有测试框架，补最少 3 个单测/集成测试：
  1. Persona present path
  2. Persona absent fallback path
  3. plan.json observability path

### 7.2 伪数据回归验证
至少构造以下场景：

#### Case A：无 Persona 表
- 期望：正常生成，人物信息回退 Scene

#### Case B：有 Persona 表，`人设模式=固定主人设`
- 期望：同一任务所有 group 使用同一 persona

#### Case C：有 Persona 表，`人设模式=多人设轮换`
- 期望：不同 group 使用不同 persona

#### Case D：ShotPlan 配置 `动作变化要求` + `禁止重复镜头`
- 期望：sub-prompt 同时体现动作和构图限制

#### Case E：Strategy 配置 `正文禁忌` + `标题句式池`
- 期望：system prompt 和 user prompt 中出现对应控制信息

### 7.3 回归验收
必须确认不破坏：
- AI全创作
- 图片实拍+AI文案
- 视频实拍+AI文案
- 发布链路
- 标签写回逻辑

---

## 8. 建议 Claude Code 执行原则

1. **先修 P0，再修 P1**，不要一口气大重构
2. **优先最小改动闭环**，不要把当前可运行链路打散
3. 每完成一项，都要补：
   - 代码证据
   - 验证命令
   - 未验证项
4. 如果飞书表还没补字段，代码必须 fallback，不得阻断旧任务
5. 若需要拆函数，优先围绕：
   - `_fill_prompts()`
   - `_assign_personas()`
   - `_build_creative_briefs()`
   - `_generate_content()`

---

## 9. 我给 Windows Claude Code 的最终任务定义

可以直接转发下面这段：

> 请基于 `docs/reviews/prompt-upgrade-v2-gap-analysis-and-hardening-plan-2026-04-18.md` 执行 Prompt 系统升级 v2 的补强实现。  
> 目标：在不破坏现有单平台飞书驱动主链路的前提下，优先修复 Persona 未进入 Prompt 链路、plan.json briefs 命中信息不完整、关键控制字段未生效等问题。  
> 请按文档中的阶段顺序实施：先 P0，再 P1，再做可观测性增强。  
> 每完成一项必须提供：改动文件、关键 diff、验证命令、验证结果、残余风险。  
> 若飞书新增字段不存在，必须 fallback，不得阻断旧任务。

---

## 10. 本次本机验证记录

已执行：

```bash
cd /Users/carson/workspace/ai-content-hub
python3 -m py_compile middleware/handlers/content_generation.py middleware/core/local_storage.py
```

结果：✅ 通过

说明：
- 当前结论基于代码审阅 + 静态编译检查
- 尚未完成真实飞书/模型调用级联验证
- 尚未完成样本生成质量验收
