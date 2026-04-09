"""
Logs router — /api/v1/logs
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session

import db
from db.models import TaskLog
from schemas import TaskLogOut, PagedResponse

router = APIRouter()


@router.get("", response_model=PagedResponse)
def list_logs(
    entity_type: str | None = Query(None),
    level: str | None = Query(None),
    entity_code: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
):
    with Session(db._get_engine()) as s:
        q = select(TaskLog)
        if entity_type:
            q = q.where(TaskLog.entity_type == entity_type)
        if level:
            q = q.where(TaskLog.level == level)
        if entity_code:
            q = q.where(TaskLog.entity_code == entity_code)
        total = s.execute(select(func.count()).select_from(q.subquery())).scalar_one()
        items = s.execute(
            q.order_by(TaskLog.created_at.desc()).offset((page - 1) * limit).limit(limit)
        ).scalars().all()
        return PagedResponse(
            total=total, page=page, limit=limit,
            items=[TaskLogOut.model_validate(r) for r in items],
        )


@router.get("/stream")
async def stream_logs():
    """
    Server-Sent Events endpoint: streams new TaskLog entries as they appear.
    Poll every 2 seconds; only sends rows newer than the connection start.
    """
    async def event_generator():
        since_id = 0
        # Seed with the latest existing log ID so we only stream new entries
        with Session(db._get_engine()) as s:
            latest = s.execute(
                select(TaskLog.id).order_by(TaskLog.id.desc()).limit(1)
            ).scalar_one_or_none()
            if latest:
                since_id = latest

        while True:
            await asyncio.sleep(2)
            with Session(db._get_engine()) as s:
                rows = s.execute(
                    select(TaskLog)
                    .where(TaskLog.id > since_id)
                    .order_by(TaskLog.id.asc())
                    .limit(50)
                ).scalars().all()
            for row in rows:
                since_id = row.id
                data = TaskLogOut.model_validate(row).model_dump_json()
                yield f"data: {data}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
