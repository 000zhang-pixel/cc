# Feishu CLI Migration and Dual-Run Governance Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Migrate Feishu-facing runtime operations toward `lark-cli` user-authenticated access, while defining deterministic ownership so Windows and mac do not race on the same Feishu-triggered jobs.

**Architecture:** Introduce a Feishu gateway abstraction with separate read/write backends. Short term, move write-critical operations to `lark-cli --as user` because current Base permissions allow user writes but reject bot writes (`91403`). In parallel, add instance ownership/lease fields so only one online middleware instance claims each task.

**Tech Stack:** Python 3.11, existing middleware, `lark-cli`, Feishu Bitable, local SQLite, Syncthing.

---

## Current-state findings

### Feishu auth and write behavior
- `lark-cli` profile `ai-content-hub` is authorized as user `Kenny` and can update Bitable records as `--as user`.
- Current middleware `FeishuClient` uses `lark_oapi` with app credentials only.
- Same record update outcome:
  - SDK/app path: `91403 Forbidden`
  - `lark-cli --as user`: success
- Therefore the immediate blocker is **identity mismatch**, not missing OAuth scopes.

### Current runtime ownership behavior
- `middleware/core/poller.py` scans trigger tables and tries to lock by writing status fields:
  - plan: `执行状态 = 执行中`
  - content migration: `搬迁状态 = 搬迁中`
  - publish: `发布状态 = 发布中`
  - material: `分析状态 = 分析中`
- There is **no cross-machine lease/owner model**.
- If two machines are online, whichever process successfully writes the lock field first effectively claims the task.
- If one machine cannot write status, it will fail to claim and skip the task.

### Windows/mac practical behavior today
- Because mac currently cannot write via SDK/app path, it cannot claim plan/publish/material tasks.
- If Windows middleware is online and its Feishu credentials can write, Windows is the effective runner.
- Publish execution is inherently local-machine bound because `PublishHandler` calls the local publish engine and local ADB environment.

### Nanobanana current state
- Current image adapter points to `NANOBANANA_BASE_URL` and uses Gemini-style generateContent API.
- On this mac:
  - `runapi.co` is reachable but current key returns `401 Invalid token`
  - `api.nanobanana.ai:443` times out
- This confirms network and credential issues must be evaluated separately from Feishu auth.

---

## Decision

### Decision 1: move Feishu writes to CLI first
Why:
- It works today with user auth.
- It avoids reverse-engineering/owning user access token refresh inside Python.
- It aligns with operator ergonomics requested by the user.

### Decision 2: keep a backend abstraction, not hardwire CLI calls everywhere
Why:
- Current codebase has many Feishu touchpoints.
- A single adapter boundary keeps migration incremental and testable.
- It preserves optional future fallback to SDK/app auth.

### Decision 3: add explicit runtime ownership
Why:
- Dual-run without ownership is nondeterministic.
- “Whoever writes first wins” is not sufficient for long-term operations.
- Publish especially needs deterministic machine affinity.

---

## Recommended target design

### A. Feishu gateway split
Create one interface with methods similar to current `FeishuClient`:
- `list_records`
- `get_record`
- `update_record`
- `create_record`
- `delete_record`
- `send_group_text`
- `send_group_card`

Backends:
1. `FeishuSdkBackend` — current `lark_oapi` path
2. `FeishuCliBackend` — invokes `lark-cli`
3. `HybridFeishuBackend` — configurable routing, e.g. reads via SDK, writes via CLI

### B. Ownership / lease model
Add ownership fields to trigger-bearing tables or maintain a dedicated local/remote lease map:
- `执行实例` / `发布实例` / `分析实例`
- `实例心跳时间`
- `锁定时间`
- `锁版本` (optional)

Recommended instance identity format:
- `windows-main`
- `mac-main`

Claim rule:
1. candidate record detected
2. attempt atomic claim by writing owner + in-progress state
3. only continue if post-write readback confirms current owner == self

### C. Machine-role policy
Recommended near-term policy:
- Windows = primary executor for publish + full pipeline
- mac = observer / backup executor / manual remediation runner

Recommended medium-term policy:
- content generation may run on either machine
- publish runs only on machine with active device/ADB binding
- ownership policy encoded in config, not tribal knowledge

---

## Implementation phases

### Phase 1: unblock production-critical writes
**Objective:** restore reliable Bitable writes with minimal code risk.

1. Introduce `FeishuCliBackend` for `update_record` and `create_record` only.
2. Keep existing SDK reads untouched.
3. Route all poller lock writes and handler status writes through CLI backend.
4. Add structured logging for every CLI write call:
   - table
   - record_id
   - fields
   - identity used
   - exit code
