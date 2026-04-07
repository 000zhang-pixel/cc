"""
Feishu Bitable read/write client for the middleware.
Wraps lark-oapi SDK for record CRUD operations.
"""
import os
import logging
from typing import Any

import lark_oapi as lark
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

    def create_record(self, table_id: str, fields: dict) -> str:
        """Create a new record and return its record_id."""
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
