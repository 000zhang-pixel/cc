"""
PublishRecordCreatorHandler — when 表4 审核状态 = 已通过,
auto-create a 表5 发布执行表 record (first-time only).
"""
import logging
from datetime import datetime

from adapters.feishu import FeishuClient
from core.local_storage import LocalStorage
from core.task import Task

logger = logging.getLogger(__name__)


class PublishRecordCreatorHandler:
    def __init__(self, feishu: FeishuClient, tables: dict, local_storage: LocalStorage | None = None):
        self._feishu = feishu
        self._tables = tables
        self._storage = local_storage

    def __call__(self, task: Task):
        content_record_id = task.record_id
        table_content = self._tables["content"]
        table_publish = self._tables["publish"]
        f = self._feishu

        try:
            # Check if a publish record already exists for this content record.
            # Feishu link-field filters don't support record_id sub-queries,
            # so we list all records in 表5 and filter Python-side.
            all_pub = f.list_records(table_publish)
            for pub_rec in all_pub:
                link_ids = f.get_link_ids(pub_rec, "关联内容")
                if content_record_id in link_ids:
                    logger.debug(
                        "Publish record already exists for content %s, skipping", content_record_id
                    )
                    return

            # Read the content record to build the publish code
            content_rec = f.get_record(table_content, content_record_id)
            content_code = f.get_text(content_rec, "内容编号").strip()

            # Derive publish code from content code
            # content_code: T_260329_089_img01 → Pub_260329_089_img01
            pub_code = self._make_pub_code(content_code, table_publish, content_record_id)

            fields = {
                "发布编号": pub_code,
                "关联内容": [content_record_id],
                "发布方式": "待定",
                "发布状态": "待发布",
            }

            f.create_record(table_publish, fields)
            logger.info(
                "Created publish record %s for content %s", pub_code, content_record_id
            )

            # Update local storage status to queued (best-effort)
            if self._storage:
                try:
                    content_code = content_rec["fields"].get("内容编号", "")
                    # content_code format: {plan_code}_{group_id}
                    # e.g. T_260403_009_img01 → plan=T_260403_009, group=img01
                    if "_img" in content_code or "_vid" in content_code:
                        sep = "_img" if "_img" in content_code else "_vid"
                        prefix, suffix = content_code.rsplit(sep, 1)
                        plan_code = prefix
                        group_id = sep.lstrip("_") + suffix
                        self._storage.update_status(plan_code, group_id, "review_passed")
                except Exception:
                    logger.warning("LocalStorage status update failed for %s", content_record_id, exc_info=True)

        except Exception as exc:
            logger.exception(
                "PublishRecordCreator failed for content record %s", content_record_id
            )

    def _make_pub_code(self, content_code: str, table_publish: str, content_record_id: str) -> str:
        """
        Derive publish code from content code.
        T_260329_089_img01 → Pub_260329_089_img01
        For re-publish (multiple records for same content), append _02, _03 etc.
        """
        if content_code.startswith("T_"):
            # Remove leading "T_" prefix → "260329_089_img01"
            base = content_code[2:]
        else:
            base = content_code

        base_pub = f"Pub_{base}"

        # Count existing publish records for this content to determine suffix.
        # List all and filter Python-side (link-field record_id filter not supported in Feishu).
        all_pub = self._feishu.list_records(table_publish)
        count = sum(
            1 for r in all_pub
            if content_record_id in self._feishu.get_link_ids(r, "关联内容")
        )
        if count == 0:
            return base_pub
        return f"{base_pub}_{count + 1:02d}"
