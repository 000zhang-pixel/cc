# Multi-Model Image Architecture Roadmap

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 在不破坏当前双模型稳定生产链路的前提下，把 AI-Content-Hub 的图片生成系统从“gpt-image-2 / nanobanana-2 双模型专项实现”演进为“能力驱动、可持续接入更多模型”的多模型框架。

**Architecture:** 保留现有 creative brief、handler 主流程、adapter 工厂与飞书回写链路；优先抽离 Prompt Policy 层与 Model Capability Registry，让模型差异从分散 if/else 收敛到结构化配置 + 策略选择；最后再补模型路由与评估闭环。

**Tech Stack:** Python 3.11, middleware/handlers/content_generation.py, middleware/adapters/ai_models.py, YAML config, pytest, Feishu-based online regression.

---

## 0. 当前基线（实施前必须保持不退化）

### 0.1 已稳定事实
- `gpt-image-2` 已完成在线闭环回归，当前是默认主力生产图模。
- `gpt-image-2` 走 YAPS OpenAI-compatible Responses + `image_generation` tool + optional `input_image` 参考图。
- `nanobanana-2` 架构上保留为第二模型路线，但 provider 可用性仍待外部模型名确认。
- 图片 prompt 现结构为：
  - shared creative brief
  - model-specific master prompt
  - shared sub prompts
- 运行期逐张调用时实际送模内容为：
  - `master + "\n\n---\n\n" + sub`

### 0.2 当前不能破坏的生产约束
- 不修改 `gpt-image-2` 的 `size: "1024x1536"`
- 不推翻当前 handler 主链路
- 不改变 content/debug/fingerprint 证据链结构
- 不把 prompt 抽象成过度设计的大框架

---

## 1. 目标架构

系统分四层：

1. **Creative Brief Layer**
   - 输入：scene / persona / strategy / shotplan / consistency_anchor
   - 责任：提供模型无关的业务语义包

2. **Prompt Policy Layer**
   - 输入：creative brief + model capability
   - 输出：master prompt + sub prompts
   - 责任：把业务语义翻译成适配不同模型特征的提示词

3. **Adapter Layer**
   - 输入：rendered prompt + ref_images + execution_hints
   - 输出：raw image bytes
   - 责任：屏蔽 OpenAI/Gemini/Xiaole/VolcEngine 等协议差异

4. **Evaluation Layer**
   - 输入：生成结果 + debug metadata + online regression evidence
   - 输出：可比较的模型质量/稳定性指标
   - 责任：支持模型运营、A/B 与路由决策

---

## 2. 分阶段实施路线图

# Phase 0 — 基线冻结与保护（P0）

### Objective
为后续改造建立“不可回退”的双模型基线，避免架构演进破坏现有主链。

### Files
- Modify: `tests/test_image_prompt_renderers.py`
- Modify: `tests/test_gpt_image2_reference_input.py`
- Modify: `tests/test_gpt_image2_primary_defaults.py`
- Modify: `tests/test_gpt_image2_aux_scripts.py`
- Modify: `tests/test_nanobanana_provider_routing.py`
- Create: `tests/test_image_model_policy_contract.py`

### Deliverables
1. 固化当前 gpt-image-2 / nanobanana-2 prompt 差异事实
2. 固化当前 adapter routing 合约
3. 增加一份“策略接口 contract”测试占位，作为后续 refactor 的保护网

### Verification
Run:
```bash
./middleware/.venv/bin/pytest \
  tests/test_image_prompt_renderers.py \
  tests/test_gpt_image2_reference_input.py \
  tests/test_gpt_image2_primary_defaults.py \
  tests/test_gpt_image2_aux_scripts.py \
  tests/test_nanobanana_provider_routing.py \
  tests/test_image_model_policy_contract.py -q
```
Expected:
- 全部通过
- 即使后续改 Prompt Policy 内部实现，外部行为保持一致

### Exit Criteria
- 当前双模型行为有明确测试护栏
- 可以进入 Phase 1 而不担心主链无感漂移

---

# Phase 1 — Prompt Policy 层落地（P1）

### Objective
把“模型专属 prompt 逻辑”从 handler 中抽离成最小可用策略层，但不改主流程。

