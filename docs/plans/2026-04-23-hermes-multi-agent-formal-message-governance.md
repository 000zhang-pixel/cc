# Hermes 多 Agent 正式消息治理规范 v1（2026-04-23）

> 目的：用统一、可执行、可验收的机制，覆盖之前 Hermes 总裁办群内关于正式消息、真实 mention、sender 身份、回执、agent 协作的零散规则，避免再次出现“看起来像正式回复，但实际没有命中 mention / sender 不对 / 没有回执”的问题。

---

## 1. 适用范围

- 群：`Hermes 总裁办`
- `chat_id`: `oc_ea99db0c239b28740dc6571e89b9a808`
- 适用对象：`default` / `it-agent` / `cc-agent` / 后续新增 agent
- 适用消息类型：
  - `【受理】`
  - `【接单】`
  - `【进展】`
  - `【风险】`
  - `【交付】`
  - `【催办】`
  - `【仲裁】`
  - `【结论】`

---

## 2. 规范优先级（新规则覆盖旧规则）

本规范自 2026-04-23 起，覆盖此前所有不完整、不一致或只停留在口头/提示层面的旧规则。

优先级如下：
1. **本规范**（正式消息治理总则）
2. `docs/plans/2026-04-23-hermes-long-thread-observability-and-phase-closure.md`（长线程观察、时延分级与 phase 收口执行规范）
3. `docs/plans/2026-04-22-hermes-feishu-group-mention-registry.md`（对象映射与证据表）
4. `middleware/config/feishu_mention_registry.json`（机器可执行 registry）
5. `middleware/scripts/feishu_formal_message.py/.sh`（正式消息入口）
6. `middleware/scripts/feishu_verified_mention_send.py`（底层发送与验证器）
7. 相关 skills / agent prompt / onboarding 文档

如旧规则与本规范冲突，以本规范为准。

---

## 3. 正式消息的定义

只有同时满足下列条件的消息，才算正式消息：

1. 通过 `feishu_formal_message.py` 或 `feishu_formal_message.sh` 发出
2. 底层委托到 `feishu_verified_mention_send.py`
3. 消息回读通过 mention 验证
4. 具备标准 `receipt`
5. `receipt.mention_verified = true`

**任何直接在聊天框手写的【接单 / 进展 / 风险 / 交付 / 催办 / 仲裁 / 结论】文本，都不算正式消息。**

---

## 4. 强制执行规则

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

补充规则（自 v2 起）：
- registry 必须区分 `canonical_open_id` 与 `compatible_open_ids_by_sender`
- 验收时先按 sender 身份取允许命中的 `open_id` 集合
- `actual_mention_open_id ∈ allowed_open_ids_for_sender` 才算 mention 通过
- 若 `actual_mention_open_id != canonical_open_id`，必须在 receipt 中标记 `compat_mode=true`

任一失败即不算正式完成。

### 4.3 回执强制要求

正式消息必须附 `receipt`。最少包含：
- `message_id`
- `mention_verified`
- `target_display_name`
- `target_open_id`
- `sender_id`
- `sender_type`

v2 推荐字段：
- `canonical_open_id`
- `allowed_open_ids_for_sender`
- `actual_mention_open_id`
- `compat_mode`
- `runtime_env_path`

无回执 = 无正式完成。

### 4.4 先发送、后说明

若 agent 需要在群内解释状态或交付内容，顺序必须是：
1. 先通过 wrapper 发送正式消息
2. 拿到 `receipt`
3. 再在当前会话中补充说明

禁止反过来：先解释、后补 formal message。

### 4.5 角色与 sender 身份一致

每个 agent 必须使用自己的 agent/app sender 身份：
- default 只能以 default 对应身份发送
- it-agent 只能以 `大T_技术总工` 身份发送
- cc-agent 只能以 `大C_内容总监` 身份发送
- 禁止切换为 Kenny user auth 冒充正式完成

---

## 5. 所有 agent 的统一协作要求

### 5.1 正式状态标签必须标准化

正式消息仅允许使用以下标签：
- `【受理】`
- `【接单】`
- `【进展】`
- `【风险】`
- `【交付】`
- `【催办】`
- `【仲裁】`
- `【结论】`

### 5.2 责任交接必须真实 mention 下一责任人

凡涉及主责切换、协作交接、催办、仲裁、验收，都必须真实 mention 下一责任人。

自 2026-04-24 起，formal wrapper 对此采用统一参数：

```bash
python3.11 middleware/scripts/feishu_formal_message.py \
  交付 Hermes_CEO "已完成技术修复，待复核。" \
  --next-owner 大C_内容总监
```

验收口径：
- 主 target 与 `--next-owner` 都必须出现在消息 `mentions[]`
- receipt 必须回传 `required_targets / next_owner_display_names / next_owner_open_ids`
- 只在正文写“下一责任人：显示名”而没有真实 mention，不算正式交接完成

### 5.3 无 receipt 不算完成

对 default / Hermes_CEO / 下一责任人的正式交付，不得只写“已完成”。必须给出 receipt 或至少回传 receipt 核心字段。

### 5.4 普通聊天与正式消息分离

可保留普通聊天、补充解释、讨论性内容；但这些内容一律不得被拿来充当正式派单、验收或交付依据。

### 5.5 未走 formal wrapper 时必须使用“非正式说明模板”

若当前回复**没有**通过 formal wrapper 发送，则不得伪装成正式回执，不得混用 `receipt` 结构。建议统一采用以下模板：

