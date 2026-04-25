# Hermes 多 Agent 正式消息治理规范 v2（2026-04-24）

> 目的：将 Hermes 总裁办群内关于正式消息、真实 mention、sender 身份、回执、阶段收口、主责归属、冒烟测试的零散规则，统一收敛为一套长期有效、可执行、可验收的治理规范。

---

## 1. 适用范围

- 群：`Hermes 总裁办`
- `chat_id`: `oc_ea99db0c239b28740dc6571e89b9a808`
- 适用对象：`Hermes_CEO` / `大T_技术总工` / `大C_内容总监` / 后续新增 agent
- 适用正式消息类型：
  - `【受理】`
  - `【派单】`
  - `【接单】`
  - `【进展】`
  - `【风险】`
  - `【交付】`
  - `【催办】`
  - `【结论】`
  - `【仲裁】`（特殊纠偏消息）

---

## 2. 规范优先级

本规范自 2026-04-24 起，覆盖此前所有不完整、不一致或只停留在口头/临时提示层面的旧规则。

优先级如下：
1. **本规范**（正式消息治理总则）
2. `docs/plans/2026-04-24-formal-message-architecture-v3.md`
3. `docs/plans/2026-04-23-hermes-long-thread-observability-and-phase-closure.md`
4. `docs/plans/2026-04-24-hermes-group-collaboration-rules.md`
5. `docs/plans/2026-04-24-hermes-daily-message-style-guide.md`
6. `docs/plans/2026-04-24-hermes-collaboration-smoke-test.md`
7. `docs/plans/2026-04-22-hermes-feishu-group-mention-registry.md`
7. `middleware/config/feishu_mention_registry.json`
8. `middleware/scripts/feishu_formal_message.py/.sh`
9. `middleware/scripts/feishu_verified_mention_send.py`
11. 相关 skills / agent prompt / onboarding 文档

如旧规则与本规范冲突，以本规范为准。

补充：
- 9 类正式消息之外的日常沟通格式，统一遵循 `docs/plans/2026-04-24-hermes-daily-message-style-guide.md`
- 日常消息不得伪装成正式消息，也不得替代 formal wrapper 的正式职责

---

## 3. 正式消息成立条件

只有同时满足下列条件的消息，才算正式消息：

1. 通过 `feishu_formal_message.py` 或 `feishu_formal_message.sh` 发出
2. 底层委托到 `feishu_verified_mention_send.py`
3. 消息回读通过 mention 验证
4. 生成标准 `receipt`
5. `receipt.mention_verified = true`

**任何直接在聊天框手写的【受理 / 派单 / 接单 / 进展 / 风险 / 交付 / 催办 / 结论 / 仲裁】文本，都不算正式消息。**

---

## 4. 正式消息强制规则

### 4.1 唯一正式发送入口

正式消息只能通过以下入口发送：

```bash
python3.11 middleware/scripts/feishu_formal_message.py <label> <target> "<text>"
```

或：

```bash
middleware/scripts/feishu_formal_message.sh <label> <target> "<text>"
```

禁止：
- 直接在当前会话里手写 `<at ...>`
- 直接发纯文本 `@显示名`
- 不经 wrapper 直接把自然语言回复当正式回单

### 4.2 真实 mention 验收

正式消息必须同时满足：
- `body.content` 含 `@_user_N`
- `mentions[]` 非空
- `mentions[]` 命中目标对象
- `sender_type` 正确
- `sender.id` 正确

补充规则（v2）：
- registry 必须区分 `canonical_open_id` 与 `compatible_open_ids_by_sender`
- 验收时先按 sender 身份取允许命中的 `open_id` 集合
- `actual_mention_open_id ∈ allowed_open_ids_for_sender` 才算 mention 通过
- 若 `actual_mention_open_id != canonical_open_id`，receipt 必须标记 `compat_mode=true`

任一失败即不算正式完成。

### 4.3 回执强制要求