### Files
- Create: `middleware/prompt_policies/__init__.py`
- Create: `middleware/prompt_policies/base.py`
- Create: `middleware/prompt_policies/reference_first.py`
- Create: `middleware/prompt_policies/identity_first.py`
- Create: `middleware/prompt_policies/factory.py`
- Modify: `middleware/handlers/content_generation.py`
- Create: `tests/test_prompt_policy_factory.py`
- Create: `tests/test_reference_first_policy.py`
- Create: `tests/test_identity_first_policy.py`

### Design
定义最小接口：
```python
class ImagePromptPolicy(Protocol):
    def build_master_prompt(...): ...
    def build_sub_prompts(...): ...
```

第一版只提供两类 policy：
- `ReferenceFirstPolicy`
  - 绑定 `gpt-image-2`
  - 强调参考图保真、商品主体唯一、输出封面级单图
- `IdentityFirstPolicy`
  - 绑定 `nanobanana-2`
  - 强调人物锁定、组图一致性、文本约束补足

### content_generation.py 改法
当前：
- `_build_model_aware_image_master_prompt()`
- `_build_image_sub_prompts()`

目标：
- `_build_model_aware_image_master_prompt()` 可保留作为兼容 façade
- 新增 `_build_model_aware_image_sub_prompts()`
- handler 内部改成通过 `policy = get_image_prompt_policy(image_model_name, capability_cfg)` 统一取 master + sub

### Constraints
- 不大改 `_fill_prompts()` 主循环
- 不动飞书表结构
- 不重写 creative brief 生成逻辑

### Verification
Run:
```bash
./middleware/.venv/bin/pytest \
  tests/test_prompt_policy_factory.py \
  tests/test_reference_first_policy.py \
  tests/test_identity_first_policy.py \
  tests/test_image_prompt_renderers.py -q
```

Online spot checks:
- 用已有历史 plan 做 handler 级 dry replay，确认 `image_prompts` 仍能正常写入 debug

### Exit Criteria
- sub prompt 正式支持模型分流
- prompt 结构演进为：shared brief + model policy(master+sub)
- handler 里不再硬编码“master 分流、sub 共享”

---

# Phase 2 — Model Capability Registry（P2）

### Objective
把模型选择依据从“模型名 if/else”升级为“能力画像 + policy 绑定”。

### Files
- Modify: `middleware/config/model_params.yaml`
- Create: `middleware/core/model_capabilities.py`
- Create: `tests/test_model_capabilities.py`
- Modify: `middleware/prompt_policies/factory.py`
- Modify: `middleware/adapters/ai_models.py`

### Design
在 `model_params.yaml` 的 image model provider 下补充结构化字段，例如：
```yaml
prompt_policy: reference_first
capabilities:
  reference_image: true
  strong_product_fidelity: true
  strong_identity_consistency: false
  preferred_use_cases:
    - ecommerce_cover
    - product_fidelity
```

`model_capabilities.py` 提供：
- 读取能力画像
- 缺省字段补齐
- 供 policy factory / routing 使用

### Rules
- `gpt-image-2` → `reference_first`
- `nanobanana-2` → `identity_first`
- 新模型优先通过配置绑定 policy，不允许直接再往 handler 里加模型名分支

### Verification
Run:
```bash
./middleware/.venv/bin/pytest \
  tests/test_model_capabilities.py \
  tests/test_prompt_policy_factory.py \
  tests/test_nanobanana_provider_routing.py -q
```

### Exit Criteria
- 模型特征由配置声明
- policy factory 根据能力/配置选择策略
- 新模型接入路径初步标准化

---

# Phase 3 — Adapter Contract 标准化（P2/P3 之间）

### Objective
统一 adapter 的执行参数接口，减少未来把模型差异继续堆进 prompt 文本。

### Files
- Modify: `middleware/adapters/ai_models.py`
- Create: `tests/test_image_adapter_contract.py`

### Design
统一接口到：
```python
generate(prompt: str, ref_images: list[bytes] | None = None, execution_hints: dict | None = None) -> bytes
```

