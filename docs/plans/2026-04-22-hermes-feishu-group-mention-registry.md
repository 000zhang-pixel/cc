# Hermes 总裁办群真实 Mention 映射与校验规则（2026-04-22）

> 目的：统一固化 Hermes 总裁办群内多 agent 协作时的真实 mention 对象与验收规则，避免再出现“纯文本 @ / 错对象 / 用错 sender 身份仍被算完成”的问题。
>
> 自 2026-04-23 起，本文件定位为 **对象映射与证据真值表**。关于正式消息流程、回执、所有 agent 的统一协作纪律、新 agent 设置规范与进群验收，请以：
> - `docs/plans/2026-04-23-hermes-multi-agent-formal-message-governance.md`
> - `docs/plans/2026-04-23-hermes-new-agent-onboarding-checklist.md`
> 为准。

---

## 1. 适用范围

- 群名称：`Hermes 总裁办`
- `chat_id`: `oc_ea99db0c239b28740dc6571e89b9a808`
- 适用场景：正式派单、交接、催办、仲裁、验收、结果回传

---

## 2. 核心规则

### 2.1 真实 mention 的唯一验收标准
正式 @ 仅在同时满足以下条件时成立：
1. 消息回读后 `body.content` 出现 `@_user_N`
2. `mentions[]` 非空
3. `mentions[]` 中命中目标对象

**不满足任一项，视为未完成正式 mention。**

### 2.2 纯文本 @ 不算
以下形式一律不算正式 mention：
```text
@大T_技术总工
@大C_内容总监
@Hermes总规划师
```
如果消息回读后 `mentions=[]`，即使界面上看起来像 @，也不计为完成。

### 2.3 sender 身份要求
在群内正式技术回单时：
- it-agent 必须使用自己的 agent/app 身份 `大T_技术总工`
- 不得切换成 Kenny user auth 代发来冒充完成
- 若当前 gateway 回复无法满足真实 mention 验收，应先发【风险】说明，再等 default / Hermes_CEO 仲裁

### 2.4 稳定标识规则
- 机器锚点以 `open_id` 为准
- 显示名只用于人类可读，不可作为机器执行依据
- 从 2026-04-23 v2 起，目标对象需区分：
  - `canonical_open_id`：当前正式对象
  - `compatible_open_ids_by_sender`：不同 sender 可接受的兼容对象
- `open_id` 在当前 tenant / 应用上下文里视为稳定标识；若未来对象重建、租户切换、权限体系变化，应重新验收

---

## 3. 当前已验证的核心 agent mention 映射表

> 以下值均来自群消息实体回读，不是人工猜测。

| Agent 显示名 | 真实 mention `open_id` | 证据消息 `message_id` | 备注 |
|---|---|---|---|
| Hermes_CEO | `ou_3320aee078910b0973175037639620ba` | `om_x100b51499b5758a0b261a89a87114c2` | 当前正式名称；已回读 `mentions[]` 命中 |
| 大C_内容总监 | `ou_a4542cef2c4c5d95de1ff64eca5d5b5a` | `om_x100b52fc2f6d88acc4fbd2757871c17` | 已回读 `mentions[]` 命中 |
| 大T_技术总工 | `ou_1814da833564decc63d23f857fc5a47d` | `om_x100b517339977ca8b3f035d85a29aea` | 已回读 `mentions[]` 命中 |

---

## 4. 证据摘要

### 4.1 Hermes_CEO（旧名：Hermes总规划师）
- 历史旧名证据：`om_x100b52f27c5ceca8c2a6af085046c9a`
  - `mentions[0].name`: `Hermes总规划师`
  - `mentions[0].id`: `ou_3320aee078910b0973175037639620ba`
- 当前正式名称证据：`om_x100b51499b5758a0b261a89a87114c2`
  - `mentions[2].name`: `Hermes_CEO`
  - `mentions[2].id`: `ou_3320aee078910b0973175037639620ba`
- 结论：二者为同一目录对象，仅名称已变更，不是两个独立 agent。

