# Phase B-v2 真实 smoke 结果单（2026-04-23 08:25）

## Objective
复跑 Hermes 总裁办 formal wrapper sender compatibility 的全量 9 条真实 smoke，确认 `default_app` / `cc_agent_app` / `it_agent_app` 是否都能以各自 sender 身份完成正式消息发送与 verified mention 验收。

## Inputs
- 代码修复：`middleware/scripts/feishu_verified_mention_send.py`
  - `get_tenant_access_token()` 改为优先读取 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`
- 运行结果 JSON：`tmp/phase-b-v2-smoke-rerun-20260423-082449.json`
- 之前失败样本：`tmp/phase-b-v2-smoke-retry-20260423-081942.json`

## Commands
```bash
python3.11 -m py_compile \
  middleware/scripts/feishu_verified_mention_send.py \
  middleware/scripts/feishu_formal_message.py \
  middleware/scripts/feishu_formal_governance_audit.py
```

随后逐条执行 9 条真实发送：
- `default_app`: 接单 / 进展 / 交付
- `cc_agent_app`: 接单 / 进展 / 交付
- `it_agent_app`: 接单 / 进展 / 交付

## Summary
- 编译检查：`PASS`
- 总计：`9/9 VERIFIED`
- `default_app`: `3/3 PASS`
- `cc_agent_app`: `3/3 PASS`
- `it_agent_app`: `3/3 PASS`

## Key Findings
### 1. 之前失败的直接根因已确认
不是 Feishu 发送失败，也不是 formal wrapper 本身坏掉。

直接根因是：
- runtime 读取凭证时优先命中了 `middleware/.env` 中的 `LARK_APP_ID/LARK_APP_SECRET`
- 该默认 env 实际固定指向 `it_agent_app`
- 导致 `default_app` / `cc_agent_app` 虽然 `--identity` 正确，但真实发送 sender 仍落到 `it_agent_app`

### 2. 修复后 sender 身份已恢复正确
- `default_app` → `sender_id=cli_a948f1034ba35cce`
- `cc_agent_app` → `sender_id=cli_a8f5ef35f9eb900e`
- `it_agent_app` → `sender_id=cli_a93b91d797b8dccb`

### 3. sender-specific compatibility map 仍然必要
修复 sender 凭证后：
- `default_app` / `cc_agent_app` 多数 case 为 `compat_mode=true`
- `it_agent_app` 为 `compat_mode=false`

说明：
- sender-specific mention drift 依然存在
- 但已不再阻塞正式协作，因为 receipt 已在 allowlist 下 `mention_verified=true`

## Result Matrix
| identity | label | target | sender_id | actual_mention_open_id | compat_mode | result |
|---|---|---|---|---|---|---|
| default_app | 接单 | Hermes_CEO | `cli_a948f1034ba35cce` | `ou_726cfff63d194e4aea7345e7ee4fbfc0` | true | PASS |
| default_app | 进展 | 大C_内容总监 | `cli_a948f1034ba35cce` | `ou_1b6dd19e4c9acc55e55ecd1bfa955809` | true | PASS |
| default_app | 交付 | 大T_技术总工 | `cli_a948f1034ba35cce` | `ou_98710ba6bfeb92022e1acc5ca9c728e9` | true | PASS |
| cc_agent_app | 接单 | Hermes_CEO | `cli_a8f5ef35f9eb900e` | `ou_ede550e0a884cef820b59a9f6750509a` | true | PASS |
| cc_agent_app | 进展 | 大T_技术总工 | `cli_a8f5ef35f9eb900e` | `ou_60d562d442dfc60042362125708d9341` | true | PASS |
| cc_agent_app | 交付 | Hermes_CEO | `cli_a8f5ef35f9eb900e` | `ou_ede550e0a884cef820b59a9f6750509a` | true | PASS |
| it_agent_app | 接单 | Hermes_CEO | `cli_a93b91d797b8dccb` | `ou_3320aee078910b0973175037639620ba` | false | PASS |
| it_agent_app | 进展 | 大C_内容总监 | `cli_a93b91d797b8dccb` | `ou_a4542cef2c4c5d95de1ff64eca5d5b5a` | false | PASS |
| it_agent_app | 交付 | Hermes_CEO | `cli_a93b91d797b8dccb` | `ou_3320aee078910b0973175037639620ba` | false | PASS |

## Acceptance
本轮可将协作状态更新为：
- `default_app`: compat-verified
- `cc_agent_app`: compat-verified
- `it_agent_app`: healthy

补充验证：
- 真实任务文本测试见 `docs/plans/2026-04-23-phase-b-v2-real-task-test.md`
- 该轮测试结果为 `3/3 VERIFIED`，证明结论不仅限于 smoke 文本

## Residual Risks
1. compatibility map 仍需持续维护；如果群目录对象再漂移，需回填 registry allowlist。
2. 本结果证明 sender formal 协作链路恢复，不等于 prompt/content 历史错位问题已修复。
3. 当前 repo 仍有未提交改动，进入下一阶段前建议整理 commit。

## Next Step
按方案 A 收口多 agent 协同主线：
1. 将 Phase B-v2 结论同步到治理总文档与 sender 调查文档
2. 补做一轮非-smoke 的真实任务测试，验证三方 sender 在真实协作文本下仍能稳定通过
3. 将“内容过期治理”降级为独立待办，今天不进入执行