第一批 hints 可先只读不强用：
- `aspect_ratio`
- `quality_mode`
- `product_priority`
- `consistency_mode`

### Constraints
- 兼容旧调用形式
- 不要求所有 adapter 一次性吃完所有 hints

### Verification
- contract tests 覆盖 OpenAIImageAdapter / ImageModelAdapter / XiaoleImageAdapter
- 确认无 hints 时行为与当前完全一致

### Exit Criteria
- adapter 接口对未来多模型/多执行参数有扩展位
- 不必继续把所有控制都塞进 prompt 文本

---

# Phase 4 — Routing Layer（P3）

### Objective
建立“按业务场景推荐模型”的最小路由层，而不是让所有计划都人工硬选。

### Files
- Create: `middleware/core/image_model_routing.py`
- Create: `tests/test_image_model_routing.py`
- Modify: `admin-server/schemas/__init__.py`
- Modify: `middleware/handlers/content_generation.py`
- Optional Modify: `admin-server/routers/plans.py`

### Input Signals
- 是否有白底图参考
- 是否强商品保真
- 是否有人物主导场景
- 是否多图一致性强需求
- content_type / category / platform

### Suggested Output
```python
{
  "recommended_model": "gpt-image-2",
  "recommended_policy": "reference_first",
  "reason_codes": ["has_reference_image", "product_fidelity_priority"]
}
```

### Rollout Strategy
- 第 1 阶段只做 recommendation，不自动覆盖用户显式传入模型
- 后续再考虑 auto-select

### Verification
- 单测覆盖典型 SKU / scene 组合
- 确认默认值仍保持 `gpt-image-2`

### Exit Criteria
- 模型选择具备可解释的推荐能力
- 为未来更多模型接入提供统一入口

---

# Phase 5 — Evaluation Layer（P4）

### Objective
建立标准化评估指标，为多模型经营和 A/B 提供闭环。

### Files
- Create: `middleware/core/image_eval_schema.py`
- Create: `middleware/scripts/score_image_runs.py`
- Create: `tests/test_image_eval_schema.py`
- Optional Modify: `workspace/content-store/...` debug writer usage in `content_generation.py`
- Optional Create: `docs/reviews/` per-run report templates

### Metrics
#### Single-image
- product_fidelity
- subject_clarity
- scene_match
- cover_readiness

#### Group-level
- intra_group_diversity
- identity_consistency
- product_consistency
- shot_repetition_rate

#### Engineering
- success_rate
- average_latency
- retry_count
- average_bytes

### Initial Implementation
第一版不强求自动视觉打分，可先做：
- schema 定义
- 人工/半自动录入通道
- regression run report 标准模板

### Verification
- 评分 schema 单测通过
- 至少能对 `T_260510_119` 这类回归案例形成结构化记录

### Exit Criteria
- 系统开始具备“模型经营”能力，而不只是“模型接入”能力

---

# Phase 6 — Multi-Model Onboarding Standard（P4+）

### Objective
为未来接更多模型建立固定接入清单，避免每次重复发明流程。

### Files
- Create: `docs/plans/model-onboarding-checklist.md`
- Create: `tests/fixtures/model_capability_samples.yaml`
- Optional Create: `middleware/prompt_policies/scene_first.py`

### Standard Checklist
1. 在 `model_params.yaml` 注册 provider 参数
2. 填 capability 画像
3. 绑定现有 policy 或声明新增 policy
4. 跑 adapter contract tests
5. 跑 prompt policy regression tests
6. 跑 1 组在线回归
7. 产出 evidence report
8. 决定是否进入推荐路由池

### Exit Criteria
- 新模型接入路径变成标准 SOP
- 工程成本和回归成本显著下降

---

## 3. 推荐文件级改造顺序（最小爆炸半径）

### Wave 1
- `tests/test_image_model_policy_contract.py`
- `middleware/prompt_policies/*`
- `tests/test_prompt_policy_factory.py`
- `tests/test_reference_first_policy.py`
- `tests/test_identity_first_policy.py`

### Wave 2
- `middleware/handlers/content_generation.py`
- `middleware/core/model_capabilities.py`
- `middleware/config/model_params.yaml`

