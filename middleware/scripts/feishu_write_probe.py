#!/usr/bin/env python3
"""Probe Feishu write capabilities for the current environment.

Focus:
- lark-cli auth/login state
- FeishuClient initialization behavior (including CLI identity fallback)
- no-op record update capability
- attachment duplicate-upload idempotency
- default no-side-effect smoke checks
- optional fresh attachment upload + best-effort cleanup

Examples:
  python3.11 middleware/scripts/feishu_write_probe.py
  python3.11 middleware/scripts/feishu_write_probe.py --attempt-fresh-upload
  python3.11 middleware/scripts/feishu_write_probe.py \
      --content-code T_260418_062_img01 \
      --attachment-file-path /path/to/img_01.jpg
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
MIDDLEWARE_ROOT = REPO_ROOT / "middleware"
ENV_PATH = MIDDLEWARE_ROOT / ".env"

load_dotenv(ENV_PATH, override=False)
sys.path.insert(0, str(MIDDLEWARE_ROOT))
sys.path.insert(0, str(REPO_ROOT))

from core.config import load_system  # noqa: E402
from adapters.feishu import FeishuClient  # noqa: E402


DEFAULT_CONTENT_CODE = "T_260418_062_img01"
DEFAULT_RECORD_ID = "recvhebAJ2BEzn"
DEFAULT_ATTACHMENT_FILE_PATH = (
    REPO_ROOT / "workspace" / "content-store" / "Pending_Content" / "T_260418_062" / "img01" / "img_01.jpg"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe Feishu write capabilities")
    parser.add_argument("--table-key", default="content", help="system.yaml feishu.tables key (default: content)")
    parser.add_argument("--lookup-field", default="内容编号", help="field used to resolve --content-code")
    parser.add_argument("--content-code", default=DEFAULT_CONTENT_CODE, help="record code used when --record-id is absent")
    parser.add_argument("--record-id", default=DEFAULT_RECORD_ID, help="target record_id (default: known safe content record)")
    parser.add_argument("--write-field", default="内容编号", help="field for no-op update probe")
    parser.add_argument("--attachment-field", default="生成图片", help="attachment field to probe")
    parser.add_argument(
        "--attachment-file-path",
        default=str(DEFAULT_ATTACHMENT_FILE_PATH),
        help="local file used for fresh-upload probe; duplicate probe can short-circuit before file access",
    )
    parser.add_argument(
        "--attempt-fresh-upload",
        action="store_true",
        help="attempt a real new attachment upload with best-effort cleanup",
    )
    parser.add_argument(
        "--login-no-wait",
        action="store_true",
        help="also initiate lark-cli device login with --no-wait and include the returned verification URL/device code",
    )
    return parser.parse_args()


def cli_command() -> str:
    return (os.environ.get("LARK_CLI_COMMAND") or "/Users/carson/.npm-global/bin/lark-cli").strip()


def run_cli(*args: str) -> dict[str, Any]:
    cmd = [cli_command(), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    payload: Any = None
    text = (proc.stdout or "").strip()
    if text:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = text
    return {
        "command": cmd,
        "exit_code": proc.returncode,
        "stdout": text,
        "stderr": (proc.stderr or "").strip(),
        "json": payload,
    }


def summarize_cli_auth(initiate_login: bool) -> dict[str, Any]:
    summary = {
        "command": cli_command(),
        "auth_status": run_cli("auth", "status"),
        "auth_list": run_cli("auth", "list"),
        "auth_scopes": run_cli("auth", "scopes"),
    }
    if initiate_login:
        summary["auth_login_no_wait"] = run_cli(
            "auth",
            "login",
            "--json",
            "--no-wait",
            "--domain",
            "base",
            "--domain",
            "drive",
        )
    return summary


def build_client() -> tuple[FeishuClient | None, dict[str, Any]]:
    sys_cfg = load_system()
    feishu_cfg = sys_cfg["feishu"]
    tables = feishu_cfg["tables"]
    meta = {
        "write_backend": os.environ.get("FEISHU_WRITE_BACKEND", "sdk"),
        "requested_cli_identity": os.environ.get("LARK_CLI_IDENTITY", "user"),
        "cli_profile": os.environ.get("LARK_CLI_PROFILE", "ai-content-hub"),
        "tables": tables,
    }
    try:
        client = FeishuClient(
            app_id=feishu_cfg["app_id"],
            app_secret=feishu_cfg["app_secret"],
            base_token=feishu_cfg["base_token"],
        )
        meta.update(
            {
                "effective_cli_identity": getattr(client, "_cli_identity", None),
                "effective_cli_command": getattr(client, "_cli_command", None),
                "initialized": True,
            }
        )
        return client, meta
    except Exception as exc:  # noqa: BLE001
        meta.update({"initialized": False, "init_error": repr(exc)})
        return None, meta


def resolve_target_record(client: FeishuClient, table_id: str, record_id: str | None, content_code: str | None, lookup_field: str) -> dict[str, Any]:
    if record_id:
        record = client.get_record(table_id, record_id)
        return {
            "record_id": record_id,
            "lookup_mode": "record_id",
            "record": record,
        }

    if not content_code:
        raise ValueError("Either --record-id or --content-code must be provided")

    recs = client.list_records(table_id, filter_str=f'CurrentValue.[{lookup_field}] = "{content_code}"')
    if not recs:
        raise RuntimeError(f"Target record not found by {lookup_field}={content_code}")
    if len(recs) > 1:
        raise RuntimeError(f"Target lookup returned {len(recs)} records for {lookup_field}={content_code}")
    return {
        "record_id": recs[0]["record_id"],
        "lookup_mode": "content_code",
        "record": recs[0],
    }


def probe_noop_update(client: FeishuClient, table_id: str, record_id: str, field_name: str, record: dict[str, Any]) -> dict[str, Any]:
    fields = record.get("fields", {})
    if field_name not in fields:
        return {"ok": False, "skipped": True, "reason": f"field {field_name!r} missing on target record"}

    value = fields[field_name]
    started_at = time.time()
    try:
        client.update_record(table_id, record_id, {field_name: value})
        after = client.get_record(table_id, record_id)
        return {
            "ok": True,
            "field": field_name,
            "value_type": type(value).__name__,
            "duration_ms": int((time.time() - started_at) * 1000),
            "verified_equal": after.get("fields", {}).get(field_name) == value,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "field": field_name,
            "duration_ms": int((time.time() - started_at) * 1000),
            "error": repr(exc),
        }


def probe_duplicate_attachment(
    client: FeishuClient,
    table_id: str,
    record_id: str,
    field_name: str,
    record: dict[str, Any],
    file_path: str,
) -> dict[str, Any]:
    attachments = record.get("fields", {}).get(field_name) or []
    if not attachments:
        return {"ok": False, "skipped": True, "reason": f"field {field_name!r} has no existing attachments"}

    existing = next((item for item in attachments if isinstance(item, dict) and item.get("name") and item.get("file_token")), None)
    if not existing:
        return {"ok": False, "skipped": True, "reason": f"field {field_name!r} has no attachment with name+token"}

    duplicate_name = existing["name"]
    before_count = len(attachments)
    started_at = time.time()
    try:
        token = client.upload_attachment(table_id, record_id, field_name, file_path, file_name=duplicate_name)
        after = client.get_record(table_id, record_id)
        after_attachments = after.get("fields", {}).get(field_name) or []
        return {
            "ok": True,
            "duplicate_name": duplicate_name,
            "returned_token": token,
            "expected_token": existing.get("file_token"),
            "duration_ms": int((time.time() - started_at) * 1000),
            "before_count": before_count,
            "after_count": len(after_attachments),
            "count_unchanged": len(after_attachments) == before_count,
            "token_matches_existing": token == existing.get("file_token"),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "duplicate_name": duplicate_name,
            "duration_ms": int((time.time() - started_at) * 1000),
            "error": repr(exc),
        }


def probe_fresh_attachment(
    client: FeishuClient,
    table_id: str,
    record_id: str,
    field_name: str,
    file_path: str,
) -> dict[str, Any]:
    path_obj = Path(file_path)
    if not path_obj.exists():
        return {"ok": False, "skipped": True, "reason": f"attachment file does not exist: {file_path}"}

    before = client.get_record(table_id, record_id)
    before_attachments = before.get("fields", {}).get(field_name) or []
    existing_tokens = {item.get("file_token") for item in before_attachments if isinstance(item, dict)}
    unique_name = f"{path_obj.stem}__probe_{int(time.time())}{path_obj.suffix}"

    started_at = time.time()
    result: dict[str, Any] = {
        "unique_name": unique_name,
        "before_count": len(before_attachments),
        "destructive_probe": True,
        "cleanup_warning": (
            "Attachment cleanup is best-effort only. On this environment, attachment fields may allow append "
            "but reject or ignore normal record update-based replacement, so probe residue may require manual UI cleanup."
        ),
    }
    try:
        token = client.upload_attachment(table_id, record_id, field_name, str(path_obj), file_name=unique_name)
        result.update(
            {
                "returned_token": token,
                "upload_ok": True,
            }
        )
    except Exception as exc:  # noqa: BLE001
        result.update(
            {
                "ok": False,
                "upload_ok": False,
                "duration_ms": int((time.time() - started_at) * 1000),
                "error": repr(exc),
            }
        )
        return result

    after_upload = client.get_record(table_id, record_id)
    after_attachments = after_upload.get("fields", {}).get(field_name) or []
    cleanup_status: dict[str, Any] = {"attempted": False}

    new_attachments = []
    for item in after_attachments:
        if not isinstance(item, dict):
            continue
        token = item.get("file_token")
        name = item.get("name")
        if token not in existing_tokens and name == unique_name:
            continue
        new_attachments.append(item)

    if len(new_attachments) != len(after_attachments):
        cleanup_status = {"attempted": True}
        try:
            client.update_record(table_id, record_id, {field_name: new_attachments})
            post_cleanup = client.get_record(table_id, record_id)
            post_cleanup_attachments = post_cleanup.get("fields", {}).get(field_name) or []
            cleanup_status.update(
                {
                    "ok": True,
                    "after_cleanup_count": len(post_cleanup_attachments),
                    "restored_original_count": len(post_cleanup_attachments) == len(before_attachments),
                }
            )
        except Exception as exc:  # noqa: BLE001
            cleanup_status.update({"ok": False, "error": repr(exc)})

    result.update(
        {
            "ok": True,
            "duration_ms": int((time.time() - started_at) * 1000),
            "after_upload_count": len(after_attachments),
            "count_increased": len(after_attachments) == len(before_attachments) + 1,
            "cleanup": cleanup_status,
        }
    )
    return result


def main() -> int:
    args = parse_args()
    safe_smoke = not args.attempt_fresh_upload
    output: dict[str, Any] = {
        "ts": int(time.time()),
        "repo_root": str(REPO_ROOT),
        "env_path": str(ENV_PATH),
        "probe_mode": "safe_smoke" if safe_smoke else "destructive_probe",
        "safe_smoke": safe_smoke,
        "destructive_probe": not safe_smoke,
        "notes": [
            "Default mode is no-side-effect: auth checks + no-op update + duplicate attachment idempotency.",
            "Fresh attachment upload is opt-in via --attempt-fresh-upload and may leave a probe attachment behind if cleanup is blocked by Feishu/OpenAPI attachment-field semantics.",
        ],
        "inputs": {
            "table_key": args.table_key,
            "lookup_field": args.lookup_field,
            "content_code": args.content_code,
            "record_id": args.record_id,
            "write_field": args.write_field,
            "attachment_field": args.attachment_field,
            "attachment_file_path": args.attachment_file_path,
            "attempt_fresh_upload": args.attempt_fresh_upload,
            "login_no_wait": args.login_no_wait,
        },
    }

    output["cli_auth"] = summarize_cli_auth(initiate_login=args.login_no_wait)

    client, client_meta = build_client()
    output["client"] = client_meta
    if client is None:
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 1

    tables = client_meta["tables"]
    table_id = tables[args.table_key]
    output["target"] = {"table_id": table_id}

    try:
        target = resolve_target_record(client, table_id, args.record_id, args.content_code, args.lookup_field)
        record = target["record"]
        record_id = target["record_id"]
        output["target"].update(
            {
                "record_id": record_id,
                "lookup_mode": target["lookup_mode"],
                "content_code": record.get("fields", {}).get(args.lookup_field),
                "attachment_count": len(record.get("fields", {}).get(args.attachment_field) or []),
            }
        )
    except Exception as exc:  # noqa: BLE001
        output["target_error"] = repr(exc)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 1

    output["probes"] = {
        "noop_update": probe_noop_update(client, table_id, record_id, args.write_field, record),
        "duplicate_attachment": probe_duplicate_attachment(
            client,
            table_id,
            record_id,
            args.attachment_field,
            record,
            args.attachment_file_path,
        ),
    }

    if args.attempt_fresh_upload:
        output["probes"]["fresh_attachment"] = probe_fresh_attachment(
            client,
            table_id,
            record_id,
            args.attachment_field,
            args.attachment_file_path,
        )
    else:
        output["probes"]["fresh_attachment"] = {
            "ok": None,
            "skipped": True,
            "reason": "safe_smoke default: fresh upload probe is disabled unless --attempt-fresh-upload is set",
            "destructive_probe": True,
        }

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
