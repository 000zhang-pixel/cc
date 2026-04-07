"""
Dispatcher — consumes Tasks from the queue and routes to the correct Handler.
Runs in its own daemon thread with a configurable worker pool.
"""
import logging
import queue
import threading

from core.task import (
    Task,
    TASK_CONTENT_GENERATION,
    TASK_MATERIAL_MIGRATION,
    TASK_PUBLISH_RECORD_CREATE,
    TASK_PUBLISH,
    TASK_MATERIAL_ANALYSIS,
)

logger = logging.getLogger(__name__)


class Dispatcher:
    def __init__(self, task_queue: queue.Queue, handlers: dict, num_workers: int = 4):
        """
        handlers: dict mapping task_type → callable(task)
        """
        self._queue = task_queue
        self._handlers = handlers
        self._num_workers = num_workers
        self._stop_event = threading.Event()

    def start(self):
        for i in range(self._num_workers):
            t = threading.Thread(
                target=self._worker,
                daemon=True,
                name=f"Dispatcher-{i}",
            )
            t.start()
        logger.info("Dispatcher started (%d workers)", self._num_workers)

    def stop(self):
        self._stop_event.set()

    def _worker(self):
        while not self._stop_event.is_set():
            try:
                task: Task = self._queue.get(timeout=1)
            except queue.Empty:
                continue

            handler = self._handlers.get(task.task_type)
            if handler is None:
                logger.warning("No handler for task_type=%s", task.task_type)
                self._queue.task_done()
                continue

            try:
                handler(task)
            except Exception:
                logger.exception(
                    "Handler %s failed for record %s",
                    task.task_type,
                    task.record_id,
                )
            finally:
                self._queue.task_done()
