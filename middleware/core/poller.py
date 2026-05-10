"""
Poller — every interval_seconds, queries Feishu tables for trigger conditions,
immediately updates the status field (anti-duplication), then enqueues a Task.
"""
import logging
import queue
import threading
import time

from adapters.feishu import FeishuClient
from core.task import (
    Task,
    TASK_CONTENT_GENERATION,
    TASK_MATERIAL_MIGRATION,
    TASK_PUBLISH_RECORD_CREATE,
    TASK_PUBLISH,
    TASK_MATERIAL_ANALYSIS,
)

logger = logging.getLogger(__name__)


class Poller:
    """
    Polls Feishu tables and pushes Tasks onto task_queue.
    Runs in its own daemon thread.
    """

    def __init__(
        self,
        feishu: FeishuClient,
        table_ids: dict,          # mapping name → table_id from system.yaml
        task_queue: queue.Queue,
        interval_seconds: int = 10,
    ):
        self._feishu = feishu
        self._tables = table_ids
        self._queue = task_queue
        self._interval = interval_seconds
        self._stop_event = threading.Event()
        # In-memory dedup for tasks that have no lockable status field
        self._queued_reviews: set[str] = set()
        # In-memory guard for long-running plan generation tasks. Feishu reads can
        # briefly lag after we lock a plan to 执行中, so prevent the same plan from
        # being queued again within the same middleware process.
        self._queued_plans: set[str] = set()

    def start(self):
        t = threading.Thread(target=self._run, daemon=True, name="Poller")
        t.start()
        logger.info("Poller started (interval=%ds)", self._interval)

    def stop(self):
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _run(self):
        while not self._stop_event.is_set():
            try:
                self._poll_all()
            except Exception:
                logger.exception("Poller cycle error")
            self._stop_event.wait(self._interval)

    def _poll_all(self):
        self._poll_plan()
        self._poll_content_migration()
        self._poll_content_review()
        self._poll_publish()
        self._poll_material()

    # ------------------------------------------------------------------
    # 表2 内容规划表 — 确认执行=是/立即执行 AND 执行状态 not in {执行中,完成,失败}
    # ------------------------------------------------------------------

    _PLAN_TRIGGER_VALUES = {"是", "立即执行"}
    _PLAN_SKIP_STATUSES  = {"执行中", "完成", "失败"}

    def _poll_plan(self):
        table_id = self._tables["plan"]
        records = self._feishu.list_records(table_id)
        for rec in records:
            f = self._feishu
            trigger = f.get_option(rec, "确认执行")
            status  = f.get_option(rec, "执行状态")
            record_id = rec["record_id"]

            if trigger not in self._PLAN_TRIGGER_VALUES:
                self._queued_plans.discard(record_id)
                continue
            if status in self._PLAN_SKIP_STATUSES:
                if status in {"完成", "失败"}:
                    self._queued_plans.discard(record_id)
                continue
            if record_id in self._queued_plans:
                logger.info("[Poller] Skip duplicate in-flight plan record %s", record_id)
                continue

            # Anti-duplication: immediately mark as 执行中
            try:
                f.update_record(table_id, record_id, {"执行状态": "执行中"})
            except Exception:
                logger.exception("Failed to lock plan record %s", record_id)
                continue

            self._queued_plans.add(record_id)
            self._queue.put(Task(
                task_type=TASK_CONTENT_GENERATION,
                table_id=table_id,
                record_id=record_id,
                payload=rec["fields"],
            ))
            logger.info("[Poller] Queued content_generation for plan record %s", record_id)

    # ------------------------------------------------------------------
    # 表4 内容生成表 — 确认搬迁=是 AND 搬迁状态=待搬迁
    # ------------------------------------------------------------------

    def _poll_content_migration(self):
        table_id = self._tables["content"]
        records = self._feishu.list_records(table_id)
        for rec in records:
            f = self._feishu
            if f.get_option(rec, "确认搬迁") != "是":
                continue
            status = f.get_option(rec, "搬迁状态")
            if status in {"搬迁中", "已完成", "搬迁失败"}:
                continue

            record_id = rec["record_id"]
            try:
                f.update_record(table_id, record_id, {"搬迁状态": "搬迁中"})
            except Exception:
                logger.exception("Failed to lock migration record %s", record_id)
                continue

            self._queue.put(Task(
                task_type=TASK_MATERIAL_MIGRATION,
                table_id=table_id,
                record_id=record_id,
                payload=rec["fields"],
            ))
            logger.info("[Poller] Queued material_migration for content record %s", record_id)

    # ------------------------------------------------------------------
    # 表4 内容生成表 — 审核状态=已通过（需中台在表5创建发布记录）
    # 防重：表5对应记录已存在则跳过（由 PublishRecordCreator handler 处理）
    # ------------------------------------------------------------------

    def _poll_content_review(self):
        table_id = self._tables["content"]
        records = self._feishu.list_records(table_id)
        for rec in records:
            if self._feishu.get_option(rec, "审核状态") != "已通过":
                continue
            record_id = rec["record_id"]
            if record_id in self._queued_reviews:
                continue
            self._queued_reviews.add(record_id)
            self._queue.put(Task(
                task_type=TASK_PUBLISH_RECORD_CREATE,
                table_id=table_id,
                record_id=record_id,
                payload=rec["fields"],
            ))
            logger.info("[Poller] Queued publish_record_create for content record %s", record_id)

    # ------------------------------------------------------------------
    # 表5 发布执行表 — 发布方式≠待定 AND 发布状态=待发布
    # ------------------------------------------------------------------

    def _poll_publish(self):
        table_id = self._tables["publish"]
        records = self._feishu.list_records(table_id)
        for rec in records:
            f = self._feishu
            method = f.get_option(rec, "发布方式")
            status = f.get_option(rec, "发布状态")
            if not method or method == "待定":
                continue
            if status != "待发布":
                continue

            record_id = rec["record_id"]
            try:
                f.update_record(table_id, record_id, {"发布状态": "发布中"})
            except Exception:
                logger.exception("Failed to lock publish record %s", record_id)
                continue

            self._queue.put(Task(
                task_type=TASK_PUBLISH,
                table_id=table_id,
                record_id=record_id,
                payload=rec["fields"],
            ))
            logger.info("[Poller] Queued publish for record %s", record_id)

    # ------------------------------------------------------------------
    # 表6 素材知识库 — 触发分析=是 AND 分析状态=待分析
    # ------------------------------------------------------------------

    def _poll_material(self):
        table_id = self._tables["material"]
        records = self._feishu.list_records(table_id)
        for rec in records:
            f = self._feishu
            if f.get_option(rec, "触发分析") != "是":
                continue
            if f.get_option(rec, "分析状态") in {"分析中", "已完成", "分析失败"}:
                continue

            record_id = rec["record_id"]
            try:
                self._feishu.update_record(table_id, record_id, {"分析状态": "分析中"})
            except Exception:
                logger.exception("Failed to lock material record %s", record_id)
                continue

            self._queue.put(Task(
                task_type=TASK_MATERIAL_ANALYSIS,
                table_id=table_id,
                record_id=record_id,
                payload=rec["fields"],
            ))
            logger.info("[Poller] Queued material_analysis for record %s", record_id)
