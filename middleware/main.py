"""
Middleware entry point.
Run from the middleware/ directory:
    python main.py
"""
import logging
import queue
import signal
import sys

from adapters.feishu import FeishuClient
from core.config import load_system, load_model_params
from core.dispatcher import Dispatcher
from core.local_storage import LocalStorage
from core.poller import Poller
from core.task import (
    TASK_CONTENT_GENERATION,
    TASK_MATERIAL_MIGRATION,
    TASK_PUBLISH_RECORD_CREATE,
    TASK_PUBLISH,
    TASK_MATERIAL_ANALYSIS,
)
from handlers.content_generation import ContentGenerationHandler
from handlers.publish import PublishHandler
from handlers.publish_record_creator import PublishRecordCreatorHandler
from handlers.material_analysis import MaterialAnalysisHandler
from handlers.material_migration import MaterialMigrationHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    sys_cfg = load_system()
    model_params = load_model_params()

    feishu_cfg = sys_cfg["feishu"]
    feishu = FeishuClient(
        app_id=feishu_cfg["app_id"],
        app_secret=feishu_cfg["app_secret"],
        base_token=feishu_cfg["base_token"],
    )
    tables = feishu_cfg["tables"]

    storage_root = sys_cfg.get("local_storage", {}).get("root", "D:/ai_content")
    storage = LocalStorage(root=storage_root)
    logger.info("LocalStorage root: %s", storage_root)

    publish_cfg = sys_cfg.get("publish", {})
    notifications_cfg = sys_cfg.get("notifications", {})

    # --- Build handlers ---
    handlers = {
        TASK_CONTENT_GENERATION: ContentGenerationHandler(feishu, tables, model_params, storage),
        TASK_MATERIAL_MIGRATION: MaterialMigrationHandler(feishu, tables, storage),
        TASK_PUBLISH_RECORD_CREATE: PublishRecordCreatorHandler(feishu, tables, storage, notifications_cfg),
        TASK_PUBLISH: PublishHandler(feishu, tables, storage, publish_cfg, notifications_cfg),
        TASK_MATERIAL_ANALYSIS: MaterialAnalysisHandler(feishu, tables, model_params),
    }

    task_queue: queue.Queue = queue.Queue()

    poller = Poller(
        feishu=feishu,
        table_ids=tables,
        task_queue=task_queue,
        interval_seconds=sys_cfg["poller"]["interval_seconds"],
    )
    dispatcher = Dispatcher(task_queue=task_queue, handlers=handlers, num_workers=4)

    poller.start()
    dispatcher.start()
    logger.info("Middleware running. Press Ctrl+C to stop.")

    # Graceful shutdown on SIGINT/SIGTERM
    stop_signals = [signal.SIGINT]
    if hasattr(signal, "SIGTERM"):
        stop_signals.append(signal.SIGTERM)

    def _shutdown(signum, frame):
        logger.info("Shutting down…")
        poller.stop()
        dispatcher.stop()
        sys.exit(0)

    for sig in stop_signals:
        signal.signal(sig, _shutdown)

    # Block main thread
    signal.pause() if hasattr(signal, "pause") else _windows_wait(poller, dispatcher)


def _windows_wait(poller, dispatcher):
    """Windows doesn't have signal.pause(). Just sleep until KeyboardInterrupt."""
    import time
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down…")
        poller.stop()
        dispatcher.stop()


if __name__ == "__main__":
    main()