正式消息必须附 `receipt`。最少包含：
- `message_id`
- `mention_verified`
- `target_display_name`
- `target_open_id`
- `sender_id`
- `sender_type`

推荐补充字段：
- `canonical_open_id`
- `allowed_open_ids_for_sender`
- `actual_mention_open_id`
- `compat_mode`
- `required_targets`
- `next_owner_display_names`
- `next_owner_open_ids`
- `runtime_env_path`

无回执 = 无正式完成。

### 4.4 先发送、后说明

若 agent 需要在群内解释状态或交付内容，顺序必须是：
1. 先通过 wrapper 发送正式消息
2. 拿到 `receipt`
3. 再在当前会话中补充说明

禁止反过来：先解释、后补 formal message。

### 4.5 角色与 sender 身份一致

每个 agent 必须使用自己的 sender 身份：
- `Hermes_CEO` 只能以 CEO 对应身份发送
- `大T_技术总工` 只能以技术总工身份发送
- `大C_内容总监` 只能以内容总监身份发送
- 禁止切换为 Kenny user auth 冒充正式完成

---

## 5. 8+1 正式消息类型标准

### 5.1 标准定义

1. `【受理】`
   - 作用：正式接住需求 / 子任务，宣布进入协同流程
   - 使用者：默认 `Hermes_CEO`；若用户直接点名某 agent，或某子任务已明确归属某专业 owner，则该 owner 也可发
   - 不承载完整执行单内容

2. `【派单】`
   - 作用：当前 owner 正式下发执行单 / 协作单
   - 使用者：默认 `Hermes_CEO`；专业 owner 在其授权范围内也可向下游 owner 发起
   - 必须明确目标、范围、交付物、时间点、回报格式、禁止项

3. `【接单】`
   - 作用：主责 agent 确认接手并开始执行
   - 使用者：主责 agent

4. `【进展】`
   - 作用：阶段状态同步
   - 使用者：当前主责 agent

5. `【风险】`
   - 作用：阻塞、依赖、冲突、超时、边界不清上报
   - 使用者：当前主责 agent 或 `Hermes_CEO`

6. `【交付】`
   - 作用：阶段结果或完整结果回交
   - 使用者：当前主责 agent

7. `【催办】`
   - 作用：针对时效、责任、节点的正式催办
   - 使用者：`Hermes_CEO`

8. `【结论】`
   - 作用：阶段收口或最终收口
   - 使用者：仅 `Hermes_CEO`

9. `【仲裁】`（特殊）
   - 作用：仅用于职责冲突、标签错误、越界、流程失配、交接不合规时的纠偏
   - 使用者：仅 `Hermes_CEO`
   - **不得拿来补普通派单细节**

### 5.2 固定流程

正式项目启动顺序固定为：

`【受理】 → 【派单】 → 【接单】 → 【进展】/【风险】 → 【交付】 → 【结论】`

补充：
- `【催办】` 可在任意节点插入
- `【仲裁】` 只在纠偏时插入，纠偏完成后必须回到主流程

### 5.3 标签硬规则

- `【受理】` 和 `【派单】` 不是一回事
- 只要正文是执行单 / 协作单 / 正式任务分配，必须使用 `【派单】`
- 若上一条标签误用，应明确：
  - “上一条标签不作为正式派单口径，以下【派单】为准”
- 一个动作只使用一个标签，不得在一条消息中混合多个正式动作

---

## 6. 主责归属与 mention 角色规则

### 6.1 一条正式消息只有一个当前 owner

硬规则：
1. 一条正式消息只能有 1 个“主接单对象 / 当前 owner”
2. 在 `【派单】` 中：
   - 第一真实 mention = 主接单对象（唯一，必须回 `【接单】`）
   - 其他真实 mention 只能是“协作知会”或“收口抄送”
3. `下一责任人` 只用于交接型消息（如 `【交付】` / `【催办】` / `【仲裁】` 之后），默认应为单数
4. 如果同一条 `【派单】` 同时出现多个真实 mention，正文必须显式区分：
   - 主接单：@xxx
   - 协作知会：@xxx
   - 收口抄送：@Hermes_CEO