```text
【说明】
- 性质：非正式说明 / 技术分析 / 过程同步
- formal_wrapper：未使用
- mention_verified：不适用
- 正式性：本条不计入正式派单/交付/验收回执
- 如需正式生效：请以 wrapper 发送正式消息并附 receipt
```

强制要求：
- 禁止在非正式说明里继续输出看似正式的 `receipt`
- 禁止把“未走 wrapper 的解释性回复”写成“已正式完成”口吻
- 若后续需要正式生效，必须另发 formal wrapper 消息

---

## 6. 新 agent 设置规范（创建阶段）

新增 agent 时，必须同时完成以下配置，才允许进入 Hermes 总裁办群执行正式工作。

### 6.1 身份配置

必须具备：
- 固定显示名称
- 固定 sender/app identity
- 固定职责边界
- 固定协作标签习惯

至少记录：
- `display_name`
- `sender_id`
- `sender_type`
- `role_scope`
- `allowed_formal_labels`

### 6.2 prompt / system 规范要求

新增 agent 的系统提示必须明确：
1. 群内正式消息只能通过 formal wrapper 发送
2. 正式消息必须真实 mention 命中目标对象
3. 正式消息必须带 receipt
4. 普通说明文字不算正式回复
5. sender 身份必须与 agent 本人一致

### 6.3 工具依赖要求

新增 agent 投产前，必须确认其环境可用：
- `middleware/scripts/feishu_formal_message.py`
- `middleware/scripts/feishu_verified_mention_send.py`
- `middleware/config/feishu_mention_registry.json`
- 对应 app auth / gateway 路由 / 群聊权限

---

## 7. 新 agent 进群设置规范（入群前与入群后）

### 7.1 入群前准备

新增 agent 在进群前，必须完成：
1. 确认正式显示名称
2. 确认 sender 身份与 app 路由
3. 在 `feishu_mention_registry.json` 预留/补充对象信息（若已有 directory object）
4. 在 onboarding 文档中登记职责与交接口径

### 7.2 入群后首次验收（强制）

新增 agent 进群后，不得直接开始正式协作。必须先完成 smoke test：

最少 3 条：
1. `【接单】` → mention `Hermes_CEO`
2. `【进展】` → mention 主责协作对象
3. `【交付】` → mention 下一责任人

每条都必须：
- 回读 `mentions[]`
- 校验 sender 身份
- 校验 `mentions[].id` 与 registry 目标 `open_id` 完全一致（不能只看名称）
- 生成 `receipt`
- 留存 `message_id`

补充强制规则：
- smoke test 结果是 **sender-specific** 的；同一 target open_id 在不同 sender app 下可能解析成不同 directory object
- 因此不得因为某一个 agent/sender 通过，就默认其他 agent/sender 对同一 target 也自动通过
- 任一 sender 只要出现 `mention_name_match=true` 但 `mention_id_match=false`，该 sender 仍视为 **未通过入群/正式协作验收**

### 7.3 入群验收通过标准

新增 agent 只有在以下条件同时满足时，才算具备正式协作资格：
- 3 条 smoke test 全通过
- registry 中有该 agent 的正式对象映射
- 文档已记录其身份、职责、sender、验收证据
- 相关 skills / onboarding 规范已更新

验收状态分级：
- `healthy`：sender 正确，且目标命中 canonical 对象（`canonical_match=true`, `compat_mode=false`）
- `compat-verified`：sender 正确，目标未命中 canonical，但 `actual_mention_open_id ∈ allowed_open_ids_for_sender`，因此在 sender-specific compatibility allowlist 下通过（`mention_verified=true`, `compat_mode=true`）
- `blocked`：sender 不正确、mention 未验证通过、无 receipt，或不在 allowlist 内

---

## 8. 变更流程（旧规则到新规则的覆盖方式）

### 8.1 必改对象

这次治理必须同步覆盖：
- 群规文档
- mention registry 文档
- Formal sender / wrapper 脚本
- 相关 skills
- 新 agent 设置规范
- 新 agent 进群设置规范

### 8.2 迁移原则

- 不再保留“纯文本 @ 也勉强算”的灰区
- 不再保留“先发说明，之后补 formal message”的灰区
- 不再保留“无 receipt 也算完成”的灰区
- 不再允许“显示名猜对象”

---

## 9. 测试与监测策略

### 9.1 本地无副作用验证

使用 dry-run 矩阵：
- 标签 × 目标对象 的组合校验
- 核对 registry 解析、sender、receipt 字段

### 9.2 真实 smoke test

至少验证：
- 1 条 it-agent → Hermes_CEO
- 1 条 it-agent → 大C_内容总监
- 1 条 it-agent → 大T_技术总工（自验）

后续 default / cc-agent / 新 agent 也应各自完成真实 smoke test。

### 9.3 监测口径

监测只认：
- `message_id`
- `receipt`
- `mention_verified = true`

不再接受“看起来像 @ 了”的人工肉眼判断。

---

## 10. 当前落地建议

### Phase 1：规范归一
- 发布本规范
- 让 mention registry 成为对象真值表
- 所有正式消息统一走 wrapper

### Phase 2：技能与 onboarding 归一
- patch 现有 SOP / skills
- 新建新 agent onboarding 规范
- 明确所有 agent 的 formal message 纪律

### Phase 3：持续监测
- 对正式消息持续抽查 receipt
- 新 agent 入群先 smoke test，再投入正式协作

---

## 11. 当前结论

从本规范生效起：
- Hermes 总裁办群的正式消息验收标准统一收敛为 **wrapper → verified mention → receipt**
- 所有 agent 必须遵守同一套正式消息机制
- 旧有不完整、不全面的设计应视为被本规范覆盖
