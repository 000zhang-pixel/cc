# Hermes 总裁办 sender 兼容性排查报告（2026-04-23）

## Objective
定位为什么同一个正式 target 在不同 sender app 下会被 Feishu 解析成不同 `mentions[].id`，并给出后续修复方向。

## 范围
- chat: `Hermes 总裁办`
- chat_id: `oc_ea99db0c239b28740dc6571e89b9a808`
- senders:
  - `default_app` = `cli_a948f1034ba35cce`
  - `cc_agent_app` = `cli_a8f5ef35f9eb900e`
  - `it_agent_app` = `cli_a93b91d797b8dccb`
- targets:
  - `Hermes_CEO`
  - `大C_内容总监`
  - `大T_技术总工`

## 结论摘要
### Update（2026-04-23 08:25）
Phase B-v2 全量 9 条真实 smoke 已复跑，结果为 **9/9 VERIFIED**。

本次最终确认：
1. 之前 `default_app` / `cc_agent_app` 的失败主因，不是 Feishu API 发不出去；
2. 也不只是 registry 映射问题；
3. **直接根因是 sender env 凭证优先级错误**：脚本此前优先读取 `LARK_APP_ID/LARK_APP_SECRET`，而这些值在 `middleware/.env` 中固定指向 `it_agent_app`，导致 `default_app` / `cc_agent_app` 即使切了 `--identity`，真实发送仍然落到 `it_agent_app` sender 上；
4. 修复为优先读取 sender profile 内的 `FEISHU_APP_ID/FEISHU_APP_SECRET` 后，三套 identity 都能命中各自 sender_id，并在 sender-specific compatibility allowlist 下通过 mention 验收。

### 1. sender-specific compatibility 仍然存在，但已不是当前阻塞根因
修复凭证优先级后，所有样本都满足：
- `chat_match=true`
- `sender_type_match=true`
- `sender_id_match=true`
- `body_has_placeholder=true`
- `mentions_non_empty=true`
- `mention_name_match=true`
- `mention_verified=true`

差异点变成：
- `default_app` / `cc_agent_app` 多数 case 为 `canonical_match=false`、`compat_mode=true`
- `it_agent_app` 为 `canonical_match=true`、`compat_mode=false`

因此当前技术判断应更新为：
- sender-specific mention resolution drift **客观存在**；
- 但本轮 smoke 失败的直接原因是 **wrong sender credentials selected at runtime**；
- 修复凭证优先级后，compatibility map 方案能够稳定兜住多 sender 场景。

### 2. `it_agent_app` 当前命中的是“正式 canonical 对象”
control baseline 显示：
- `Hermes_CEO` → `ou_3320aee078910b0973175037639620ba`
- `大C_内容总监` → `ou_a4542cef2c4c5d95de1ff64eca5d5b5a`
- `大T_技术总工` → `ou_1814da833564decc63d23f857fc5a47d`

这与当前 mention registry / evidence doc 一致，因此 **canonical target 映射本身没有坏**。

### 3. `default_app`、`cc_agent_app` 命中的是“历史 sender 视角下的兼容对象”
从 profile/env 与历史 session 证据看：
- `default_app` 会把 `Hermes_CEO` 解析到自己的 bot open_id：`ou_726cfff63d194e4aea7345e7ee4fbfc0`
- `default_app` 对 `大C_内容总监` / `大T_技术总工` 会解析到旧的人物对象：
  - `大C_内容总监` → `ou_1b6dd19e4c9acc55e55ecd1bfa955809`
  - `大T_技术总工` → `ou_98710ba6bfeb92022e1acc5ca9c728e9`
- `cc_agent_app` 会把 `大C_内容总监` 解析到自己的 bot open_id：`ou_cc480f343fa33cac128349783edc358c`
- `cc_agent_app` 对跨人协作对象也会命中另一套旧对象：
  - `Hermes_CEO` → `ou_ede550e0a884cef820b59a9f6750509a`
  - `大T_技术总工` → `ou_60d562d442dfc60042362125708d9341`

## 核心证据

## A. Sender env / bot identity 证据
### default_app
来源：`/Users/carson/.hermes/.env`
- `FEISHU_APP_ID=cli_a948f1034ba35cce`
- `FEISHU_BOT_USER_ID=cli_a948f1034ba35cce`
- `FEISHU_BOT_OPEN_ID=ou_726cfff63d194e4aea7345e7ee4fbfc0`
- `FEISHU_BOT_NAME=Hermes_CEO`

### cc_agent_app
来源：`/Users/carson/.hermes/profiles/cc-agent/.env`
- `FEISHU_APP_ID=cli_a8f5ef35f9eb900e`
- `FEISHU_BOT_USER_ID=cli_a8f5ef35f9eb900e`
- `FEISHU_BOT_NAME=大C_内容总监`

历史 session 进一步给出 bot open_id：
- `cli_a8f5ef35f9eb900e` 的 `bot_open_id = ou_cc480f343fa33cac128349783edc358c`
- 证据片段来源：
  - `/Users/carson/.hermes/sessions/session_20260416_104634_fc9933.json`
  - `/Users/carson/.hermes/sessions/session_20260411_164604_5f8fa5.json`

## B. 当前 canonical registry 目标
来源：`middleware/config/feishu_mention_registry.json`
- `Hermes_CEO` → `ou_3320aee078910b0973175037639620ba`
- `大C_内容总监` → `ou_a4542cef2c4c5d95de1ff64eca5d5b5a`
- `大T_技术总工` → `ou_1814da833564decc63d23f857fc5a47d`

## C. sender × target 实测矩阵

