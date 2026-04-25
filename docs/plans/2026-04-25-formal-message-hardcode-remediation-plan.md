# Formal Message Hardcode Remediation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** 去掉 formal message 模板体系中对“回报格式 / 禁止项”等业务口径的硬编码默认值，改为“结构模板 + 显式传参/策略生成 + 校验兜底”的可维护架构。

**Architecture:** 保留现有 wrapper → interactive sender → renderer → verified mention 的发送链路，不重做消息系统；本次只重构“字段来源与校验规则”。核心改动是：模板不再内置业务话术默认值，wrapper/renderer 增加显式字段校验，并引入可选的策略层为不同消息类型生成动态 `actions[] / guardrails[]`。短期先实现“无硬编码默认值 + 必填校验”，中期再收敛到统一数组字段模型。

**Tech Stack:** Python 3.11、JSON templates、Feishu interactive card wrapper、现有 docs/plans 文档体系。

**Status Update (2026-04-25):**
- Phase A 已完成：模板业务默认值清理、缺失阻断、示例补齐、自检与 strict smoke 已通过。
- Phase B 进行中：`dispatch / risk / arbitration` 主路径已迁到 `business_sections + actions[] / guardrails[]`，renderer / wrapper 已支持数组输入，并对旧字段 `report_item_* / action_item_* / guardrail_*` 保留兼容告警。
- 当前剩余：补 schema / cheatsheet / quick commands 等文档收口，并整理仅包含本次相关文件的干净 commit。

---

## 一、当前问题与证据

### 1. 模板默认值硬编码
已确认以下模板直接在 `default_values` 中写死业务文案：

- `middleware/templates/feishu_interactive_02_dispatch.json`
- `middleware/templates/feishu_interactive_02_dispatch_compact.json`
- `middleware/templates/feishu_interactive_02_dispatch_compact_divider.json`
- `middleware/templates/feishu_interactive_02_dispatch_rich.json`
- `middleware/templates/feishu_interactive_05_risk.json`
- `middleware/templates/feishu_interactive_09_arbitration.json`

其中最关键的是 `02 dispatch*`：
- `report_item_1..4 = 已完成 / 当前阻塞 / 需协同项 / 下一步`
- `guardrail_1..3 = 不要跳过字段口径直接进入实现 / 不要把未确认项写成既定结论 / 不要多主责并行汇报`

### 2. 渲染器会自动吞默认值
`middleware/scripts/render_interactive_card.py`
- `build_mapping()` 先合并 `template_payload.default_values`
- 再合并传入 `data`

结果是：即使调用方不传 `report_item_* / guardrail_*`，也会自动落回模板默认话术。

### 3. wrapper 没有强制这些字段显式提供
`middleware/scripts/feishu_formal_message.py`
- 当前只对 annex / 角色占位做 hint 与 strict block
- 没有对 `actions/guardrails` 或旧的 `report_item_/guardrail_` 做“缺失即阻断”
- risk / arbitration 的 `action_item_*` 也属于业务区块，若继续留在默认值里，同样会产生“看似显式、实则模板回落”的假象

### 4. 文档已经与目标架构部分错位
已有文档已开始朝数组结构靠拢：
- `docs/plans/2026-04-24-feishu-interactive-card-field-mapping.md`
  - 已定义 `actions[]`
  - 已定义 `guardrails[]`

但模板和代码仍在使用 `report_item_* / guardrail_*` 的半旧模型，存在“文档先进、模板落后”的分裂。

### 5. probe / style 脚本也有演示性硬编码
- `middleware/scripts/feishu_interactive_card_probe.py`
- `middleware/scripts/feishu_post_style_probe.py`

这些脚本中的固定文案不会直接污染正式模板主链路，但会继续制造“默认业务口径”的错觉，后续也应统一清理。

---

## 二、修复目标（最终状态）

### 必须达到
1. 正式模板不再把业务口径写死在 `default_values`。
2. `回报格式 / 禁止项` 的内容来源必须是：
   - 调用方显式传参，或
   - 明确可追踪的策略生成器。
3. 若消息类型要求这些区块存在，但调用方未提供，也没有策略层生成，则 wrapper/renderer 必须报错，而不是静默落默认值。
4. 文档、模板、wrapper、自检/strict smoke、样例数据口径一致。

### 最好同时达到
5. 字段模型统一为数组：
   - `actions[]`
   - `guardrails[]`
6. 模板隐藏空区块，而不是渲染空占位或 `-`。
7. 自检输出中明确说明：哪些字段由调用方提供，哪些字段由策略层补全。

---

## 三、建议修复策略