5. 在 `【派单】` 场景下，只有“主接单”承担首个 `【接单】` 义务
6. 若需要给协作对象单独下任务，应另发一条独立 `【派单】`，而不是在一条消息里设置多个 owner
7. 即使两个人接收的正文完全相同，只要责任归属是两条独立链路，也必须拆成两条正式消息；“同内容”不能作为并列双 owner 的理由
8. `【催办】` / `【仲裁】` 同样遵守单 owner 规则：若需要分别追两个人的时效或责任，应各发各的正式消息并分别验 receipt
9. 若确实只想发统一提醒或公告，可在日常消息中多 @，或在正式消息中保留一个 owner、其他对象仅作协作知会/收口抄送；不得把多 @ 公告伪装成多人并列正式派单/催办

### 6.2 正式责任字段写法

凡是主责、协作、收口、回交对象、下一责任人等正式责任字段：
- 必须使用群内真实显示名
- 正式责任字段应尽量使用真实 mention
- 禁止写 profile 名或抽象角色名，如 `default` / `it-agent` / `cc-agent`

---

## 7. 模板治理规则

### 7.1 短模板适用边界

短模板只适用于：
- 首响
- 轻量催办
- 已明确上下文下的单动作提醒

短模板不适用于：
- 正式项目派单
- 跨 agent 协同启动
- 当日执行单
- 需要明确交付物 / 时间点 / 禁止项的任务

满足以下任一条件，必须升级为结构化模板：
1. 涉及 2 个及以上 agent
2. 需要当天或分阶段交付
3. 需要明确主责 / 协作 / 收口
4. 需要明确交付物、时间点、回报格式、禁止项

### 7.2 执行单 / 协作单最小字段

正式 `【派单】` 最少包含：
- 目标
- 范围
- 交付物
- 时间点
- 回报格式
- 禁止项
- 协作接口（若有）
- 收口责任人

复杂派单新增规则：
- 不要求把所有复杂细节塞进一条群消息
- 当交付项超过 5 条、存在多阶段时点、字段级要求或明确验收清单时，应升级为 **rich 派单**
- rich 派单采用：`摘要卡（群内正式派单） + annex（文档/附件/Base/长文附录）`
- 群内卡片仍只保留：owner / goal / Top 交付 / 时间点 / 回报格式 / 禁止项 / annex 入口 / receipt

### 7.3 短模板与标准模板并行

模板体系统一分为：
- short：首响、轻量催办、短确认、已知上下文下的单动作推进
- standard：当前 interactive card 9 类模板
- rich：复杂派单 / 复杂交付 / 复杂风险，采用“摘要卡 + annex”

优先适合 short 的消息类型：
- `【受理】`
- `【接单】`
- `【进展】`
- `【风险】`
- `【催办】`
- `【结论】`

### 7.4 首响优先于完整长文

当正式派单 / 催办 / 仲裁已成立，且主责 agent 已真实收到任务时：
- 首响目标是先建立可观察状态
- 不允许等待完整长文才首次回应

推荐 SLA：
- 轻任务：10~15 秒内短状态
- 常规任务：30 秒内 `【接单】` 或 `【进展】`
- 若 60 秒内仍无阶段结论，至少先回一个短正式状态

### 7.4 消息排版建议（新增）

为提升群内正式消息的可读性与可扫描性，正式模板建议统一采用轻量分层排版：
- 一级信息使用无序列表 `-`
- 步骤、交付项、时间点使用有序列表 `1. 2. 3.`
- 需要二级说明时，使用缩进二级列表
- 单条正式消息优先控制在 4~8 行核心内容；超出部分应拆到下一条【进展】或【交付】
- 可适度使用 emoji 提升辨识度，但必须克制、专业，不得影响正式性

