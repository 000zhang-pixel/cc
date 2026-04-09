"""
Sync router — /api/v1/sync
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.orm import Session

import db
from db.models import SyncCursor
from schemas import SyncCursorOut

router = APIRouter()

# Track whether a sync is running (simple flag — single-process admin server)
_sync_running = False


def _run_sync():
    global _sync_running
    _sync_running = True
    try:
        # Import FeishuSyncer + config at runtime to avoid circular imports
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "middleware"))
        from core.config import load_system
        from adapters.feishu import FeishuClient
        from db.sync import FeishuSyncer

        sys_cfg = load_system()
        feishu_cfg = sys_cfg["feishu"]
        feishu = FeishuClient(
            app_id=feishu_cfg["app_id"],
            app_secret=feishu_cfg["app_secret"],
            base_token=feishu_cfg["base_token"],
        )
        syncer = FeishuSyncer(feishu, feishu_cfg["tables"], db._get_engine())
        syncer.sync_all()
    finally:
        _sync_running = False


@router.post("/pull")
def trigger_sync(background_tasks: BackgroundTasks):
    """Trigger a full Feishu→local sync in the background."""
    global _sync_running
    if _sync_running:
        raise HTTPException(409, "Sync already in progress")
    background_tasks.add_task(_run_sync)
    return {"ok": True, "message": "Sync started in background"}


@router.get("/status", response_model=list[SyncCursorOut])
def sync_status():
    """Return sync cursor state for all tables."""
    with Session(db._get_engine()) as s:
        rows = s.execute(select(SyncCursor).order_by(SyncCursor.table_name)).scalars().all()
        return [SyncCursorOut.model_validate(r) for r in rows]