## 方案总览
采用“两阶段修复 + 一次兼容收口”：

### Phase A：止血修复（先消灭硬编码生效）
目标：先阻断“未传参也能发出去”的错误默认行为。

动作：
1. 删除正式模板中的 `report_item_* / guardrail_*` 默认值；对 risk / arbitration 同步删除 `action_item_*` 默认值。
2. 将这些字段加入必填校验。
3. wrapper self-check / strict-hints 新增“业务区块缺失”校验。
4. 所有正式示例数据补齐对应字段。

优点：
- 见效快
- 风险小
- 不需要重写所有模板结构

代价：
- 仍保留旧字段命名（`report_item_*`），只是从“默认值”改成“必传值”

### Phase B：结构升级（统一到数组字段模型）
目标：把旧的 `report_item_1..4 / guardrail_1..3` 升级为文档口径一致的 `actions[] / guardrails[]`。

动作：
1. 更新模板 schema 与渲染器映射规则。
2. wrapper 接受数组输入，并负责映射/校验。
3. 模板 index、field mapping、cheatsheet、quick commands 全部切到数组模型。
4. 保留一个短期兼容层：允许旧字段输入，但发 warning，并在后续版本移除。

优点：
- 长期最干净
- 与文档一致
- 易扩展，不再受限于固定 4 项/3 项

代价：
- 影响模板、样例、渲染器、wrapper、自检脚本
- 需要更完整回归

### 推荐决策
**推荐按 Phase A → Phase B 顺序执行。**
不要一次性“大爆改”。先止血，再统一模型。

---

## 四、影响范围

### 代码
- `middleware/scripts/render_interactive_card.py`
- `middleware/scripts/send_formal_interactive_card.py`
- `middleware/scripts/feishu_formal_message.py`
- `middleware/scripts/feishu_formal_message_strict_smoke.py`（需检查并补回归）
- `middleware/scripts/feishu_interactive_card_probe.py`
- `middleware/scripts/feishu_post_style_probe.py`

### 模板
重点：
- `middleware/templates/feishu_interactive_02_dispatch.json`
- `middleware/templates/feishu_interactive_02_dispatch_compact.json`
- `middleware/templates/feishu_interactive_02_dispatch_compact_divider.json`
- `middleware/templates/feishu_interactive_02_dispatch_rich.json`
- `middleware/templates/feishu_interactive_05_risk.json`
- `middleware/templates/feishu_interactive_09_arbitration.json`

连带检查：
- 所有 `feishu_interactive_*.json`
- 所有 `feishu_interactive_render_example_*.json`
- probe 模板

### 文档
- `docs/plans/2026-04-24-feishu-interactive-card-field-mapping.md`
- `docs/plans/2026-04-24-interactive-card-template-index.md`
- `docs/plans/2026-04-24-formal-message-cheatsheet.md`
- `docs/plans/2026-04-24-formal-message-quick-commands.md`
- `docs/plans/2026-04-24-formal-message-wrapper-v2.md`
- `docs/plans/2026-04-24-formal-message-template-governance.md`
- 相关 skills（至少 feishu / governance / SOP 类）

---

## 五、实施任务拆解

### Task 1：建立“硬编码清单”并冻结改动范围
**Objective:** 输出完整受影响文件表，避免边修边漏。

**Files:**
- Create: `docs/plans/2026-04-25-formal-message-hardcode-remediation-plan.md`
- Inspect: `middleware/templates/*.json`
- Inspect: `middleware/scripts/*.py`
- Inspect: `docs/plans/*.md`

**Steps:**
1. 列出所有包含 `report_item_` / `guardrail_` / 固定业务文案的模板与脚本。
2. 区分：正式模板 / probe 模板 / 示例数据 / 文档。
3. 形成一份“必须改 / 可延后改”的清单。

**Verification:**
- 至少确认 3 类对象：模板、脚本、文档。
- 清单能覆盖 dispatch / risk / arbitration 主路径。

---

### Task 2：Phase A 模板止血
**Objective:** 去掉正式模板里的业务默认值。

**Files:**
- Modify: `middleware/templates/feishu_interactive_02_dispatch.json`
- Modify: `middleware/templates/feishu_interactive_02_dispatch_compact.json`
- Modify: `middleware/templates/feishu_interactive_02_dispatch_compact_divider.json`
- Modify: `middleware/templates/feishu_interactive_02_dispatch_rich.json`
- Modify: `middleware/templates/feishu_interactive_05_risk.json`
- Modify: `middleware/templates/feishu_interactive_09_arbitration.json`

