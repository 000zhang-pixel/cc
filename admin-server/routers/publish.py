"""
Publish router — /api/v1/publish
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from sqlalchemy import select, func
from sqlalchemy.orm import Session

import db
from db.models import Content, PublishRecord
from schemas import PublishOut, PagedResponse, ExecutePublishRequest

router = APIRouter()


@router.get("", response_model=PagedResponse)
def list_publish(
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    with Session(db._get_engine()) as s:
        q = select(PublishRecord)
        if status:
            q = q.where(PublishRecord.pub_status == status)
        total = s.execute(select(func.count()).select_from(q.subquery())).scalar_one()
        items = s.execute(
            q.order_by(PublishRecord.updated_at.desc()).offset((page - 1) * limit).limit(limit)
        ).scalars().all()
        return PagedResponse(
            total=total, page=page, limit=limit,
            items=[PublishOut.model_validate(r) for r in items],
        )


@router.get("/{pub_code}", response_model=PublishOut)
def get_publish(pub_code: str):
    with Session(db._get_engine()) as s:
        rec = s.execute(
            select(PublishRecord).where(PublishRecord.pub_code == pub_code)
        ).scalar_one_or_none()
        if rec is None:
            raise HTTPException(404, f"PublishRecord {pub_code!r} not found")
        return PublishOut.model_validate(rec)


@router.post("/{pub_code}/retry")
def retry_publish(pub_code: str):
    """Reset a failed publish record back to 待发布."""
    result = db.update_publish_status(pub_code, pub_status="待发布")
    if result is None:
        raise HTTPException(404, f"PublishRecord {pub_code!r} not found")
    db.log_task("publish", result, "INFO", "Admin retry: reset to 待发布", entity_code=pub_code)
    return {"ok": True, "pub_code": pub_code, "new_status": "待发布"}


@router.post("/{pub_code}/execute")
def execute_publish(pub_code: str, body: ExecutePublishRequest,
                    background_tasks: BackgroundTasks, request: Request):
    """Trigger actual publishing via PublishHandler (Feishu 表5 + publish engine)."""
    if not request.app.state.handlers_ready:
        raise HTTPException(503, "Handler singletons not initialized — check middleware config")

    feishu = request.app.state.feishu
    tables = request.app.state.tables
    pub_handler = request.app.state.pub_handler

    with Session(db._get_engine()) as s:
        rec = s.execute(
            select(PublishRecord).where(PublishRecord.pub_code == pub_code)
        ).scalar_one_or_none()
        if rec is None:
            raise HTTPException(404, f"PublishRecord {pub_code!r} not found")
        if rec.pub_status not in ("待发布", "发布失败"):
            raise HTTPException(400, f"Cannot execute publish with status={rec.pub_status!r}")

        if not rec.content_id:
            raise HTTPException(400, "PublishRecord has no linked content — cannot trigger publish")
        content = s.get(Content, rec.content_id)
        if not content or not content.feishu_record_id:
            raise HTTPException(400, "Linked content has no Feishu record — sync content from Feishu first")

        feishu_record_id = rec.feishu_record_id
        content_feishu_id = content.feishu_record_id

    # If no Feishu 表5 record exists yet, create one
    if not feishu_record_id:
        try:
            now_ms = int(datetime.utcnow().timestamp() * 1000)
            feishu_record_id = feishu.create_record(tables["publish"], {
                "发布编号": pub_code,
                "关联内容": [content_feishu_id],
                "发布方式": body.publish_method,
                "发布状态": "待发布",
                "创建时间": now_ms,
            })
            db.update_publish_status(pub_code, feishu_record_id=feishu_record_id)
        except Exception as exc:
            raise HTTPException(502, f"Failed to create Feishu 表5 record: {exc}")
    else:
        try:
            feishu.update_record(tables["publish"], feishu_record_id, {
                "发布方式": body.publish_method,
            })
        except Exception as exc:
            raise HTTPException(502, f"Failed to update Feishu publish record: {exc}")

    # Update local DB status
    db.update_publish_status(pub_code, publish_method=body.publish_method, pub_status="发布中")

    background_tasks.add_task(_run_publish, pub_handler, pub_code, feishu_record_id, tables)
    db.log_task("publish", 0, "INFO",
                f"Admin triggered publish method={body.publish_method}",
                entity_code=pub_code)
    return {"ok": True, "pub_code": pub_code, "publish_method": body.publish_method,
            "feishu_record_id": feishu_record_id}


def _run_publish(pub_handler, pub_code: str, feishu_record_id: str, tables: dict):
    from core.task import Task, TASK_PUBLISH
    task = Task(
        task_type=TASK_PUBLISH,
        table_id=tables["publish"],
        record_id=feishu_record_id,
        payload={"pub_code": pub_code},
    )
    try:
        pub_handler(task)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("Background publish failed for %s: %s", pub_code, exc, exc_info=True)
        db.log_task("publish", 0, "ERROR", f"Background publish failed: {exc}", entity_code=pub_code)
