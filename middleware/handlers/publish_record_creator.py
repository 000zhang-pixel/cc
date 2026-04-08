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
    def __init__(
        self,
        feishu: FeishuClient,
        tables: dict,
        local_storage: LocalStorage | None = None,
        notifications_cfg: dict | None = None,
    ):
        self._feishu = feishu
        self._tables = tables
        self._storage = local_storage
        self._notifications = notifications_cfg or {}

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
            # Build enriched card data from content record
            platform = f.get_option(content_rec, "目标平台") or "得物"
            form_type = f.get_option(content_rec, "内容形态") or ""
            title_preview = f.get_text(content_rec, "标题").strip()[:30] or "—"
            # SKU name (best-effort)
            sku_name = ""
            try:
                sku_ids = f.get_link_ids(content_rec, "关联SKU")
                if sku_ids:
                    sku_rec = f.get_record(self._tables.get("sku", ""), sku_ids[0]) if self._tables.get("sku") else None
                    if sku_rec:
                        sku_name = f.get_text(sku_rec, "SKU名称").strip()
            except Exception:
                pass
            self._notify_card_queued(pub_code, platform, form_type, title_preview, sku_name)

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

    def _notify_card_queued(
        self, pub_code: str, platform: str, form_type: str,
        title_preview: str, sku_name: str
    ) -> None:
        """Send a '待发布' card to the configured Feishu group."""
        if not self._notifications.get("enabled"):
            return
        if not self._notifications.get("notify_on", {}).get("queued", True):
            return
        chat_id = self._notifications.get("chat_id", "").strip()
        if not chat_id:
            return
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"content": "📋 待发布任务已进队列", "tag": "plain_text"},
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"content": f"**发布编号**\n{pub_code}", "tag": "lark_md"}},
                        {"is_short": True, "text": {"content": f"**目标平台**\n{platform}", "tag": "lark_md"}},
                    ],
                },
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"content": f"**内容形态**\n{form_type or '—'}", "tag": "lark_md"}},
                        {"is_short": True, "text": {"content": f"**SKU**\n{sku_name or '—'}", "tag": "lark_md"}},
                    ],
                },
                {
                    "tag": "div",
                    "text": {"content": f"**标题预览**\n{title_preview}", "tag": "lark_md"},
                },
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [{"tag": "plain_text", "content": "等待发布引擎调度处理"}],
                },
            ],
        }
        try:
            self._feishu.send_group_card(chat_id, card)
        except Exception as exc:
            logger.warning("[Notify] card send failed: %s", exc)