**Steps:**
1. 删除 `default_values` 中的 `report_item_*`。
2. 删除 `default_values` 中的 `guardrail_*`。
3. 把缺失后仍必须存在的字段加入 `required_placeholders`。
4. 对 rich 模板仅保留 truly structural defaults（如 annex_title 这类 UI 层默认值），不保留业务判断文案。

**Verification:**
- 模板文本中仍保留占位符，但 `default_values` 不再出现业务固定文案。
- `read_file` 检查不再有“已完成/当前阻塞/不要…”这类默认值藏在 `default_values` 中。

---

### Task 3：renderer 加强校验
**Objective:** 防止模板缺字段时静默回落。

**Files:**
- Modify: `middleware/scripts/render_interactive_card.py`
- Test/verify via command line

**Steps:**
1. 在 `build_mapping()` 之前或之后区分：
   - structural defaults
   - runtime-required fields
2. 对属于业务区块的字段，缺失时直接报错，不允许通过默认值补齐。
3. 为后续 Phase B 预留兼容入口：
   - 若传 `actions[]/guardrails[]`，可先转换成旧占位符；
   - 若传旧字段，暂时兼容。

**Verification commands:**
- 渲染 dispatch 模板但不传回报格式/禁止项 → 预期 FAIL
- 补齐字段后再渲染 → 预期 PASS

---

### Task 4：wrapper 增加“业务区块缺失”自检与阻断
**Objective:** 让错误在发送前暴露，而不是到群里才发现。

**Files:**
- Modify: `middleware/scripts/feishu_formal_message.py`
- Possibly modify: `middleware/scripts/send_formal_interactive_card.py`

**Steps:**
1. 在 `build_smart_hints()` 中加入新规则：
   - dispatch 若缺少回报格式/禁止项 → warning + violation
   - risk / arbitration 若缺 guardrails → warning + violation
2. `--strict-hints` 下，这些 violation 必须 exit 2。
3. `--self-check` 输出中新增字段来源说明：
   - user_provided
   - strategy_generated
   - missing

**Verification:**
- `--self-check` 能看出缺失字段
- `--strict-hints` 在关键缺失时能阻断

---

### Task 5：补齐并规范所有正式样例数据
**Objective:** 让所有 quick commands / demo / smoke 都按新规则可运行。

**Files:**
- Modify: all `middleware/templates/feishu_interactive_render_example_*.json`
- Modify: any probe data json using old assumptions

**Steps:**
1. 为 dispatch 示例显式补齐回报格式与禁止项。
2. 为 risk / arbitration 示例显式补齐 guardrails。
3. 若进入 Phase B，则统一改为 `actions[] / guardrails[]`。
4. 保证示例数据表达“任务相关口径”，不要再复用完全相同的万能文案。

**Verification:**
- cheatsheet 中每条命令都能在 self-check 模式通过。

---

### Task 6：统一字段模型到 `actions[] / guardrails[]`（Phase B）
**Objective:** 消灭旧的固定序号字段模型。

**Files:**
- Modify: `middleware/templates/feishu_interactive_formal_message_schema.json`
- Modify: `middleware/scripts/render_interactive_card.py`
- Modify: `middleware/scripts/feishu_formal_message.py`
- Modify: relevant templates

**Steps:**
1. schema 以数组字段为主，不再鼓励 `report_item_1..4`。
2. renderer 支持：
   - `actions[] -> action section`
   - `guardrails[] -> guardrail section`
3. 模板改成数组渲染策略：
   - 若当前模板体系无法原生循环，可在 wrapper 预展开成 `action_lines_markdown` / `guardrail_lines_markdown`
4. 保留旧字段 1 个过渡版本，并打印 deprecated warning。

**Verification:**
- 新数组模型可渲染 dispatch / risk / arbitration
- 旧字段输入仍可短期工作，但有告警

---

### Task 7：probe / style script 去业务硬编码
**Objective:** 不让辅助脚本继续输出错误示范。

**Files:**
- Modify: `middleware/scripts/feishu_interactive_card_probe.py`
- Modify: `middleware/scripts/feishu_post_style_probe.py`

**Steps:**
1. 把写死文案替换为参数化输入或明确标注“示例探针，不代表正式默认口径”。
2. probe 默认使用测试专用字段，而不是伪装成正式业务默认值。

**Verification:**
- probe 运行结果不再暗示系统自带固定回报格式/禁止项。

---

### Task 8：文档与技能同步
**Objective:** 保证“代码改了，规则也改了，手册也改了”。