### Wave 3
- `middleware/adapters/ai_models.py`
- `tests/test_image_adapter_contract.py`

### Wave 4
- `middleware/core/image_model_routing.py`
- `tests/test_image_model_routing.py`

### Wave 5
- `middleware/core/image_eval_schema.py`
- `middleware/scripts/score_image_runs.py`

---

## 4. 每阶段的回归要求

### Mandatory local tests
```bash
./middleware/.venv/bin/pytest tests/test_*image* -q
```

### Mandatory focused tests
```bash
./middleware/.venv/bin/pytest \
  tests/test_image_prompt_renderers.py \
  tests/test_gpt_image2_reference_input.py \
  tests/test_gpt_image2_primary_defaults.py \
  tests/test_gpt_image2_aux_scripts.py \
  tests/test_nanobanana_provider_routing.py -q
```

### Mandatory online evidence after Phase 1 or major prompt changes
- 至少跑 1 次 gpt-image-2 在线闭环回归
- 记录：plan status / content status / image count / content.json.debug.image_prompts / 失败信息
- 若 nanobanana provider 恢复可用，再补 1 次同规格回归

---

## 5. ADR-style 决策结论

### Decision A
`gpt-image-2` 继续作为默认主力生产模型，直到有新的在线证据证明其他模型在“商品保真 + 稳定性 + 成本”综合上更优。

### Decision B
Prompt 体系从“模型名硬编码分流”演进为“policy + capability 驱动”，但必须通过最小变更逐步实施。

### Decision C
Creative brief 保持共享，不为每个模型单独复制上游业务语义层。

### Decision D
Adapter 负责协议差异，Prompt Policy 负责语义适配，两者边界必须保持清晰。

### Decision E
未来新模型接入必须先满足 contract tests + prompt regression + online evidence 三件套，不能直接进生产默认路径。

---

## 6. 风险与控制

### Risk 1: 抽象过度
**表现：** 过早做复杂框架，影响当前主链稳定。
**控制：** 先只落地两种 policy，不先做通用 DSL。

### Risk 2: 共享 sub prompt 遗留时间过长
**表现：** 新模型接入继续复制 nanobanana 风格约束。
**控制：** Phase 1 把 sub prompt 分流作为最高优先级。

### Risk 3: provider 不稳定掩盖架构效果
**表现：** nanobanana provider 不通导致 prompt 调整无法真实评估。
**控制：** 将 provider 问题与 prompt policy 问题分离，先完成架构侧可验证改造。

### Risk 4: 评估层缺失导致多模型运营失真
**表现：** 模型选择长期靠主观经验。
**控制：** 即使先人工评分，也要尽快建立统一 schema。

---

## 7. 建议的执行顺序

1. **先做 Phase 0**：补 contract 测试护栏
2. **再做 Phase 1**：拆出 prompt policy，尤其是 sub prompt 分流
3. **再做 Phase 2**：模型 capability 注册
4. **再做 Phase 3**：adapter contract 标准化
5. **再做 Phase 4**：推荐路由
6. **最后做 Phase 5/6**：评估闭环 + 新模型接入标准

---

## 8. 完成定义（Definition of Done）

当以下条件同时成立时，可认为系统已从双模型专项实现升级到多模型可扩展框架：

- gpt-image-2 主链保持稳定默认生产可用
- nanobanana-2 或其他第二模型可通过独立 policy 运行
- master/sub prompt 都已按 policy 分流
- capability registry 可声明新模型特征
- 新模型接入不再要求修改 handler 主体分支
- evaluation schema 可沉淀对比证据
- 至少 1 个新模型可按 onboarding checklist 接入到非默认路径

---

## 9. 执行建议

建议下一步直接从 **Phase 0 + Phase 1** 开始实施，因为这是：
- 爆炸半径最小
- 对当前双模型收益最大
- 对未来多模型扩展最关键的基础设施

优先实现项：
1. `tests/test_image_model_policy_contract.py`
2. `middleware/prompt_policies/` 目录
3. `_build_model_aware_image_sub_prompts()`
4. `tests/test_prompt_policy_factory.py`
5. `tests/test_reference_first_policy.py`
6. `tests/test_identity_first_policy.py`