| sender | target | expected canonical open_id | actual mention open_id | 结果 |
|---|---|---:|---:|---|
| it_agent_app | Hermes_CEO | `ou_3320aee078910b0973175037639620ba` | `ou_3320aee078910b0973175037639620ba` | PASS |
| it_agent_app | 大C_内容总监 | `ou_a4542cef2c4c5d95de1ff64eca5d5b5a` | `ou_a4542cef2c4c5d95de1ff64eca5d5b5a` | PASS |
| it_agent_app | 大T_技术总工 | `ou_1814da833564decc63d23f857fc5a47d` | `ou_1814da833564decc63d23f857fc5a47d` | PASS |
| default_app | Hermes_CEO | `ou_3320aee078910b0973175037639620ba` | `ou_726cfff63d194e4aea7345e7ee4fbfc0` | FAIL |
| default_app | 大C_内容总监 | `ou_a4542cef2c4c5d95de1ff64eca5d5b5a` | `ou_1b6dd19e4c9acc55e55ecd1bfa955809` | FAIL |
| default_app | 大T_技术总工 | `ou_1814da833564decc63d23f857fc5a47d` | `ou_98710ba6bfeb92022e1acc5ca9c728e9` | FAIL |
| cc_agent_app | Hermes_CEO | `ou_3320aee078910b0973175037639620ba` | `ou_ede550e0a884cef820b59a9f6750509a` | FAIL |
| cc_agent_app | 大C_内容总监 | `ou_a4542cef2c4c5d95de1ff64eca5d5b5a` | `ou_cc480f343fa33cac128349783edc358c` | FAIL |
| cc_agent_app | 大T_技术总工 | `ou_1814da833564decc63d23f857fc5a47d` | `ou_60d562d442dfc60042362125708d9341` | FAIL |

## D. 实测 message_id
### it_agent_app
- `Hermes_CEO`: `om_x100b51a19e57e0a0c34ede9a3e1aa83`
- `大C_内容总监`: `om_x100b51a19e78aca4c4a1b980fcc8625`
- `大T_技术总工`: `om_x100b51a19e1d30a0c4dba99232c0efa`

### default_app
- `Hermes_CEO`: `om_x100b51a19fb008a0c34d03a389cb3ad`
- `大C_内容总监`: `om_x100b51a19f3f44a4c2af48738658d39`
- `大T_技术总工`: `om_x100b51a19cb040a4c34653ad65adb73`

### cc_agent_app
- `Hermes_CEO`: `om_x100b51a19c3ca4acc4eadcdbf38fee7`
- `大C_内容总监`: `om_x100b51a19d4ea0a0c318cb40a4adb60`
- `大T_技术总工`: `om_x100b51a19d37fd30c2b33459181b974`

## 技术判断
### 判断 1：问题出在“全局单一 target 映射”假设不成立
当前 verifier 假设：
- 同一个 target role 只有 1 个全局正确 `open_id`
- 所有 sender app 都能命中同一个 directory object

实测已证明该假设不成立。

### 判断 2：Feishu 目录对象存在 sender-specific 可见/兼容层
至少在当前租户/群/应用组合下，同名角色存在两类对象：
1. canonical 对象（it-agent 当前命中）
2. sender-specific 兼容对象 / bot 对象 / 历史对象（default / cc 当前命中）

### 判断 3：不能简单把 registry 改回旧 open_id
因为：
- 一改回旧 open_id，会让 it-agent 当前健康链路失效
- 不同 sender 实际命中的兼容对象彼此也不一致
- 因此不能用“全局换 target open_id”解决

## 推荐修复方向
### 方案 A（推荐）：registry 升级为 sender-specific compatibility map
为每个 target 增加：
- `canonical_open_id`
- `compatible_open_ids_by_sender`

示意：
```json
{
  "targets": {
    "Hermes_CEO": {
      "display_name": "Hermes_CEO",
      "canonical_open_id": "ou_3320aee078910b0973175037639620ba",
      "compatible_open_ids_by_sender": {
        "it_agent_app": ["ou_3320aee078910b0973175037639620ba"],
        "default_app": ["ou_726cfff63d194e4aea7345e7ee4fbfc0"],
        "cc_agent_app": ["ou_ede550e0a884cef820b59a9f6750509a"]
      }
    }
  }
}
```

同时 verifier 改为：
- 先校验 sender 身份
- 再按 sender 查允许的 mention open_id 列表
- 命中其中之一即算兼容通过
- receipt 中同时输出 `expected_canonical_open_id` 与 `actual_mention_open_id`
- 若 `actual != canonical`，标记 `compat_mode=true`

### 方案 B（更严格但高风险）：逐 sender 重建目录对象一致性
目标是让所有 app sender 都收敛到同一 canonical 对象。

问题：
- 需要更重的飞书目录/群成员/应用配置排查
- 当前缺少直接目录管理权限与稳定文档证据
- 执行成本高，且容易影响在线协作

当前不建议先走 B。

## 验证建议
实施方案 A 后，需要重跑：
1. `default_app` 3 条 smoke
2. `cc_agent_app` 3 条 smoke
3. `it_agent_app` 3 条 smoke

验收字段新增：
- `expected_canonical_open_id`
- `allowed_open_ids_for_sender`
- `actual_mention_open_id`
- `compat_mode`

## 当前建议状态
- `it_agent_app`: healthy
- `default_app`: compat-verified
- `cc_agent_app`: compat-verified

说明：
- `it_agent_app` 当前直接命中 canonical 对象，`canonical_match=true`
- `default_app` / `cc_agent_app` 当前以 sender-specific compatibility allowlist 验收通过，`compat_mode=true`
- 因此二者不再属于 blocked 状态，但仍需持续维护 compatibility map
