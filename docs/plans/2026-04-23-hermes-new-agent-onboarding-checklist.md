# Hermes 新 Agent 设置与进群验收清单（2026-04-23）

> 用途：为后续新增 agent 提供统一 checklist。未完成清单，不得进入 Hermes 总裁办群承担正式协作责任。

---

## A. Agent 基础设置

- [ ] 已确认 agent 名称 / 显示名称
- [ ] 已确认 agent 职责边界
- [ ] 已确认主模型 / 备用模型
- [ ] 已确认群内身份口吻（不得冒充 Kenny / 其他 agent）
- [ ] 已明确正式消息标签使用范围

需登记字段：
- `agent_name`:
- `display_name`:
- `role_scope`:
- `primary_model`:
- `fallback_models`:
- `sender_type`:
- `sender_id`:

---

## B. 正式消息机制接入

- [ ] 已接入 `middleware/scripts/feishu_formal_message.py`
- [ ] 已接入 `middleware/scripts/feishu_verified_mention_send.py`
- [ ] 已确认 `middleware/config/feishu_mention_registry.json` 可读取
- [ ] 已确认 app auth / gateway 路由正常
- [ ] 已明确：正式消息必须带 `receipt`
- [ ] 已明确：普通说明文字不算正式消息
- [ ] 已明确：未走 formal wrapper 时必须使用独立 `【说明】` 模板，不得伪装成 receipt
- [ ] 已确认 sender 对应 `env_path` 可被 formal sender 正确装载

---

## C. Registry 与对象映射

- [ ] 已确认该 agent 的 directory object / open_id
- [ ] 已写入或更新 `feishu_mention_registry.json`
- [ ] 已补充证据 `message_id`
- [ ] 已在文档中记录正式显示名 / 旧名（若有）

需登记字段：
- `canonical_open_id`:
- `compatible_open_ids_by_sender`:
- `display_name`:
- `aliases`:
- `evidence_message_id`:
- `env_path`:

---

## D. 入群 smoke test（强制）

至少完成以下 3 条：

- [ ] `【接单】` → mention `Hermes_CEO`
- [ ] `【进展】` → mention 协作对象
- [ ] `【交付】` → mention 下一责任人（使用 `--next-owner`，并确认其出现在 `mentions[]`）

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

---

## E. Skills / 群规 / onboarding 文档同步

- [ ] 已 patch 相关 SOP / skills
- [ ] 已同步多 agent 协作规范
- [ ] 已同步新 agent 设置规范
- [ ] 已同步新 agent 进群设置规范
- [ ] 已明确旧规则已被新规范覆盖

---

## F. 准入结论

只有以下条件全部成立时，新增 agent 才可进入正式协作：

- [ ] smoke test 全通过
- [ ] receipt 完整
- [ ] registry 可查
- [ ] 文档齐全
- [ ] 技能已更新
- [ ] default / Hermes_CEO 已确认准入

准入状态分级：
- `healthy`：sender 正确，且目标命中 canonical 对象
- `compat-verified`：sender 正确，目标未命中 canonical，但在 `allowed_open_ids_for_sender` allowlist 下验收通过
- `blocked`：sender 不正确、mention 未通过、无 receipt，或不在 allowlist 内

结论：
- [ ] 允许进群正式协作（healthy）
- [ ] 允许进群正式协作（compat-verified）
- [ ] 仅允许观察，不允许正式回单
- [ ] 打回重配（blocked）
