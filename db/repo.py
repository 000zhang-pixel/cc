"""
db/repo.py — thin repository layer for middleware handlers.

Provides:
  - log_task(): write a TaskLog entry
  - update_plan_status(): atomic plan status transition
  - update_content_status(): atomic content status transition
  - update_publish_status(): atomic publish record status transition
"""
import logging
import traceback
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import select

from db.models import Plan, Content, PublishRecord, TaskLog, make_engine

logger = logging.getLogger(__name__)

# Module-level shared engine (initialised once in middleware main.py)
_engine = None


def init_engine(engine=None):
    """Call once from middleware main.py on startup."""
    global _engine
    _engine = engine or make_engine()
    return _engine


def _get_engine():
    global _engine
    if _engine is None:
        _engine = make_engine()
    return _engine


# ---------------------------------------------------------------------------
# Task logging
# ---------------------------------------------------------------------------

def log_task(
    entity_type: str,
    entity_id: int,
    level: str,
    message: str,
    entity_code: str | None = None,
    detail: str | None = None,
):
    """Write a TaskLog row. Non-blocking — errors are swallowed to never break handlers."""
    try:
        with Session(_get_engine()) as s:
            s.add(TaskLog(
                entity_type=entity_type,
                entity_id=entity_id,
                entity_code=entity_code,
                level=level,
                message=message,
                detail=detail,
            ))
            s.commit()
    except Exception as e:
        logger.warning("log_task failed (non-critical): %s", e)


def log_exc(entity_type: str, entity_id: int, message: str, entity_code: str | None = None):
    """Shortcut: log current exception as ERROR with full traceback."""
    log_task(
        entity_type=entity_type,
        entity_id=entity_id,
        level="ERROR",
        message=message,
        entity_code=entity_code,
        detail=traceback.format_exc(),
    )


# ---------------------------------------------------------------------------
# Plan status
# ---------------------------------------------------------------------------

def get_plan_by_code(plan_code: str) -> Plan | None:
    with Session(_get_engine()) as s:
        return s.execute(
            select(Plan).where(Plan.plan_code == plan_code)
        ).scalar_one_or_none()


def update_plan_status(
    plan_code: str,
    exec_status: str,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    error_msg: str | None = None,
) -> int | None:
    """Returns plan.id if found, None otherwise."""
    with Session(_get_engine()) as s:
        plan = s.execute(
            select(Plan).where(Plan.plan_code == plan_code)
        ).scalar_one_or_none()
        if not plan:
            logger.warning("update_plan_status: plan %s not found in local DB", plan_code)
            return None
        plan.exec_status = exec_status
        if started_at is not None:
            plan.started_at = started_at
        if finished_at is not None:
            plan.finished_at = finished_at
        if error_msg is not None:
            plan.error_msg = error_msg
        plan.updated_at = datetime.utcnow()
        s.commit()
        return plan.id


def mark_plan_started(plan_code: str) -> int | None:
    return update_plan_status(plan_code, "执行中", started_at=datetime.utcnow())


def mark_plan_done(plan_code: str) -> int | None:
    return update_plan_status(plan_code, "完成", finished_at=datetime.utcnow())


def mark_plan_failed(plan_code: str, error_msg: str) -> int | None:
    return update_plan_status(plan_code, "失败", error_msg=error_msg)


# ---------------------------------------------------------------------------
# Content status
# ---------------------------------------------------------------------------

def upsert_content(content_code: str, **fields) -> int | None:
    """Create or update a Content row. Returns content.id."""
    with Session(_get_engine()) as s:
        content = s.execute(
            select(Content).where(Content.content_code == content_code)
        ).scalar_one_or_none()
        if content:
            for k, v in fields.items():
                setattr(content, k, v)
            content.updated_at = datetime.utcnow()
        else:
            content = Content(content_code=content_code, **fields)
            s.add(content)
        s.commit()
        return content.id


def update_content_status(
    content_code: str,
    **fields: Any,
) -> int | None:
    with Session(_get_engine()) as s:
        content = s.execute(
            select(Content).where(Content.content_code == content_code)
        ).scalar_one_or_none()
        if not content:
            logger.warning("update_content_status: content %s not found", content_code)
            return None
        for k, v in fields.items():
            setattr(content, k, v)
        content.updated_at = datetime.utcnow()
        s.commit()
        return content.id


# ---------------------------------------------------------------------------
# PublishRecord status
# ---------------------------------------------------------------------------

def upsert_publish_record(pub_code: str, **fields) -> int | None:
    """Create or update a PublishRecord row. Returns pub_record.id."""
    with Session(_get_engine()) as s:
        rec = s.execute(
            select(PublishRecord).where(PublishRecord.pub_code == pub_code)
        ).scalar_one_or_none()
        if rec:
            for k, v in fields.items():
                setattr(rec, k, v)
            rec.updated_at = datetime.utcnow()
        else:
            rec = PublishRecord(pub_code=pub_code, **fields)
            s.add(rec)
        s.commit()
        return rec.id


def update_publish_status(pub_code: str, **fields: Any) -> int | None:
    with Session(_get_engine()) as s:
        rec = s.execute(
            select(PublishRecord).where(PublishRecord.pub_code == pub_code)
        ).scalar_one_or_none()
        if not rec:
            logger.warning("update_publish_status: pub_record %s not found", pub_code)
            return None
        for k, v in fields.items():
            setattr(rec, k, v)
        rec.updated_at = datetime.utcnow()
        s.commit()
        return rec.id
