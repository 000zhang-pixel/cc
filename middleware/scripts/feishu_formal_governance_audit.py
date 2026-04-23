#!/usr/bin/env python3
"""Audit formal-message governance coverage with a dry-run matrix.

This script validates that the wrapper + registry + receipt pipeline is usable
for configured targets without sending real group messages.
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
REGISTRY = REPO_ROOT / "middleware" / "config" / "feishu_mention_registry.json"
DEFAULT_LABELS = ["接单", "进展", "风险", "交付", "催办", "仲裁", "结论"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit Feishu formal-message governance via dry-run matrix")
    parser.add_argument("--labels", nargs="*", default=DEFAULT_LABELS, help="labels to test")
    parser.add_argument("--targets", nargs="*", help="target names in registry; default=all targets")
    parser.add_argument("--text", default="治理审计 dry-run 占位，请忽略。", help="message body used for dry-run")
    parser.add_argument("--chat", default="hermes_board", help="chat key")
    parser.add_argument("--identity", default="it_agent_app", help="sender identity key")
    return parser.parse_args()


def load_registry_targets() -> list[str]:
    raw = json.loads(REGISTRY.read_text(encoding="utf-8"))
    return list((raw.get("targets") or {}).keys())


def run_case(label: str, target: str, text: str, chat: str, identity: str) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(WRAPPER),
        label,
        target,
        text,
        "--chat",
        chat,
        "--identity",
        identity,
        "--dry-run",
    ]
    proc = subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    result: dict[str, Any] = {
        "label": label,
        "target": target,
        "identity": identity,
        "exit_code": proc.returncode,
    }
    if proc.stdout.strip():
        payload = json.loads(proc.stdout)
        receipt = payload.get("receipt") or {}
        result.update(
            {
                "receipt_status": receipt.get("status"),
                "chat_id": receipt.get("chat_id"),
                "sender_id": receipt.get("sender_id"),
                "sender_type": receipt.get("sender_type"),
                "target_open_id": receipt.get("target_open_id"),
                "canonical_open_id": receipt.get("canonical_open_id"),
                "allowed_open_ids_for_sender": receipt.get("allowed_open_ids_for_sender"),
                "target_display_name": receipt.get("target_display_name"),
                "runtime_env_path": receipt.get("runtime_env_path"),
            }
        )
    if proc.stderr.strip():
        result["stderr"] = proc.stderr.strip()
    return result


def main() -> int:
    args = parse_args()
    targets = args.targets or load_registry_targets()
    results = [run_case(label, target, args.text, args.chat, args.identity) for label in args.labels for target in targets]
    failures = [row for row in results if row.get("exit_code") != 0 or row.get("receipt_status") != "DRY_RUN_OK"]
    summary = {
        "total_cases": len(results),
        "labels": args.labels,
        "targets": targets,
        "identity": args.identity,
        "failed_count": len(failures),
        "all_ok": not failures,
        "failures": failures,
        "sample": results[: min(10, len(results))],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())
