"""
Feishu Bitable read/write client for the middleware.
Reads stay on lark-oapi SDK. Writes can optionally route through lark-cli user auth.
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import lark_oapi as lark
import requests
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
    ListAppTableFieldRequest,
    AppTableRecord,
)
from lark_oapi.api.drive.v1 import DownloadMediaRequest, UploadAllMediaRequest, UploadAllMediaRequestBody

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
        self._cli_identity = (os.environ.get("LARK_CLI_IDENTITY", "user") or "user").strip().lower()
        self._cli_command = self._resolve_cli_command(os.environ.get("LARK_CLI_COMMAND"))
        self._field_id_cache: dict[tuple[str, str], str] = {}

        if self._write_backend not in {"sdk", "cli"}:
            raise RuntimeError(
                f"Unsupported FEISHU_WRITE_BACKEND={self._write_backend!r}; expected 'sdk' or 'cli'"
            )

        if self._write_backend == "cli":
            self._verify_cli_auth()
            if self._cli_profile:
                logger.info(
                    "LARK_CLI_PROFILE=%s is informational only for current lark-cli integration; commands run without --profile",
                    self._cli_profile,
                )

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
            [self._cli_command, "auth", "status"],
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
        identity = (payload.get("identity") or "").strip().lower()
        has_cli_identity = bool(identity) and bool(payload.get("appId"))
        default_as = (payload.get("defaultAs") or "").strip().lower()

        # Newer lark-cli builds may omit tokenStatus entirely when only bot identity
        # is available. Treat a successful `auth status` response with a usable
        # identity/appId as configured.
        if token_status in ("valid", "expired") or has_cli_identity:
            available_identities = {x for x in (identity, default_as) if x and x != "auto"}
            if self._cli_identity and self._cli_identity not in available_identities:
                fallback_identity = identity or (default_as if default_as != "auto" else "")
                if fallback_identity:
                    logger.warning(
                        "Requested LARK_CLI_IDENTITY=%s is unavailable; falling back to %s",
                        self._cli_identity,
                        fallback_identity,
                    )
                    self._cli_identity = fallback_identity
            return

        raise RuntimeError(
            "lark-cli auth is not configured: "
            f"tokenStatus={token_status!r}, identity={identity!r}, profile={self._cli_profile}"
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

    @staticmethod
    def _cli_error_allows_sdk_fallback(message: str) -> bool:
        normalized = (message or "").lower()
        return any(token in normalized for token in (
            "http 403",
            "permission",
            "you don't have permission",
            "you do not have permission",
            '"identity": "bot"',
        ))

    @staticmethod
    def _sdk_read_error_allows_cli_fallback(exc: Exception) -> bool:
        if isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
            return True
        normalized = str(exc).lower()
        return any(token in normalized for token in (
            "read timed out",
            "connection aborted",
            "connection reset",
            "temporarily unavailable",
        ))

    def _run_cli_bitable_write(self, *, table_id: str, record_id: str | None, fields: dict) -> dict:
        if not self._cli_command:
            raise RuntimeError("lark-cli command is unavailable")
        cmd = [
            self._cli_command,
            "base",
            "+record-upsert",
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

    def _run_cli_base_command(self, subcommand: str, *, table_id: str, extra_args: list[str] | None = None) -> dict:
        if not self._cli_command:
            raise RuntimeError("lark-cli command is unavailable")
        cmd = [
            self._cli_command,
            "base",
            subcommand,
            "--as",
            self._cli_identity,
            "--base-token",
            self.base_token,
            "--table-id",
            table_id,
        ]
        if extra_args:
            cmd.extend(extra_args)
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        logger.info(
            "Feishu CLI base command: subcommand=%s table=%s identity=%s profile=%s exit_code=%s",
            subcommand,
            table_id,
            self._cli_identity,
            self._cli_profile,
            proc.returncode,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                "lark-cli base command failed: "
                f"subcommand={subcommand}, table={table_id}, exit_code={proc.returncode}, "
                f"stderr={proc.stderr.strip() or proc.stdout.strip()}"
            )
        payload = self._parse_cli_json(proc.stdout, action=f"base {subcommand}")
        if payload.get("ok") is False:
            error = payload.get("error") or {}
            raise RuntimeError(
                "lark-cli base command returned ok=false: "
                f"subcommand={subcommand}, table={table_id}, error={json.dumps(error, ensure_ascii=False)[:500]}"
            )
        return payload

    @staticmethod
    def _parse_simple_filter(filter_str: str | None) -> tuple[str, str] | None:
        if not filter_str:
            return None
        match = re.fullmatch(r'CurrentValue\.\[(.+?)\]\s*=\s*"((?:\\.|[^"])*)"', filter_str.strip())
        if not match:
            return None
        field_name = match.group(1)
        raw_value = match.group(2)
        value = bytes(raw_value, "utf-8").decode("unicode_escape")
        return field_name, value

    @staticmethod
    def _cli_row_to_record(fields: list[str], row: list[Any], record_id: str) -> dict:
        mapped_fields = {field_name: row[idx] if idx < len(row) else None for idx, field_name in enumerate(fields)}
        return {"record_id": record_id, "fields": mapped_fields}

    def _cli_record_matches_filter(self, record: dict, filter_str: str | None) -> bool:
        parsed = self._parse_simple_filter(filter_str)
        if not filter_str:
            return True
        if not parsed:
            raise RuntimeError(f"Unsupported CLI filter syntax: {filter_str!r}")
        field_name, expected = parsed
        actual = record.get("fields", {}).get(field_name)
        if isinstance(actual, list):
            if all(isinstance(item, str) for item in actual):
                return expected in actual
            return False
        if actual is None:
            return expected == ""
        return str(actual) == expected

    def get_field_id(self, table_id: str, field_name: str) -> str:
        cache_key = (table_id, field_name)
        cached = self._field_id_cache.get(cache_key)
        if cached:
            return cached

        if self._write_backend == "cli" and self._cli_command:
            offset = 0
            while True:
                payload = self._run_cli_base_command(
                    "+field-list",
                    table_id=table_id,
                    extra_args=["--limit", "100", "--offset", str(offset)],
                )
                data = payload.get("data") or {}
                items = data.get("fields") or []
                for item in items:
                    if item.get("name") == field_name and item.get("id"):
                        self._field_id_cache[cache_key] = item["id"]
                        return item["id"]
                if not data.get("has_more"):
                    break
                offset += len(items)
            raise RuntimeError(f"field not found: table={table_id}, field={field_name}")

        try:
            resp = self._client.bitable.v1.app_table_field.list(
                ListAppTableFieldRequest.builder()
                .app_token(self.base_token)
                .table_id(table_id)
                .page_size(500)
                .build()
            )
        except Exception as exc:
            if self._cli_command and self._sdk_read_error_allows_cli_fallback(exc):
                logger.warning(
                    "Falling back to CLI get_field_id after SDK read failure: table=%s field=%s error=%s",
                    table_id,
                    field_name,
                    exc,
                )
                offset = 0
                while True:
                    payload = self._run_cli_base_command(
                        "+field-list",
                        table_id=table_id,
                        extra_args=["--limit", "100", "--offset", str(offset)],
                    )
                    data = payload.get("data") or {}
                    items = data.get("fields") or []
                    for item in items:
                        if item.get("name") == field_name and item.get("id"):
                            self._field_id_cache[cache_key] = item["id"]
                            return item["id"]
                    if not data.get("has_more"):
                        break
                    offset += len(items)
                raise RuntimeError(f"field not found: table={table_id}, field={field_name}")
            raise
        if not resp.success():
            raise RuntimeError(
                f"list_fields failed [{resp.code}]: {resp.msg} (table={table_id})"
            )

        items = resp.data.items or []
        for item in items:
            if item.field_name == field_name:
                self._field_id_cache[cache_key] = item.field_id
                return item.field_id
        raise RuntimeError(f"field not found: table={table_id}, field={field_name}")

    def upload_attachment(self, table_id: str, record_id: str, field_name: str, file_path: str, *, file_name: str | None = None) -> str:
        path_obj = Path(file_path)
        fname = file_name or path_obj.name

        existing_attachment = self._find_existing_attachment(table_id, record_id, field_name, fname)
        if existing_attachment:
            file_token = existing_attachment.get("file_token")
            logger.info(
                "Feishu attachment already exists, skipping duplicate upload: table=%s record=%s field=%s file=%s token=%s",
                table_id,
                record_id,
                field_name,
                fname,
                file_token,
            )
            return file_token

        if self._write_backend == "cli" and self._cli_command:
            try:
                return self._upload_attachment_cli(table_id, record_id, field_name, path_obj, fname)
            except RuntimeError as exc:
                if not self._cli_error_allows_sdk_fallback(str(exc)):
                    raise
                logger.warning(
                    "Falling back to SDK attachment upload after CLI failure: table=%s record=%s field=%s error=%s",
                    table_id,
                    record_id,
                    field_name,
                    exc,
                )
        return self._upload_attachment_sdk(table_id, record_id, field_name, path_obj, fname)

    def _get_existing_attachments(self, table_id: str, record_id: str, field_name: str) -> list[dict]:
        record = self.get_record(table_id, record_id)
        raw = record.get("fields", {}).get(field_name, [])
        if not isinstance(raw, list):
            return []
        return [item for item in raw if isinstance(item, dict) and item.get("file_token")]

    def _find_existing_attachment(self, table_id: str, record_id: str, field_name: str, file_name: str) -> dict | None:
        normalized = (file_name or "").strip()
        if not normalized:
            return None
        for attachment in self._get_existing_attachments(table_id, record_id, field_name):
            if (attachment.get("name") or "").strip() == normalized:
                return attachment
        return None

    def _upload_attachment_sdk(self, table_id: str, record_id: str, field_name: str, path_obj: Path, file_name: str) -> str:
        file_bytes = path_obj.read_bytes()
        req = (
            UploadAllMediaRequest.builder()
            .request_body(
                UploadAllMediaRequestBody.builder()
                .file_name(file_name)
                .parent_type("bitable_file")
                .parent_node(self.base_token)
                .size(len(file_bytes))
                .file(io.BytesIO(file_bytes))
                .build()
            )
            .build()
        )
        resp = self._client.drive.v1.media.upload_all(req)
        if not resp.success():
            raise RuntimeError(
                f"SDK media upload failed [{resp.code}]: {resp.msg} (file={file_name})"
            )
        file_token = resp.data.file_token
        logger.debug("SDK uploaded %s → file_token=%s", file_name, file_token)

        # Append token to existing attachment field (don't overwrite). If the
        # record cannot be read here, fail closed rather than risking an update
        # that overwrites pre-existing attachments.
        existing_attachments = self._get_existing_attachments(table_id, record_id, field_name)

        new_attachments = existing_attachments + [{"file_token": file_token, "name": file_name}]
        update_req = (
            UpdateAppTableRecordRequest.builder()
            .app_token(self.base_token)
            .table_id(table_id)
            .record_id(record_id)
            .request_body(
                AppTableRecord.builder()
                .fields({field_name: new_attachments})
                .build()
            )
            .build()
        )
        update_resp = self._client.bitable.v1.app_table_record.update(update_req)
        if not update_resp.success():
            raise RuntimeError(
                f"SDK record update for attachment failed [{update_resp.code}]: {update_resp.msg}"
            )
        return file_token

    def _upload_attachment_cli(self, table_id: str, record_id: str, field_name: str, path_obj: Path, file_name: str) -> str:
        field_id = self.get_field_id(table_id, field_name)
        cmd = [
            self._cli_command,
            "base",
            "+record-upload-attachment",
            "--as",
            self._cli_identity,
            "--base-token",
            self.base_token,
            "--table-id",
            table_id,
            "--record-id",
            record_id,
            "--field-id",
            field_id,
            "--file",
            f"./{path_obj.name}",
            "--name",
            file_name,
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            cwd=str(path_obj.parent),
        )
        logger.info(
            "Feishu CLI attachment upload: table=%s record=%s field=%s exit_code=%s",
            table_id, record_id, field_name, proc.returncode,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                "lark-cli attachment upload failed: "
                f"table={table_id}, record={record_id}, field={field_name}, exit_code={proc.returncode}, "
                f"stderr={proc.stderr.strip() or proc.stdout.strip()}"
            )
        payload = self._parse_cli_json(proc.stdout, action="base +record-upload-attachment")
        if payload.get("ok") is False:
            raise RuntimeError(
                f"lark-cli attachment upload ok=false: {json.dumps(payload, ensure_ascii=False)[:500]}"
            )
        attachment = (payload.get("data") or {}).get("attachment") or {}
        file_token = attachment.get("file_token")
        if not file_token:
            raise RuntimeError(f"lark-cli attachment upload: no file_token in response")
        return file_token

    def list_records(
        self,
        table_id: str,
        filter_str: str | None = None,
        page_size: int = 100,
    ) -> list[dict]:
        """Return all records from a table, auto-paginating. Each item is {record_id, fields}."""
        if self._write_backend == "cli" and self._cli_command:
            records = []
            offset = 0
            while True:
                payload = self._run_cli_base_command(
                    "+record-list",
                    table_id=table_id,
                    extra_args=["--limit", str(page_size), "--offset", str(offset)],
                )
                data = payload.get("data") or {}
                rows = data.get("data") or []
                field_names = data.get("fields") or []
                record_ids = data.get("record_id_list") or []
                for idx, row in enumerate(rows):
                    record_id = record_ids[idx] if idx < len(record_ids) else ""
                    record = self._cli_row_to_record(field_names, row, record_id)
                    if self._cli_record_matches_filter(record, filter_str):
                        records.append(record)
                if not data.get("has_more"):
                    break
                offset += len(rows)
            return records

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

            try:
                resp = self._client.bitable.v1.app_table_record.list(req_builder.build())
            except Exception as exc:
                if self._cli_command and self._sdk_read_error_allows_cli_fallback(exc):
                    logger.warning(
                        "Falling back to CLI list_records after SDK read failure: table=%s filter=%s error=%s",
                        table_id,
                        filter_str,
                        exc,
                    )
                    records = []
                    offset = 0
                    while True:
                        payload = self._run_cli_base_command(
                            "+record-list",
                            table_id=table_id,
                            extra_args=["--limit", str(page_size), "--offset", str(offset)],
                        )
                        data = payload.get("data") or {}
                        rows = data.get("data") or []
                        field_names = data.get("fields") or []
                        record_ids = data.get("record_id_list") or []
                        for idx, row in enumerate(rows):
                            record_id = record_ids[idx] if idx < len(record_ids) else ""
                            record = self._cli_row_to_record(field_names, row, record_id)
                            if self._cli_record_matches_filter(record, filter_str):
                                records.append(record)
                        if not data.get("has_more"):
                            return records
                        offset += len(rows)
                raise
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
        if self._write_backend == "cli" and self._cli_command:
            payload = self._run_cli_base_command(
                "+record-get",
                table_id=table_id,
                extra_args=["--record-id", record_id],
            )
            record = ((payload.get("data") or {}).get("record") or {})
            return {"record_id": record_id, "fields": record}

        try:
            resp = self._client.bitable.v1.app_table_record.get(
                GetAppTableRecordRequest.builder()
                .app_token(self.base_token)
                .table_id(table_id)
                .record_id(record_id)
                .build()
            )
        except Exception as exc:
            if self._cli_command and self._sdk_read_error_allows_cli_fallback(exc):
                logger.warning(
                    "Falling back to CLI get_record after SDK read failure: table=%s record=%s error=%s",
                    table_id,
                    record_id,
                    exc,
                )
                payload = self._run_cli_base_command(
                    "+record-get",
                    table_id=table_id,
                    extra_args=["--record-id", record_id],
                )
                record = ((payload.get("data") or {}).get("record") or {})
                return {"record_id": record_id, "fields": record}
            raise
        if not resp.success():
            raise RuntimeError(
                f"get_record failed [{resp.code}]: {resp.msg} "
                f"(table={table_id}, record={record_id})"
            )
        return {"record_id": resp.data.record.record_id, "fields": resp.data.record.fields or {}}

    def update_record(self, table_id: str, record_id: str, fields: dict) -> None:
        """Update specific fields on an existing record."""
        if self._write_backend == "cli":
            try:
                self._run_cli_bitable_write(
                    table_id=table_id,
                    record_id=record_id,
                    fields=fields,
                )
                return
            except RuntimeError as exc:
                if not self._cli_error_allows_sdk_fallback(str(exc)):
                    raise
                logger.warning(
                    "Falling back to SDK update_record after CLI failure: table=%s record=%s fields=%s error=%s",
                    table_id,
                    record_id,
                    list(fields.keys()),
                    exc,
                )

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
            "策略编号",
            "方案编号",
            "场景编号",
            "人设编号",
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
            try:
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
            except RuntimeError as exc:
                if not self._cli_error_allows_sdk_fallback(str(exc)):
                    raise
                logger.warning(
                    "Falling back to SDK create_record after CLI failure: table=%s fields=%s error=%s",
                    table_id,
                    list(fields.keys()),
                    exc,
                )

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
        if self._write_backend == "cli" and self._cli_command:
            self._run_cli_base_command(
                "+record-delete",
                table_id=table_id,
                extra_args=["--record-id", record_id, "--yes"],
            )
            return

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
        """Extract plain text from common Feishu field shapes."""
        val = self.get_field(record, field)
        if val is None:
            return default
        if isinstance(val, list):
            parts = []
            for seg in val:
                if isinstance(seg, dict):
                    text = seg.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                elif isinstance(seg, str):
                    parts.append(seg)
            return "".join(parts) if parts else default
        return str(val)

    def get_option(self, record: dict, field: str, default: str = "") -> str:
        """Extract single-select option value."""
        val = self.get_field(record, field)
        if val is None:
            return default
        if isinstance(val, dict):
            return val.get("text", default)
        if isinstance(val, list):
            if not val:
                return default
            first = val[0]
            if isinstance(first, dict):
                return first.get("text", default)
            if isinstance(first, str):
                return first
            return default
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

        Supported shapes seen in this project:
        - [{"record_ids": ["recXXX"], ...}]
        - [{"id": "recXXX"}]
        - [{"record_id": "recXXX"}]
        - ["recXXX"]
        """
        val = self.get_field(record, field)
        if not val:
            return []

        def _extract_ids(item: Any) -> list[str]:
            if isinstance(item, str):
                return [item] if item else []
            if not isinstance(item, dict):
                return []
            ids = item.get("record_ids")
            if isinstance(ids, list):
                return [i for i in ids if isinstance(i, str) and i]
            for key in ("id", "record_id"):
                candidate = item.get(key)
                if isinstance(candidate, str) and candidate:
                    return [candidate]
            return []

        if isinstance(val, list):
            ids = []
            for item in val:
                ids.extend(_extract_ids(item))
            return ids
        return _extract_ids(val)

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
