# 9 类正式消息字段映射表（interactive card）

## 使用原则
- 主标题统一模板：`{title_prefix}｜{code} {label}`
- 副标题统一模板：`{doc_type} · {task_name_or_phase}`
- 一张卡片只承载一个正式动作
- owner 始终唯一
- receipt 始终保留
- `actions[] / guardrails[]` 是正式推荐模型；`report_item_* / action_item_* / guardrail_*` 仅作为过渡兼容输入，不再推荐新增使用

## 一、通用基础字段

| 字段 | 含义 | 是否必填 | 示例 | 说明 |
|---|---|---:|---|---|
| `title_prefix` | 卡片项目前缀/业务线前缀 | 是 | `AI-CONTENT-HUB` | 可配置，不写死 |
| `code` | 两位数消息编号 | 是 | `02` | `01~09` |
| `label` | 消息类型名称 | 是 | `派单` | 与 code 一一对应 |
| `doc_type` | 文档/消息副标题类型 | 是 | `执行单` | 如执行单/阶段结论/风险通报 |
| `task_name` | 任务名 | 是 | `四表治理与 Prompt 提升` | 可用于副标题或正文 |
| `status` | 当前状态 | 否 | `已进入字段锁定阶段` | 放时间/状态段 |
| `summary` | 当前摘要 | 否 | `先锁字段，再接技术与内容流程` | 可用于 01/08/09 |
| `owner` | 主责人 mention | 是 | `@大T_技术总工` | 单主责 |
| `collaborators` | 协作人 mentions | 否 | `@大C_内容总监` | 可多个 |
| `closers` | 收口抄送 mentions | 否 | `@Hermes_CEO` | 建议保留 |
| `decision_maker` | 需拍板人 mention | 否 | `@Hermes_CEO` | 风险/仲裁更常用 |
| `next_owner` | 下一责任人 mention | 否 | `@大C_内容总监` | 交接时常用 |
| `goal` | 动作目标 | 否 | `今日先产出基础可执行版` | 派单/催办常用 |
| `deadline` | 总截止时间 | 否 | `今天 17:30 前` | 可映射到 timing |
| `progress_deadline` | 进展回报时点 | 否 | `12:00 前回【04 进展】` | 派单/接单/催办常用 |
| `delivery_deadline` | 交付回报时点 | 否 | `17:30 前回【07 交付】` | 派单/进展常用 |
| `next_milestone` | 下一节点 | 否 | `等待技术接线确认` | timing 段常用 |
| `deliverables[]` | 交付项列表 | 否 | `字段草案/版本规则/接线建议` | 一般 2~4 条 |
| `judgements[]` | 判断/结论列表 | 否 | `当前先锁字段，不先做自动化` | 结论/仲裁常用 |
| `risks[]` | 风险点列表 | 否 | `字段口径未统一` | 风险卡主字段 |
| `impacts[]` | 影响范围列表 | 否 | `任务延期/责任不清` | 风险/仲裁常用 |
| `actions[]` | 回报或动作项列表 | 否 | `已完成/阻塞/下一步` | 各类型都会用 |
| `guardrails[]` | 边界/禁止项列表 | 否 | `不要多主责并行` | 派单/风险/仲裁更常用 |
| `receipt_text` | receipt 文案 | 是 | `receipt｜以回读与 mention 验证为准` | 固定口径 |

---

## 二、9 类消息字段映射

| code | label | doc_type 建议 | header 颜色 | 必备角色 | core 段主字段 | timing 段主字段 | action 段主字段 | guardrails |
|---|---|---|---|---|---|---|---|---|
| `01` | 受理 | `受理单` / `受理确认` | `blue` | `owner` / `next_owner` | `judgements[]` | `status` / `next_milestone` | `actions[]` | 可选 |
| `02` | 派单 | `执行单` | `blue` | `owner` / `collaborators` / `closers` | `deliverables[]` | `progress_deadline` / `delivery_deadline` / `status` | `actions[]` | 必填推荐 |
| `03` | 接单 | `接单确认` | `turquoise` | `owner` | `judgements[]` / `deliverables[]` | `progress_deadline` / `status` | `actions[]` | 可选 |
| `04` | 进展 | `阶段进展` | `indigo` | `owner` | `deliverables[]` / `judgements[]` | `status` / `deadline` / `next_milestone` | `actions[]` | 弱化 |
| `05` | 风险 | `风险通报` | `red` | `owner` / `decision_maker` | `risks[]` / `impacts[]` | `deadline` / `status` | `actions[]` | 建议保留 |
| `06` | 催办 | `催办单` | `orange` | `owner` / `next_owner` | `deliverables[]` / `judgements[]` | `deadline` / `progress_deadline` | `actions[]` | 可选 |
| `07` | 交付 | `交付单` | `green` | `owner` / `next_owner` / `closers` | `deliverables[]` | `status` / `next_milestone` | `actions[]` | 可选 |
| `08` | 结论 | `阶段结论` | `green` | `owner` / `closers` | `judgements[]` | `status` / `next_milestone` | `actions[]` | 可选 |
| `09` | 仲裁 | `仲裁单` | `purple` | `owner` / `decision_maker` / `next_owner` | `judgements[]` / `impacts[]` | `deadline` / `status` | `actions[]` | 建议保留 |

---

## 三、02 派单推荐字段实例

| 区块 | 字段 | 示例 |
|---|---|---|
| header.title | `title_prefix + code + label` | `AI-CONTENT-HUB｜02 派单` |
| header.subtitle | `doc_type + task_name` | `执行单 · 四表治理与 Prompt 提升` |
| overview | `task_name` | `四表治理与 Prompt 提升` |
| overview | `owner` | `@大T_技术总工` |
| overview | `collaborators` | `@大C_内容总监` |
| overview | `closers` | `@Hermes_CEO` |
| overview | `goal` | `今日先产出基础可执行版` |
| core | `deliverables[0..2]` | `四张表字段关系草案 / Prompt 资产结构 / 技术接线建议` |
| timing | `progress_deadline` | `12:00 前回【04 进展】` |
| timing | `delivery_deadline` | `17:30 前回【07 交付】` |
| timing | `status` | `已启动，等待主责拆解` |
| timing | `next_milestone` | `先完成字段和口径锁定` |
| action | `actions[]` | `已完成 / 当前阻塞 / 需协同项 / 下一步` |
| guardrails | `guardrails[]` | `不要跳过字段口径直接进入实现` |
| receipt | `receipt_text` | `receipt｜以回读与 mention 验证为准` |

---

## 四、推荐渲染规则

### header 渲染
- `header.title = {title_prefix} + '｜' + {code} + ' ' + {label}`
- `header.subtitle = {doc_type} + ' · ' + {task_name_or_phase}`
- `header.template` 按消息类型固定映射

### body 渲染
- `overview.lines`：角色、目标、任务名
- `core.lines`：`deliverables[] / judgements[] / risks[] / impacts[]`
- `timing.lines`：`status / deadline / progress_deadline / delivery_deadline / next_milestone`
- `action.lines`：`actions[]`
- `guardrails.lines`：`guardrails[]`
- 当前实现中，模板通过 `business_sections` 声明业务区块，再由 renderer 预展开为 `actions_md / guardrails_md` markdown 段落

### receipt 渲染
- 永远单独放底部
- 不与 action 段合并

---

## 五、落地建议
1. 先实现 `02 派单` 与 `08 结论`
2. 把 9 类差异收敛到：`code / label / doc_type / color / core字段来源`
3. 渲染器只维护一套 body 结构，不为每类消息写 9 套完全不同模板
4. 若字段缺失，优先隐藏对应行，而不是渲染空占位符
