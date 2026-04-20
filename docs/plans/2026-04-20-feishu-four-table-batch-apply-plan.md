# Phone-chain Four-table Batch Apply Plan

> **For Hermes:** Use this plan with `scripts/remediate_four_tables.py` and `scripts/data/phone_chain_four_table_remediation.json`.

**Goal:** Turn the audited four-table governance decisions into a repeatable batch apply workflow for Strategy / ShotPlan / Scene / Persona.

**Architecture:** Keep the existing remediation content payloads from `tmp/remediation_report.json`, then layer audited semantic actions (`disable`, `downgrade`, `keep`, `rewrite`, `add`) on top and execute them through the existing `FeishuClient` read/write abstraction. The script is intentionally idempotent: updates target existing records; creates skip when the code already exists.

**Tech Stack:** Python 3.11, `middleware/adapters/feishu.py`, `middleware/core/config.py`, Feishu Bitable.

---

## Objective

Deliver three production-ready artifacts inside the repo:

1. `scripts/data/phone_chain_four_table_remediation.json` — canonical remediation data file
2. `scripts/remediate_four_tables.py` — dry-run/apply executor
3. This document — execution plan and risk notes

---

## Facts

- Existing audit/PRD decisions already exist in:
  - `docs/prd/phone-chain-template-system-remediation-prd-2026-04-20.md`
  - `docs/reviews/2026-04-20-phone-chain-scene-shotplan-audit-list.md`
  - `tmp/phone-chain-scene-shotplan-audit.csv`
- Existing temp remediation payload exists in:
  - `tmp/remediation_report.json`
- Existing export snapshots exist in:
  - `tmp/bitable_exports_2026-04-18/strategy.json`
  - `tmp/bitable_exports_2026-04-18/shotplan.json`
  - `tmp/bitable_exports_2026-04-18/scene.json`
  - `tmp/bitable_exports_2026-04-18/persona.json`
- Existing Feishu access layer already supports:
  - `list_records`
  - `update_record`
  - `create_record`

---

## Execution Mapping

### disable
- Set `是否启用 = 停用`
- Also set numeric ranking to zero where supported:
  - Strategy → `优先级 = 0`
  - Persona → `优先级 = 0`
  - Scene → `权重 = 0`
- Append governance note into `备注`

### downgrade
- Strategy → `优先级 = 20`
- Persona → `优先级 = 40`
- Scene → `权重 = 20`
- ShotPlan currently has **no numeric priority field**; downgrade is encoded in `备注` only

### keep
- Strategy → normalize to `优先级 = 60`
- Persona → normalize to `优先级 = 90`
- Scene → normalize to `权重 = 80`
- ShotPlan keep items remain enabled and are marked in `备注`

### rewrite
- Reuse field rewrites from `tmp/remediation_report.json`
- Includes enum normalization, new governance fields, and content rewrites

### add
- Reuse create payloads from `tmp/remediation_report.json`
- Skip if code already exists

---

## File-level Deliverables

### Task 1: Canonicalize remediation data

**Objective:** Move the temp remediation outputs into a formal repo-tracked JSON plan.

**Files:**
- Create: `scripts/data/phone_chain_four_table_remediation.json`

**Validation:**
- Must contain top-level `summary` and `operations`
- Must include all four tables
- Must explicitly encode `semantic_action`

### Task 2: Create batch executor

**Objective:** Provide one dry-run/apply script for Strategy / ShotPlan / Scene / Persona.

**Files:**
- Create: `scripts/remediate_four_tables.py`

**Requirements:**
- Default to dry-run
- `--apply` required for live writes
- Optional `--tables strategy,shotplan,...`
- Optional `--semantic-actions disable,downgrade,...` for phased rollout
- Create must be idempotent by code lookup
- Update must use `record_id` with code lookup fallback
- Print machine-readable JSON summary

### Task 3: Validate artifacts

**Objective:** Verify plan/data/script consistency before any live write.

**Commands:**
```bash
python3.11 scripts/remediate_four_tables.py --dry-run
python3.11 scripts/remediate_four_tables.py --dry-run --tables strategy,shotplan,scene,persona
```

**Expected:**
- JSON summary emitted
- No duplicate operations by `(table, code)`
- No missing table configuration for selected tables

---

## Recommended Apply Order

1. `disable` — highest risk suppression
2. `downgrade` — reduce residual exposure
3. `rewrite` / `keep` normalization
4. `add` — seed new core templates

Operationally the script preserves the full per-record payload, but rollout should still be reviewed in the above order if executed table-by-table.

### Suggested rollout commands

Phase 0 — dry-run the full package:
```bash
python3.11 scripts/remediate_four_tables.py --dry-run
```

Phase 1 — dry-run only hard suppressions:
```bash
python3.11 scripts/remediate_four_tables.py --dry-run --semantic-actions disable
```

Phase 2 — apply only hard suppressions after manual review:
```bash
python3.11 scripts/remediate_four_tables.py --apply --semantic-actions disable
```

Phase 3 — dry-run medium-risk downweights:
```bash
python3.11 scripts/remediate_four_tables.py --dry-run --semantic-actions downgrade
```

Phase 4 — dry-run structural rewrite/add package:
```bash
python3.11 scripts/remediate_four_tables.py --dry-run --semantic-actions keep,rewrite,add
```

If you want to isolate by table, combine both selectors, for example:
```bash
python3.11 scripts/remediate_four_tables.py --dry-run --tables scene,shotplan --semantic-actions disable,downgrade
```

---

## Known Risks

1. **ShotPlan downgrade is only partially enforceable**
   - Current table schema has no numeric priority field
   - Downgrade is represented in `备注`, not in runtime weighting
   - If runtime-level ShotPlan ranking is required, add a dedicated priority field later

2. **Current payload source had a semantic gap**
   - `tmp/remediation_report.json` did not encode disable decisions directly
   - The formal JSON plan fixes this by layering audit decisions on top

3. **Persona existing rows were under-modeled in temp data**
   - Temp report only created new personas
   - Formal plan now adds explicit update ops for existing persona governance

---

## Apply Commands

Dry run:
```bash
python3.11 scripts/remediate_four_tables.py --dry-run
```

Apply all four tables:
```bash
python3.11 scripts/remediate_four_tables.py --apply
```

Apply selected tables only:
```bash
python3.11 scripts/remediate_four_tables.py --apply --tables strategy,scene
```

---

## Acceptance Criteria

- One repo-tracked JSON plan exists for four-table remediation
- One repo-tracked script can dry-run and apply the plan
- Script output clearly reports processed / skipped / failed counts
- Data file explicitly captures disable / downgrade / rewrite / add semantics
- Persona governance updates are no longer missing from the plan
