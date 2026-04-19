"""
Feishu Bitable read/write client for the middleware.
Reads stay on lark-oapi SDK. Writes can optionally route through lark-cli user auth.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from typing import Any

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
)
from lark_oapi.api.bitable.v1 import (
    ListAppTableRecordRequest,
    GetAppTableRecordRequest,
    UpdateAppTableRecordRequest,
    CreateAppTableRecordRequest,
    DeleteAppTableRecordRequest,
    AppTableRecord,
)
from lark_oapi.api.drive.v1 import DownloadMediaRequest

logger = logging.getLogger(__name__)


class FeishuClient:
    def __init__(self, app_id: str, app_secret: str, base_token: str):
        self.base_token = base_token
        self._client = lark.Client.builder() \
            .app_id(app_id) \
            .app_secret(app_secret) \
            .log_level(lark.LogLevel.WARNING) \
            .timeout(30) \
            .build()

        self._write_backend = (os.environ.get("FEISHU_WRITE_BACKEND", "sdk") or "sdk").strip().lower()
        self._cli_profile = (os.environ.get("LARK_CLI_PROFILE", "ai-content-hub") or "ai-content-hub").strip()
        self._cli_identity = (os.environ.get("LARK_CLI_IDENTITY", "user") or "user").strip()
        self._cli_command = self._resolve_cli_command(os.environ.get("LARK_CLI_COMMAND"))

        if self._write_backend not in {"sdk", "cli"}:
            raise RuntimeError(
                f"Unsupported FEISHU_WRITE_BACKEND={self._write_backend!r}; expected 'sdk' or 'cli'"
            )

        if self._write_backend == "cli":
            self._verify_cli_auth()

        logger.info(
            "Feishu client initialized (read_backend=sdk, write_backend=%s%s)",
            self._write_backend,
            f", cli_profile={self._cli_profile}, cli_identity={self._cli_identity}" if self._write_backend == "cli" else "",
        )

    @staticmethod
    def _resolve_cli_command(configured: str | None) -> str | None:
        candidate = (configured or "").strip()
        if candidate:
            return candidate
        for name in ("lark-cli", "lark-cli.cmd"):
            resolved = shutil.which(name)
            if resolved:
                return resolved
        return None

    def _verify_cli_auth(self) -> None:
        if not self._cli_command:
            raise RuntimeError(
                "FEISHU_WRITE_BACKEND=cli but lark-cli was not found in PATH. "
                "Set LARK_CLI_COMMAND explicitly or install lark-cli."
            )
        proc = subprocess.run(
            [self._cli_command, "auth", "status", "--profile", self._cli_profile, "--verify"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                "lark-cli auth verification failed: "
                f"exit_code={proc.returncode}, stderr={proc.stderr.strip() or proc.stdout.strip()}"
            )
        payload = self._parse_cli_json(proc.stdout, action="auth-status")
        token_status = payload.get("tokenStatus")
        verified = payload.get("verified")
        if token_status != "valid" or verified is not True:
            raise RuntimeError(
                "lark-cli auth is not valid/verified: "
                f"tokenStatus={token_status!r}, verified={verified!r}, profile={self._cli_profile}"
            )

    @staticmethod
    def _parse_cli_json(stdout: str, action: str) -> dict:
        text = (stdout or "").strip()
        if not text:
            raise RuntimeError(f"lark-cli {action} returned empty stdout")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"lark-cli {action} returned non-JSON output: {text[:500]}") from exc

    def _run_cli_bitable_write(self, *, table_id: str, record_id: str | None, fields: dict) -> dict:
        if not self._cli_command:
            raise RuntimeError("lark-cli command is unavailable")
        cmd = [
            self._cli_command,
            "base",
            "+record-upsert",
            "--profile",
            self._cli_profile,
            "--as",
            self._cli_identity,
            "--base-token",
            self.base_token,
            "--table-id",
            table_id,
            "--json",
            json.dumps(fields, ensure_ascii=False),
        ]
        if record_id:
            cmd.extend(["--record-id", record_id])
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        logger.info(
            "Feishu CLI write: table=%s record=%s fields=%s identity=%s profile=%s exit_code=%s",
            table_id,
            record_id,
            sorted(fields.keys()),
            self._cli_identity,
            self._cli_profile,
            proc.returncode,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                "lark-cli write failed: "
                f"table={table_id}, record={record_id}, exit_code={proc.returncode}, "
                f"stderr={proc.stderr.strip() or proc.stdout.strip()}"
            )

        payload = self._parse_cli_json(proc.stdout, action="base +record-upsert")
        if payload.get("code") not in (None, 0):
            raise RuntimeError(
                "Feishu OpenAPI write failed: "
                f"code={payload.get('code')}, msg={payload.get('msg')}, table={table_id}, record={record_id}"
            )
        if payload.get("ok") is False:
            raise RuntimeError(
                "lark-cli write returned ok=false: "
                f"table={table_id}, record={record_id}, response={json.dumps(payload, ensure_ascii=False)[:500]}"
            )
        return payload

    def list_records(
        self,
        table_id: str,
        filter_str: str | None = None,
        page_size: int = 100,
    ) -> list[dict]:
        """Return all records from a table, auto-paginating. Each item is {record_id, fields}."""
        records = []
        page_token = None

        while True:
            req_builder = (
                ListAppTableRecordRequest.builder()
                .app_token(self.base_token)
                .table_id(table_id)
                .page_size(page_size)
            )
            if filter_str:
                req_builder = req_builder.filter(filter_str)
            if page_token:
                req_builder = req_builder.page_token(page_token)

            resp = self._client.bitable.v1.app_table_record.list(req_builder.build())
            if not resp.success():
                raise RuntimeError(
                    f"list_records failed [{resp.code}]: {resp.msg} "
                    f"(table={table_id})"
                )

            items = resp.data.items or []
            for item in items:
                records.append({"record_id": item.record_id, "fields": item.fields or {}})

            if not resp.data.has_more:
                break
            page_token = resp.data.page_token

        return records

    def get_record(self, table_id: str, record_id: str) -> dict:
        """Return a single record as {record_id, fields}."""
        resp = self._client.bitable.v1.app_table_record.get(
            GetAppTableRecordRequest.builder()
            .app_token(self.base_token)
            .table_id(table_id)
            .record_id(record_id)
            .build()
        )
        if not resp.success():
            raise RuntimeError(
                f"get_record failed [{resp.code}]: {resp.msg} "
                f"(table={table_id}, record={record_id})"
            )
        return {"record_id": resp.data.record.record_id, "fields": resp.data.record.fields or {}}

    def update_record(self, table_id: str, record_id: str, fields: dict) -> None:
        """Update specific fields on an existing record."""
        if self._write_backend == "cli":
            self._run_cli_bitable_write(
                table_id=table_id,
                record_id=record_id,
                fields=fields,
            )
            return

        record = AppTableRecord.builder().fields(fields).build()
        resp = self._client.bitable.v1.app_table_record.update(
            UpdateAppTableRecordRequest.builder()
            .app_token(self.base_token)
            .table_id(table_id)
            .record_id(record_id)
            .request_body(record)
            .build()
        )
        if not resp.success():
            raise RuntimeError(
                f"update_record failed [{resp.code}]: {resp.msg} "
                f"(table={table_id}, record={record_id}, fields={list(fields.keys())})"
            )

    def _infer_created_record_id(self, table_id: str, fields: dict, payload: dict) -> str | None:
        data = payload.get("data") or {}
        record = data.get("record") or {}
        for candidate in (
            record.get("record_id"),
            record.get("id"),
            data.get("record_id"),
            data.get("id"),
        ):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()

        unique_lookup_fields = [
            "内容编号",
            "提示词编号",
            "发布编号",
            "规划编号",
            "素材编号",
            "SKU编号",
        ]
        for field_name in unique_lookup_fields:
            value = fields.get(field_name)
            if not isinstance(value, str) or not value.strip():
                continue
            escaped = value.replace('\\', '\\\\').replace('"', '\\"')
            try:
                matches = self.list_records(
                    table_id,
                    filter_str=f'CurrentValue.[{field_name}] = "{escaped}"',
                )
            except Exception:
                logger.warning(
                    "Feishu create_record fallback lookup failed: table=%s field=%s value=%r",
                    table_id,
                    field_name,
                    value,
                    exc_info=True,
                )
                continue
            if len(matches) == 1:
                return matches[0]["record_id"]
            if len(matches) > 1:
                raise RuntimeError(
                    "Feishu create_record fallback lookup was ambiguous: "
                    f"table={table_id}, field={field_name}, value={value!r}, matches={len(matches)}"
                )
        return None

    def create_record(self, table_id: str, fields: dict) -> str:
        """Create a new record and return its record_id."""
        if self._write_backend == "cli":
            payload = self._run_cli_bitable_write(
                table_id=table_id,
                record_id=None,
                fields=fields,
            )
            record_id = self._infer_created_record_id(table_id, fields, payload)
            if not record_id:
                raise RuntimeError(
                    "Feishu create_record via CLI succeeded but response had no record_id and fallback lookup failed: "
                    f"table={table_id}, response={json.dumps(payload, ensure_ascii=False)[:500]}"
                )
            return record_id

        record = AppTableRecord.builder().fields(fields).build()
        resp = self._client.bitable.v1.app_table_record.create(
            CreateAppTableRecordRequest.builder()
            .app_token(self.base_token)
            .table_id(table_id)
            .request_body(record)
            .build()
        )
        if not resp.success():
            raise RuntimeError(
                f"create_record failed [{resp.code}]: {resp.msg} "
                f"(table={table_id}, fields={list(fields.keys())})"
            )
        return resp.data.record.record_id

    def delete_record(self, table_id: str, record_id: str) -> None:
        """Delete a record by record_id."""
        resp = self._client.bitable.v1.app_table_record.delete(
            DeleteAppTableRecordRequest.builder()
            .app_token(self.base_token)
            .table_id(table_id)
            .record_id(record_id)
            .build()
        )
        if not resp.success():
            raise RuntimeError(
                f"delete_record failed [{resp.code}]: {resp.msg} "
                f"(table={table_id}, record={record_id})"
            )

    # --- Convenience helpers ---

    def get_field(self, record: dict, field: str, default=None):
        """Safely extract a field value from a record dict."""
        return record.get("fields", {}).get(field, default)

    def get_text(self, record: dict, field: str, default: str = "") -> str:
        """Extract plain text (handles Feishu rich-text list format)."""
        val = self.get_field(record, field)
        if val is None:
            return default
        if isinstance(val, list):
            # Rich-text format: [{type, text}, ...]
            return "".join(seg.get("text", "") for seg in val if isinstance(seg, dict))
        return str(val)

    def get_option(self, record: dict, field: str, default: str = "") -> str:
        """Extract single-select option value."""
        val = self.get_field(record, field)
        if val is None:
            return default
        if isinstance(val, dict):
            return val.get("text", default)
        return str(val)

    def get_options(self, record: dict, field: str) -> list[str]:
        """Extract multi-select option values as a list of strings."""
        val = self.get_field(record, field)
        if not val:
            return []
        if isinstance(val, list):
            return [v.get("text", "") if isinstance(v, dict) else str(v) for v in val]
        return []

    def get_link_ids(self, record: dict, field: str) -> list[str]:
        """Extract linked record IDs from a link field.

        Feishu returns link fields as a list of objects:
        [{"record_ids": ["recXXX"], "table_id": "tbl...", "text": "...", ...}]
        """
        val = self.get_field(record, field)
        if not val:
            return []
        if isinstance(val, list):
            ids = []
            for item in val:
                if isinstance(item, dict):
                    # Each item has record_ids (plural) key
                    item_ids = item.get("record_ids", [])
                    ids.extend(item_ids)
                elif isinstance(item, str):
                    ids.append(item)
            return [i for i in ids if i]
        if isinstance(val, dict):
            return val.get("record_ids", [])
        return []

    def get_number(self, record: dict, field: str, default: float = 0) -> float:
        """Extract a numeric field value."""
        val = self.get_field(record, field)
        if val is None:
            return default
        try:
            return float(val)
        except (TypeError, ValueError):
            return default

    def download_media(self, file_token: str) -> bytes:
        """Download a Bitable attachment by its file_token. Returns raw bytes."""
        resp = self._client.drive.v1.media.download(
            DownloadMediaRequest.builder()
            .file_token(file_token)
            .build()
        )
        if not resp.success():
            raise RuntimeError(
                f"download_media failed [{resp.code}]: {resp.msg} "
                f"(file_token={file_token})"
            )
        return resp.file.read()

    def send_group_text(self, chat_id: str, text: str) -> None:
        """Send a plain-text message to a Feishu group chat.

        Fails silently (logs warning) so notification errors never block the main flow.
        """
        try:
            body = CreateMessageRequestBody.builder() \
                .receive_id(chat_id) \
                .msg_type("text") \
                .content(json.dumps({"text": text})) \
                .build()
            resp = self._client.im.v1.message.create(
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(body)
                .build()
            )
            if not resp.success():
                logger.warning(
                    "send_group_text failed [%s]: %s (chat_id=%s)",
                    resp.code, resp.msg, chat_id
                )
        except Exception as exc:
            logger.warning("send_group_text exception: %s", exc)

    def send_group_card(self, chat_id: str, card: dict) -> None:
        """Send an interactive card message to a Feishu group chat.

        Args:
            chat_id: Feishu group chat_id
            card: Card JSON dict (will be wrapped in {"config": {...}, "elements": [...]})

        Fails silently (logs warning) so notification errors never block the main flow.
        """
        try:
            body = CreateMessageRequestBody.builder() \
                .receive_id(chat_id) \
                .msg_type("interactive") \
                .content(json.dumps(card)) \
                .build()
            resp = self._client.im.v1.message.create(
                CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(body)
                .build()
            )
            if not resp.success():
                logger.warning(
                    "send_group_card failed [%s]: %s (chat_id=%s)",
                    resp.code, resp.msg, chat_id
                )
        except Exception as exc:
            logger.warning("send_group_card exception: %s", exc)