推荐做法：
- `【受理】` / `【催办】` / `【结论】`：优先短列表
- `【派单】` / `【交付】`：优先“无序列表 + 有序列表”混合结构
- `【风险】`：固定写成“风险点 / 影响范围 / 需要协助 / 建议决策”四段

不推荐做法：
- 一整段长文本无分层
- 一条消息中混用过多层级
- 为了好看堆过多 emoji 或装饰字符
- 将复杂背景、长解释和正式动作混在同一条正式消息中

---

## 8. 长线程 phase 收口规则

当满足任一条件时，应优先收口再进入下一阶段：
- 同一阶段连续出现 2 次及以上 `【进展】` 仍未形成 `【交付】` 或 `【结论】`
- 讨论跨 2 个以上子目标
- 出现“继续吗 / 还在吗 / phase B / 下一阶段 / 先收口”等切段信号
- 触发 compression / timeout / fallback / response ready 高延迟
- 主责 agent 已获得足以支撑阶段结论的证据

收口动作：
1. 主责 agent 优先回 `【交付】` 或 `【风险】`
2. `Hermes_CEO` 尽快回 `【结论】` 或必要时 `【仲裁】`
3. 下一阶段必须用新一条正式消息继续，而不是在旧阶段无限续写

phase 收口正式消息正文只保留：
- 阶段结论
- 当前状态
- 责任人
- 下一步
- receipt

约束：
- 优先 4~6 行
- 单条只承载一个动作
- 不把长分析继续堆在群主线程

---

## 9. 冒烟测试与长期巡检机制

### 9.1 新 agent 准入 smoke test

新增 agent 入群后，不得直接开始正式协作。必须至少完成 3 条真实消息：
1. `【接单】` → mention `Hermes_CEO`
2. `【进展】` → mention 协作对象
3. `【交付】` → mention 下一责任人（使用 `--next-owner` 并确认其出现在 `mentions[]`）

每条必须留存：
- `message_id`
- `target_display_name`
- `target_open_id`
- `canonical_open_id`
- `allowed_open_ids_for_sender`
- `actual_mention_open_id`
- `compat_mode`
- `sender_id`
- `sender_type`
- `mention_verified`

### 9.2 在岗 agent 周期性 smoke test

为防止规则回退，已在岗 agent 也应周期性抽检：
- `Hermes_CEO`：检查 `【受理】` / `【派单】` / `【结论】`
- `大T_技术总工`：检查 `【接单】` / `【进展】` / `【交付】`
- `大C_内容总监`：检查 `【接单】` / `【进展】` / `【交付】`

建议频率：
- 新规则上线后一周内：每天一次轻量抽检
- 稳定后：每周一次
- 发生 sender / registry / 脚本变更后：立即补测

### 9.3 监测口径

监测只认：
- `message_id`
- `receipt`
- `mention_verified = true`
- `all_required_mentions_match = true`（若脚本返回该字段）

不再接受“看起来像 @ 了”的人工肉眼判断。

---

## 10. 同步覆盖范围

本轮治理必须同步覆盖：
- 群协同 SOP
- 相关 skills
- 群规文档
- onboarding 文档
- mention registry 文档
- formal wrapper / sender 脚本说明

迁移原则：
- 不再保留“纯文本 @ 也勉强算”的灰区
- 不再保留“先发说明，之后补 formal message”的灰区
- 不再保留“无 receipt 也算完成”的灰区
- 不再允许“显示名猜对象”
- 不再允许“一个派单多个 owner”的灰区
- 不再允许“用【仲裁】补普通派单”的灰区

---

## 11. 当前结论

从本规范 v2 生效起：
- Hermes 总裁办群正式消息统一收敛为 **wrapper → verified mention → receipt**
- 正式消息类型统一收敛为 **8+1 标准**
- 一条正式消息只允许一个当前 owner
- 正式项目派单统一使用 `【派单】`
- `【仲裁】` 只用于纠偏，不能替代正常派单
- 所有 agent 必须遵守同一套长期治理、抽检与冒烟验收机制
