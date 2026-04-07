"""
飞书多维表格 API 封装
提供建表、建字段、查询等操作，所有写操作均支持幂等。
"""
import logging
import lark_oapi as lark
from lark_oapi.api.bitable.v1 import (
    CreateAppTableRequest, CreateAppTableRequestBody, ReqTable,
    ListAppTableRequest,
    CreateAppTableFieldRequest, AppTableField,
    ListAppTableFieldRequest,
)

logger = logging.getLogger(__name__)


class LarkBaseClient:
    def __init__(self, app_id: str, app_secret: str):
        self.client = lark.Client.builder() \
            .app_id(app_id) \
            .app_secret(app_secret) \
            .build()

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list_tables(self, app_token: str) -> dict[str, str]:
        """返回 {表名: table_id} 映射"""
        req = ListAppTableRequest.builder().app_token(app_token).build()
        resp = self.client.bitable.v1.app_table.list(req)
        if not resp.success():
            raise RuntimeError(f"查询表列表失败: {resp.msg} (code={resp.code})")
        tables = {}
        for item in (resp.data.items or []):
            tables[item.name] = item.table_id
        return tables

    def list_fields(self, app_token: str, table_id: str) -> dict[str, str]:
        """返回 {字段名: field_id} 映射"""
        req = ListAppTableFieldRequest.builder() \
            .app_token(app_token) \
            .table_id(table_id) \
            .build()
        resp = self.client.bitable.v1.app_table_field.list(req)
        if not resp.success():
            raise RuntimeError(f"查询字段列表失败: {resp.msg} (code={resp.code})")
        fields = {}
        for item in (resp.data.items or []):
            fields[item.field_name] = item.field_id
        return fields

    # ------------------------------------------------------------------
    # 建表（幂等）
    # ------------------------------------------------------------------

    def ensure_table(self, app_token: str, table_name: str) -> str:
        """
        确保表存在，返回 table_id。
        已存在则跳过创建，直接返回现有 table_id。
        """
        existing = self.list_tables(app_token)
        if table_name in existing:
            logger.info(f"[跳过] 表已存在: {table_name}")
            return existing[table_name]

        req = CreateAppTableRequest.builder() \
            .app_token(app_token) \
            .request_body(
                CreateAppTableRequestBody.builder()
                .table(ReqTable.builder().name(table_name).build())
                .build()
            ).build()
        resp = self.client.bitable.v1.app_table.create(req)
        if not resp.success():
            raise RuntimeError(f"建表失败 [{table_name}]: {resp.msg} (code={resp.code})")
        table_id = resp.data.table_id
        logger.info(f"[创建] 表: {table_name} → {table_id}")
        return table_id

    # ------------------------------------------------------------------
    # 建字段（幂等）
    # ------------------------------------------------------------------

    def ensure_field(
        self,
        app_token: str,
        table_id: str,
        field_def: dict,
    ) -> str:
        """
        确保字段存在，返回 field_id。
        field_def 格式：
          {
            "field_name": "字段名",
            "type": 1,          # 飞书字段类型码
            "property": {...},  # 可选，类型专属属性
          }
        已存在则跳过，直接返回现有 field_id。
        """
        existing = self.list_fields(app_token, table_id)
        name = field_def["field_name"]
        if name in existing:
            logger.info(f"  [跳过] 字段已存在: {name}")
            return existing[name]

        field = AppTableField.builder() \
            .field_name(name) \
            .type(field_def["type"])

        if "property" in field_def:
            field = field.property(field_def["property"])

        req = CreateAppTableFieldRequest.builder() \
            .app_token(app_token) \
            .table_id(table_id) \
            .request_body(field.build()) \
            .build()
        resp = self.client.bitable.v1.app_table_field.create(req)
        if not resp.success():
            raise RuntimeError(
                f"建字段失败 [{name}]: {resp.msg} (code={resp.code})"
            )
        field_id = resp.data.field.field_id
        logger.info(f"  [创建] 字段: {name} (type={field_def['type']}) → {field_id}")
        return field_id