5. Verify:
   - plan claim works
   - publish claim works
   - failure/success status writes work

### Phase 2: abstract all Feishu access behind gateway
**Objective:** remove direct backend coupling from handlers.

1. Create `middleware/adapters/feishu_gateway.py`
2. Move current SDK client into `feishu_sdk_backend.py`
3. Add `feishu_cli_backend.py`
4. Replace direct instantiation in `main.py` with backend factory from config.
5. Add config switches:
   - `feishu.backend.read = sdk|cli`
   - `feishu.backend.write = sdk|cli`
   - `feishu.cli.profile = ai-content-hub`

### Phase 3: dual-run governance
**Objective:** deterministic task ownership across Windows and mac.

1. Add machine identity config:
   - `runtime.instance_id`
   - `runtime.capabilities.publish = true|false`
   - `runtime.capabilities.generate = true|false`
2. Add claim metadata fields or equivalent lease storage.
3. Modify poller claim flow to confirm ownership after write.
4. For publish tasks, only machines with `publish=true` may claim.
5. For generation tasks, policy can be `primary-only` initially.

### Phase 4: CLI-first ops tooling
**Objective:** make routine operations easier for humans.

1. Add admin scripts using `lark-cli` for:
   - check plan
   - reset plan
   - replay publish
   - inspect locks
2. Document auth refresh / health check runbook.
3. Add startup doctor check to fail fast if CLI user auth is invalid.

---

## File-level change map

### New files
- `middleware/adapters/feishu_cli_backend.py`
- `middleware/adapters/feishu_sdk_backend.py`
- `middleware/adapters/feishu_gateway.py`
- `docs/runbooks/feishu-cli-auth-and-runtime.md`

### Modify
- `middleware/adapters/feishu.py` (either convert into gateway facade or retire)
- `middleware/main.py`
- `middleware/core/config.py`
- `middleware/config/system.yaml`
- `middleware/core/poller.py`
- `middleware/handlers/content_generation.py`
- `middleware/handlers/publish.py`
- `middleware/handlers/material_analysis.py`
- `middleware/handlers/material_migration.py`
- `middleware/handlers/publish_record_creator.py`

### Optional follow-up
- `scripts/check_plan.py`
- `scripts/reset_plan.py`
- `scripts/remediate_tables.py`

---

## Acceptance criteria

### Feishu CLI migration
- Poller can claim a plan on the current mac using CLI-backed write path.
- Handler can mark plan/content/publish/material records success/failure using CLI path.
- Middleware startup clearly reports which backend is used for reads and writes.
- If CLI auth is invalid, startup fails with explicit remediation instructions.

### Dual-run governance
- With Windows and mac both online, the same Feishu trigger is processed by one instance only.
- Claimed records show owning instance.
- Publish tasks are only executed by publish-capable machine.
- Logs make winner/loser claim attempts obvious.

### Nanobanana observability
- Health check distinguishes:
  - DNS/TCP/connectivity failure
  - auth failure (`401`)
  - API response format failure
- Runtime logs show which base URL and model were used.

---

## Validation plan

### CLI write validation
- `lark-cli auth status --profile ai-content-hub`
- one safe `base +record-upsert --as user`
- middleware dry run of poller claim on one test record

### Dual-run validation
1. Start Windows and mac middleware simultaneously.
2. Create one plan trigger from Feishu/mobile.
3. Confirm exactly one instance writes in-progress state.
4. Confirm losing instance logs claim rejection and does not execute downstream steps.

### Publish validation
1. Create one publish-ready record.
2. Confirm only publish-capable instance claims it.
3. Confirm local publish engine path belongs to claiming host.

---

## Risks

### Operational risks
- `lark-cli` process spawning is slower than in-process SDK calls.
- CLI JSON shape/version changes can break parsers.
- User auth introduces dependency on operator session validity.

### Mitigations
- Start with writes only, keep reads on SDK.
- Parse CLI output defensively and pin CLI version where possible.
- Add startup health check and runbook.

### Non-goals for first pass
- Full replacement of all SDK reads.
- Cross-machine distributed scheduler.
- Automatic token export from CLI into Python SDK.

---

## Recommended immediate next move

1. Implement **Phase 1 only**: CLI-backed writes, SDK-backed reads.
2. After write path is stable, implement ownership fields and claim confirmation.
3. Then run a real dual-machine test from mobile-created Feishu task.
