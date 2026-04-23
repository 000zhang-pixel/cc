#!/usr/bin/env python3
"""One-line convenience wrapper for formal Feishu messages.

This wrapper exists to reduce the chance of bypassing verified mention send flow.
It delegates to feishu_verified_mention_send.py with safer defaults and short aliases.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
VERIFIED_SENDER = SCRIPT_DIR / "feishu_verified_mention_send.py"

PRESET_SUFFIX = {
    "plain": "{text}",
    "eta": "{text} 预计 15 分钟内回传。",
    "blocked": "{text} 当前存在阻塞，请关注后续【风险】同步。",
    "handoff": "{text} 请接续处理，并在完成后回传【交付】。",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="One-line formal Feishu message wrapper")
    parser.add_argument("label", help="接单/进展/风险/交付/催办/仲裁/结论")
    parser.add_argument("target", help="registry target name, e.g. Hermes_CEO")
    parser.add_argument("text", help="body text after the mention")
    parser.add_argument("--chat", default="hermes_board", help="chat key in registry")
    parser.add_argument("--identity", default="it_agent_app", help="sender identity key in registry")
    parser.add_argument(
        "--preset",
        choices=sorted(PRESET_SUFFIX.keys()),
        default="plain",
        help="append a standard suffix to reduce manual wording variance",
    )
    parser.add_argument("--dry-run", action="store_true", help="delegate to verified sender in dry-run mode")
    return parser.parse_args()


def render_text(text: str, preset: str) -> str:
    normalized = text.strip()
    if not normalized:
        raise ValueError("text cannot be empty")
    return PRESET_SUFFIX[preset].format(text=normalized)


def build_receipt(delegate_stdout: Any, *, label: str, target: str, preset: str, dry_run: bool) -> dict[str, Any] | None:
    if not isinstance(delegate_stdout, dict):
        return None
    mode = delegate_stdout.get("mode")
    if mode == "dry_run":
        chat = delegate_stdout.get("chat") or {}
        sender = delegate_stdout.get("sender_identity") or {}
        runtime_env = delegate_stdout.get("runtime_env") or {}
        target_info = delegate_stdout.get("target") or {}
        return {
            "status": "DRY_RUN_OK",
            "label": label,
            "target": target,
            "preset": preset,
            "dry_run": dry_run,
            "message_id": None,
            "chat_id": chat.get("chat_id"),
            "sender_type": sender.get("sender_type"),
            "sender_id": sender.get("sender_id"),
            "target_open_id": target_info.get("canonical_open_id") or target_info.get("open_id"),
            "target_display_name": target_info.get("display_name"),
            "canonical_open_id": target_info.get("canonical_open_id") or target_info.get("open_id"),
            "allowed_open_ids_for_sender": target_info.get("allowed_open_ids_for_sender") or [],
            "actual_mention_open_id": None,
            "compat_mode": False,
            "mention_verified": False,
            "runtime_env_path": runtime_env.get("active_env_path"),
        }
    if mode in {"send_and_verify", "verify_existing"}:
        checks = delegate_stdout.get("checks") or {}
        expected = delegate_stdout.get("expected") or {}
        runtime_env = delegate_stdout.get("runtime_env") or {}
        return {
            "status": "VERIFIED" if delegate_stdout.get("ok") else "FAILED",
            "label": label,
            "target": target,
            "preset": preset,
            "dry_run": dry_run,
            "message_id": delegate_stdout.get("message_id"),
            "chat_id": delegate_stdout.get("chat_id"),
            "sender_type": delegate_stdout.get("sender_type"),
            "sender_id": delegate_stdout.get("sender_id"),
            "target_open_id": expected.get("target_open_id"),
            "target_display_name": expected.get("target_display_name"),
            "canonical_open_id": expected.get("canonical_open_id") or expected.get("target_open_id"),
            "allowed_open_ids_for_sender": expected.get("allowed_open_ids_for_sender") or [],
            "actual_mention_open_id": delegate_stdout.get("actual_mention_open_id"),
            "compat_mode": bool(delegate_stdout.get("compat_mode")),
            "mention_verified": bool(delegate_stdout.get("ok")),
            "verification_checks": checks,
            "runtime_env_path": runtime_env.get("active_env_path"),
        }
    return None


def main() -> int:
    args = parse_args()
    text = render_text(args.text, args.preset)
    cmd = [
        sys.executable,
        str(VERIFIED_SENDER),
        "--label",
        args.label,
        "--target",
        args.target,
        "--text",
        text,
        "--chat",
        args.chat,
        "--identity",
        args.identity,
    ]
    if args.dry_run:
        cmd.append("--dry-run")

    proc = subprocess.run(cmd, check=False, text=True, capture_output=True)
    payload = {
        "wrapper": str(Path(__file__).name),
        "delegated_command": cmd,
        "exit_code": proc.returncode,
    }
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if stdout:
        try:
            payload["delegate_stdout"] = json.loads(stdout)
        except json.JSONDecodeError:
            payload["delegate_stdout"] = stdout
    if stderr:
        payload["delegate_stderr"] = stderr
    receipt = build_receipt(
        payload.get("delegate_stdout"),
        label=args.label,
        target=args.target,
        preset=args.preset,
        dry_run=args.dry_run,
    )
    if receipt:
        payload["receipt"] = receipt
    stream = sys.stdout if proc.returncode == 0 else sys.stderr
    print(json.dumps(payload, ensure_ascii=False, indent=2), file=stream)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