**Files:**
- Modify: `docs/plans/2026-04-24-feishu-interactive-card-field-mapping.md`
- Modify: `docs/plans/2026-04-24-interactive-card-template-index.md`
- Modify: `docs/plans/2026-04-24-formal-message-cheatsheet.md`
- Modify: `docs/plans/2026-04-24-formal-message-quick-commands.md`
- Modify: `docs/plans/2026-04-24-formal-message-wrapper-v2.md`
- Modify: `docs/plans/2026-04-24-formal-message-template-governance.md`
- Patch related skills after implementation

**Steps:**
1. 文档中明确：`title_prefix` 可默认，业务口径不可默认。
2. 文档命令示例全部补齐 actions/guardrails 传参。
3. 把字段说明统一改成数组模型。
4. 如 skill 内容仍写旧字段，补 patch。

**Verification:**
- 文档、模板、wrapper 参数名一致。
- 不再出现“report_item_1..4 是推荐最终模型”的表述。

---

### Task 9：回归与 live smoke
**Objective:** 验证改动没有破坏正式链路。

**Files:**
- Validate existing smoke scripts
- Possibly add: `middleware/scripts/feishu_formal_message_data_contract_smoke.py`

**Steps:**
1. 跑 renderer 本地渲染回归。
2. 跑 wrapper `--self-check`。
3. 跑 `--strict-hints` 失败用例与成功用例。
4. 对至少 3 类正式消息做 dry-run：dispatch / risk / conclusion。
5. 必要时在测试群 live smoke 1 条 dispatch + 1 条 risk。

**Verification matrix:**
- 缺字段时：必须 fail
- 显式传字段时：必须 pass
- mention/receipt：不得回退
- smart_hints：能解释字段缺失或字段来源

---

## 六、关键设计决策

### 决策 1：哪些默认值可以保留？
**可以保留：**
- 纯结构/UI 默认值
  - `closer_mentions = Hermes_CEO`（如果这是组织级约定，且不是业务判断）
  - `annex_title = 详细执行附录`
  - header 颜色、receipt 固定文案

**不应保留：**
- 业务判断/执行口径
  - `已完成 / 当前阻塞 / 需协同项 / 下一步`
  - `不要跳过字段口径直接进入实现`
  - 任意与具体任务、具体流程、具体约束相关的话术

### 决策 2：兼容期要不要支持旧字段？
建议：**支持一个过渡版本，但必须告警。**

原因：
- 当前已有模板、脚本、示例、可能还有人工习惯依赖旧字段。
- 一刀切会增加回归风险。

建议规则：
- v1：支持旧字段 + warning
- v2：文档完全切新字段
- v3：移除旧字段

### 决策 3：策略生成器是否本轮必须做？
建议：
- **本轮先做接口与占位，不强求一步到位。**
- 先完成“显式传参 + 缺失阻断”。
- 策略生成器可作为下一步增强项：
  - `dispatch` 根据任务类型生成默认 `actions[]`
  - `risk` 根据风险级别生成 `guardrails[]`

---

## 七、验收标准

### 功能验收
- [ ] 正式模板 `default_values` 中不再出现业务固定口径
- [ ] 缺少业务区块字段时，wrapper/renderer 会报错
- [ ] dispatch / risk / arbitration 至少 3 类消息可用新规则发送
- [ ] 旧字段若暂时兼容，系统会给 deprecated warning

### 文档验收
- [ ] cheatsheet 与 quick commands 采用新字段模型
- [ ] field mapping 与模板真实实现一致
- [ ] governance 文档明确“业务口径不可硬编码”

### 发送链路验收
- [ ] mention_verified 不受影响
- [ ] receipt 结构不受影响
- [ ] strict-hints 可以拦截缺失业务字段

---

## 八、推荐实施顺序

1. Task 1 清单冻结
2. Task 2 模板止血
3. Task 3 renderer 校验
4. Task 4 wrapper 校验
5. Task 5 样例数据补齐
6. Task 9 做一轮回归
7. Task 6 进入数组模型升级
8. Task 7/8 清理 probe 与文档
9. 再做一次 smoke + live 验收

---

## 九、我给 Kenny 的最终建议

**建议立刻执行 Phase A。**
原因很简单：
- 这是实际错误来源
- 不改的话，群里会继续发出“看似正式、实则默认硬编码”的消息
- 风险不在 UI，而在治理口径失真

**Phase B 紧跟，但可以单开一次小迭代。**
这样能把风险控制住，同时不给当前正式发送链路造成一次性大爆改。

---

## 十、执行后提醒

这是一个重要节点，建议修复完成后及时提交：

```bash
cd /Users/carson/workspace/ai-content-hub
git add -A
git commit -m "fix: remove hardcoded formal message action and guardrail defaults"
git push origin main
```
