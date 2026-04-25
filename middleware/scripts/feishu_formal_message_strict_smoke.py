#!/usr/bin/env python3
"""Strict-hints smoke test for formal message wrapper.

Goals:
- ensure valid rich/standard scenarios still pass with --strict-hints
- ensure annex mismatch / role-placeholder mismatch are blocked with exit 2
- provide machine-readable summary for cron / CI / manual巡检
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
WRAPPER = REPO_ROOT / "middleware" / "scripts" / "feishu_formal_message.py"


CASES: list[dict[str, Any]] = [
    {
        "name": "accept_standard_valid",
        "expect_exit": 0,
        "expect_strict_blocking": False,
        "command": [
            "受理", "大T_技术总工",
            "--format", "interactive",
            "--data", "middleware/templates/feishu_interactive_render_example_accept.json",
            "--identity", "default_app",
            "--chat", "hermes_board",
            "--next-owner", "Hermes_CEO",
            "--strict-hints",
            "--dry-run",
        ],
    },
    {
        "name": "ack_standard_valid",
        "expect_exit": 0,
        "expect_strict_blocking": False,
        "command": [
            "接单", "大T_技术总工",
            "--format", "interactive",
            "--data", "middleware/templates/feishu_interactive_render_example_ack.json",
            "--identity", "default_app",
            "--chat", "hermes_board",
            "--strict-hints",
            "--dry-run",
        ],
    },
    {
        "name": "progress_rich_valid",
        "expect_exit": 0,
        "expect_strict_blocking": False,
        "command": [
            "进展", "大T_技术总工",
            "--format", "interactive",
            "--detail-level", "rich",
            "--data", "middleware/templates/feishu_interactive_render_example_progress_rich_final.json",
            "--identity", "default_app",
            "--chat", "hermes_board",
            "--strict-hints",
            "--dry-run",
        ],
    },
    {
        "name": "delivery_standard_valid",
        "expect_exit": 0,
        "expect_strict_blocking": False,
        "command": [
            "交付", "大T_技术总工",
            "--format", "interactive",
            "--detail-level", "standard",
            "--data", "middleware/templates/feishu_interactive_render_example_delivery.json",
            "--identity", "default_app",
            "--chat", "hermes_board",
            "--next-owner", "Hermes_CEO",
            "--closer", "Hermes_CEO",
            "--strict-hints",
            "--dry-run",
        ],
    },
    {
        "name": "delivery_rich_valid",
        "expect_exit": 0,
        "expect_strict_blocking": False,
        "command": [
            "交付", "大T_技术总工",
            "--format", "interactive",
            "--detail-level", "rich",
            "--data", "middleware/templates/feishu_interactive_render_example_delivery_rich_final.json",
            "--identity", "default_app",
            "--chat", "hermes_board",
            "--next-owner", "Hermes_CEO",
            "--closer", "Hermes_CEO",
            "--strict-hints",
            "--dry-run",
        ],
    },
    {
        "name": "dispatch_rich_valid",
        "expect_exit": 0,
        "expect_strict_blocking": False,
        "command": [
            "派单", "大T_技术总工",
            "--format", "interactive",
            "--detail-level", "rich",
            "--data", "middleware/templates/feishu_interactive_render_example_dispatch_rich.json",
            "--identity", "default_app",
            "--chat", "hermes_board",
            "--collaborator", "大C_内容总监",
            "--closer", "Hermes_CEO",
            "--annex-link", "https://example.com/dispatch-annex",
            "--annex-title", "四表治理执行附录",
            "--annex-summary", "包含字段清单、验收标准、阶段时点与依赖项",
            "--strict-hints",
            "--dry-run",
        ],
    },
    {
        "name": "followup_standard_valid",
        "expect_exit": 0,
        "expect_strict_blocking": False,
        "command": [
            "催办", "大T_技术总工",
            "--format", "interactive",
            "--data", "middleware/templates/feishu_interactive_render_example_followup.json",
            "--identity", "default_app",
            "--chat", "hermes_board",
            "--strict-hints",
            "--dry-run",
        ],
    },
    {
        "name": "conclusion_standard_valid",
        "expect_exit": 0,
        "expect_strict_blocking": False,
        "command": [
            "结论", "Hermes_CEO",
            "--format", "interactive",
            "--detail-level", "standard",
            "--data", "middleware/templates/feishu_interactive_render_example_conclusion.json",
            "--identity", "default_app",
            "--chat", "hermes_board",
            "--closer", "Hermes_CEO",
            "--strict-hints",
            "--dry-run",
        ],
    },
    {
        "name": "dispatch_annex_mismatch_blocked",
        "expect_exit": 2,
        "expect_strict_blocking": True,
        "expected_violation_codes": ["ANNEX_REQUIRES_RICH"],
        "command": [
            "派单", "大T_技术总工",
            "--format", "interactive",
            "--data", "middleware/templates/feishu_interactive_render_example_dispatch_rich.json",
            "--identity", "default_app",
            "--chat", "hermes_board",
            "--annex-link", "https://example.com/dispatch-annex",
            "--strict-hints",
            "--self-check",
        ],
    },
    {
        "name": "progress_role_placeholder_blocked",
        "expect_exit": 2,
        "expect_strict_blocking": True,
        "expected_violation_codes": ["ROLE_PLACEHOLDER_MISSING"],
        "command": [
            "进展", "大T_技术总工",
            "--format", "interactive",
            "--detail-level", "rich",
            "--data", "middleware/templates/feishu_interactive_render_example_progress_rich_final.json",
            "--identity", "default_app",
            "--chat", "hermes_board",
            "--closer", "Hermes_CEO",
            "--strict-hints",
            "--self-check",
        ],
    },
    {
        "name": "accept_business_block_missing",
        "expect_exit": 2,
        "expect_strict_blocking": True,
        "expected_violation_codes": ["BUSINESS_PLACEHOLDERS_MISSING"],
        "command": [
            "受理", "大T_技术总工",
            "--format", "interactive",
            "--detail-level", "standard",
            "--data", '{"title_prefix":"AI-CONTENT-HUB","task_name":"四表治理需求受理","goal":"确认已正式受理并进入下一责任人安排","judgement_1":"本次需求已进入正式治理流程","judgement_2":"当前阶段先锁定范围与责任口径","judgement_3":"下一步转入正式派单执行","status":"已受理","next_milestone":"转入 02 派单"}',
            "--identity", "default_app",
            "--chat", "hermes_board",
            "--strict-hints",
            "--self-check",
        ],
    },
    {
        "name": "dispatch_business_block_missing",
        "expect_exit": 2,
        "expect_strict_blocking": True,
        "expected_violation_codes": ["BUSINESS_PLACEHOLDERS_MISSING"],
        "command": [
            "派单", "大T_技术总工",
            "--format", "interactive",
            "--detail-level", "standard",
            "--data", '{"title_prefix":"AI-CONTENT-HUB","task_name":"四表治理与 Prompt 提升","goal":"今日先产出基础可执行版","deliverable_1":"四张表字段与关系草案","deliverable_2":"Prompt 资产结构与版本规则","deliverable_3":"技术接线建议","progress_deadline":"12:00 前回【04 进展】","delivery_deadline":"17:30 前回【07 交付】","status":"已启动，等待主责拆解","next_milestone":"先完成字段与口径锁定"}',
            "--identity", "default_app",
            "--chat", "hermes_board",
            "--strict-hints",
            "--self-check",
        ],
    },
    {
        "name": "risk_business_block_missing",
        "expect_exit": 2,
        "expect_strict_blocking": True,
        "expected_violation_codes": ["BUSINESS_PLACEHOLDERS_MISSING"],
        "command": [
            "风险", "大T_技术总工",
            "--format", "interactive",
            "--data", '{"title_prefix":"AI-CONTENT-HUB","task_name":"四表治理字段口径确认","goal":"同步当前风险并请求明确决策口径","risk_1":"字段命名和归档口径尚未完全统一","impact_1":"会影响 Prompt 资产表与效果复盘表后续接线","action_suggestion":"先由 CEO 锁定口径，再进入技术实现","status":"待拍板","deadline":"今天 17:00 前","next_milestone":"完成字段口径锁定"}',
            "--identity", "default_app",
            "--chat", "hermes_board",
            "--strict-hints",
            "--self-check",
        ],
    },
    {
        "name": "conclusion_legacy_business_compat_warn_only",
        "expect_exit": 0,
        "expect_strict_blocking": False,
        "command": [
            "结论", "Hermes_CEO",
            "--format", "interactive",
            "--detail-level", "standard",
            "--data", '{"title_prefix":"AI-CONTENT-HUB","task_name":"阶段结论兼容验证","goal":"验证 action_item 兼容层仅告警不阻断","judgement_1":"阶段已形成一致口径","judgement_2":"当前可转入下一阶段","judgement_3":"若需调整再开仲裁","status":"阶段已收口","next_milestone":"进入下一阶段","action_item_1":"按当前阶段结论进入下一阶段执行","action_item_2":"如有阻塞，回【05 风险】","action_item_3":"如需重新分工，由 Hermes_CEO 发【09 仲裁】"}',
            "--identity", "default_app",
            "--chat", "hermes_board",
            "--closer", "Hermes_CEO",
            "--strict-hints",
            "--self-check",
        ],
    },
    {
        "name": "dispatch_legacy_business_compat_warn_only",
        "expect_exit": 0,
        "expect_strict_blocking": False,
        "command": [
            "派单", "大T_技术总工",
            "--format", "interactive",
            "--detail-level", "standard",
            "--data", '{"title_prefix":"AI-CONTENT-HUB","task_name":"旧字段兼容验证","goal":"验证 report_item / guardrail 兼容层仅告警不阻断","deliverable_1":"项1","deliverable_2":"项2","deliverable_3":"项3","progress_deadline":"12:00 前","delivery_deadline":"18:00 前","status":"进行中","next_milestone":"迁移完成","report_item_1":"旧格式回报1","report_item_2":"旧格式回报2","report_item_3":"旧格式回报3","report_item_4":"旧格式回报4","guardrail_1":"旧格式边界1","guardrail_2":"旧格式边界2","guardrail_3":"旧格式边界3"}',
            "--identity", "default_app",
            "--chat", "hermes_board",
            "--strict-hints",
            "--self-check",
        ],
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run strict-hints smoke tests for formal wrapper")
    parser.add_argument("--case", action="append", help="run only named case(s)")
    parser.add_argument("--list", action="store_true", help="list available case names")
    return parser.parse_args()



def parse_payload(stdout: str, stderr: str) -> dict[str, Any] | None:
    for raw in (stdout.strip(), stderr.strip()):
        if not raw:
            continue
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            continue
    return None



def run_case(case: dict[str, Any]) -> dict[str, Any]:
    cmd = [sys.executable, str(WRAPPER), *case["command"]]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    payload = parse_payload(proc.stdout, proc.stderr) or {}
    smart_hints = payload.get("smart_hints") or {}
    violations = smart_hints.get("violations") or []
    violation_codes = [item.get("code") for item in violations if isinstance(item, dict)]
    row = {
        "name": case["name"],
        "exit_code": proc.returncode,
        "expected_exit": case["expect_exit"],
        "strict_blocking": smart_hints.get("strict_blocking"),
        "expected_strict_blocking": case.get("expect_strict_blocking"),
        "violation_codes": violation_codes,
        "expected_violation_codes": case.get("expected_violation_codes", []),
        "command": cmd,
        "payload": payload,
    }
    problems: list[str] = []
    if proc.returncode != case["expect_exit"]:
        problems.append(f"exit_code={proc.returncode} != expected={case['expect_exit']}")
    if smart_hints.get("strict_blocking") != case.get("expect_strict_blocking"):
        problems.append(
            f"strict_blocking={smart_hints.get('strict_blocking')} != expected={case.get('expect_strict_blocking')}"
        )
    expected_codes = case.get("expected_violation_codes", [])
    for code in expected_codes:
        if code not in violation_codes:
            problems.append(f"missing violation code: {code}")
    if case["expect_exit"] == 0:
        receipt = payload.get("receipt") or {}
        if receipt and receipt.get("status") not in {"DRY_RUN_OK", "VERIFIED"}:
            problems.append(f"unexpected receipt status: {receipt.get('status')}")
    row["ok"] = not problems
    row["problems"] = problems
    return row



def main() -> int:
    args = parse_args()
    if args.list:
        print(json.dumps([case["name"] for case in CASES], ensure_ascii=False, indent=2))
        return 0
    selected = CASES
    if args.case:
        wanted = set(args.case)
        selected = [case for case in CASES if case["name"] in wanted]
        missing = sorted(wanted - {case["name"] for case in selected})
        if missing:
            print(json.dumps({"error": "unknown_case", "missing": missing}, ensure_ascii=False, indent=2), file=sys.stderr)
            return 2
    results = [run_case(case) for case in selected]
    failures = [row for row in results if not row["ok"]]
    summary = {
        "script": Path(__file__).name,
        "total_cases": len(results),
        "failed_count": len(failures),
        "all_ok": not failures,
        "results": results,
    }
    stream = sys.stdout if not failures else sys.stderr
    print(json.dumps(summary, ensure_ascii=False, indent=2), file=stream)
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