### 4.2 大C_内容总监
- `message_id`: `om_x100b52fc2f6d88acc4fbd2757871c17`
- `mentions[3].name`: `大C_内容总监`
- `mentions[3].id`: `ou_a4542cef2c4c5d95de1ff64eca5d5b5a`

### 4.3 大T_技术总工
- `message_id`: `om_x100b517339977ca8b3f035d85a29aea`
- `mentions[0].name`: `大T_技术总工`
- `mentions[0].id`: `ou_1814da833564decc63d23f857fc5a47d`

---

## 5. 强制执行要求

### 5.1 所有 agent 必须记住
在 Hermes 总裁办群内，所有 agent 必须记住本表中的真实 mention 映射；涉及正式交接、催办、仲裁、验收时，必须优先使用该映射，不得再靠显示名猜测。

### 5.2 交付/派单必须满足双重校验
每次正式消息都要同时校验：
1. sender 身份是否正确
2. `mentions[]` 是否命中正确对象

### 5.3 正式消息必须附回执
自 2026-04-23 起，正式【接单】【进展】【风险】【交付】【催办】【仲裁】【结论】在技术执行侧必须附脚本回执；无回执不算正式完成。

最少必须包含：
- `message_id`
- `mention_verified`
- `target_display_name`
- `target_open_id`
- `sender_id`
- `sender_type`

v2 推荐补充：
- `canonical_open_id`
- `allowed_open_ids_for_sender`
- `actual_mention_open_id`
- `compat_mode`
- `runtime_env_path`

推荐直接使用 `middleware/scripts/feishu_formal_message.py` 输出中的 `receipt` 字段作为标准回执。

### 5.4 若映射失效
出现以下任一情况，需要重新验收并更新本表：
- `mentions[]` 不再命中当前显示名
- 群内成员/agent 被重建
- tenant / app 权限发生变化
- sender 身份或群聊路由发生迁移

---

## 6. 推荐自查方法

### 6.0 强制发送器（推荐默认入口）
自 2026-04-23 起，正式消息不要再手写 `<at ...>` 或纯文本 `@`。统一走一行入口：

```bash
python3.11 middleware/scripts/feishu_formal_message.py \
  交付 Hermes_CEO "已完成技术排查，待你拍板。"
```

或 shell 包装：

```bash
middleware/scripts/feishu_formal_message.sh \
  进展 大C_内容总监 "第一批校验已完成"
```

其底层仍委托 `middleware/scripts/feishu_verified_mention_send.py`，并强制执行：
1. 从 `middleware/config/feishu_mention_registry.json` 解析目标对象，不允许靠显示名猜测
2. 用 app sender 发送
3. 发送后立即回读消息实体
4. 同时校验：`chat_id`、`sender_type`、`sender.id`、`body.content` 是否含 `@_user_N`、`mentions[]` 是否命中预期对象
5. 任一项失败即非 0 退出，不得算交付完成
6. 常用 preset 已内置：`plain / eta / blocked / handoff`

### 6.1 查最近消息
```bash
/Users/carson/.npm-global/bin/lark-cli api GET /open-apis/im/v1/messages \
  --as app \
  --params '{"container_id_type":"chat","container_id":"oc_ea99db0c239b28740dc6571e89b9a808","page_size":10}'
```

### 6.2 精确回读某条证据消息
```bash
/Users/carson/.npm-global/bin/lark-cli api GET /open-apis/im/v1/messages/om_x100b517339977ca8b3f035d85a29aea --as app
```

### 6.3 验收项
- `body.content` 含 `@_user_N`
- `mentions[]` 非空
- `mentions[].name` 与预期显示名一致
- `mentions[].id` 与本表记录一致
- `sender.sender_type` 与预期一致
- `sender.id` 与当前 agent/app 身份一致

---

## 7. 当前结论

从 2026-04-22 起，Hermes 总裁办群内 3 个核心 agent 的真实 mention 对象已坐实。后续凡正式协作消息：
- 必须按本表使用真实 `open_id`
- 必须按 `mentions[]` 验收
- 不满足即不算完成
