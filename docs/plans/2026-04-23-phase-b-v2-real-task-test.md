# Phase B-v2 真实任务测试结果（2026-04-23 08:49）

## Objective
在 smoke 之外补做一轮真实任务文本测试，确认三套 sender identity 在真实协作语义下仍能通过 formal wrapper、verified mention 与 receipt 验收。

## Input
- 结果 JSON：`tmp/phase-b-v2-real-task-test-20260423-084921.json`
- 已完成的 smoke 基线：`docs/plans/2026-04-23-phase-b-v2-real-smoke-results.md`

## Cases
1. `default_app` → `【接单】` `Hermes_CEO`
   - 文本：已受理，将根据 Phase B-v2 结果更新多 agent 协同状态结论，并同步主责任务板。
2. `cc_agent_app` → `【进展】` `大T_技术总工`
   - 文本：内容侧配合说明，formal wrapper 与 sender 兼容性结果已可作为后续协同验收前提，待技术侧给出最终收口结论。
3. `it_agent_app` → `【交付】` `Hermes_CEO`
   - 文本：技术收口，Phase B-v2 已确认 default_app/cc_agent_app 为 compat-verified，it_agent_app 为 healthy；真实任务测试通过，可按新状态执行正式协作。

## Result
- 总计：`3/3 VERIFIED`
- `default_app`: PASS
- `cc_agent_app`: PASS
- `it_agent_app`: PASS

## Verification summary
| identity | label | target | sender_id | actual_mention_open_id | compat_mode | canonical_match | result |
|---|---|---|---|---|---|---|---|
| default_app | 接单 | Hermes_CEO | `cli_a948f1034ba35cce` | `ou_726cfff63d194e4aea7345e7ee4fbfc0` | true | false | PASS |
| cc_agent_app | 进展 | 大T_技术总工 | `cli_a8f5ef35f9eb900e` | `ou_60d562d442dfc60042362125708d9341` | true | false | PASS |
| it_agent_app | 交付 | Hermes_CEO | `cli_a93b91d797b8dccb` | `ou_3320aee078910b0973175037639620ba` | false | true | PASS |

## Message evidence
- `default_app` message_id: `om_x100b51a287e50084c3c911c932b96bf`
- `cc_agent_app` message_id: `om_x100b51a287f3f8a0c366fef1cb0df9c`
- `it_agent_app` message_id: `om_x100b51a287991080c2b34ac771c72b5`

## Conclusion
1. Phase B-v2 的 sender 修复不只在 smoke 文本下有效，在真实任务文本下也成立。
2. `default_app` / `cc_agent_app` 当前结论可以稳定定级为 `compat-verified`，不再属于 blocked。
3. `it_agent_app` 继续作为 `healthy` 基线 sender。

## Today scope control
- 内容过期治理 / 历史 drift 处置：**已转入待办，今天不执行**。
- 今日主线仅收口多 agent 协同 Phase B-v2。
