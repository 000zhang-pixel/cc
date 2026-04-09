"""
Stats router — /api/v1/stats
Returns aggregate counts for the dashboard overview cards.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import select, func
from sqlalchemy.orm import Session

import db
from db.models import Plan, Content, PublishRecord, TaskLog, SyncCursor

router = APIRouter()


@router.get("")
def get_stats():
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    since_24h = datetime.utcnow() - timedelta(hours=24)

    with Session(db._get_engine()) as s:
        # --- Plans ---
        plan_rows = s.execute(
            select(Plan.exec_status, func.count().label("n"))
            .group_by(Plan.exec_status)
        ).all()
        plans = {r.exec_status: r.n for r in plan_rows}
        plans["total"] = sum(plans.values())

        # --- Contents ---
        content_gen = s.execute(
            select(Content.gen_status, func.count().label("n"))
            .group_by(Content.gen_status)
        ).all()
        content_review = s.execute(
            select(Content.review_status, func.count().label("n"))
            .group_by(Content.review_status)
        ).all()
        contents = {r.gen_status: r.n for r in content_gen}
        contents.update({r.review_status: r.n for r in content_review})
        contents["total"] = s.execute(select(func.count()).select_from(Content)).scalar_one()

        # --- Publish ---
        pub_rows = s.execute(
            select(PublishRecord.pub_status, func.count().label("n"))
            .group_by(PublishRecord.pub_status)
        ).all()
        publish = {r.pub_status: r.n for r in pub_rows}
        publish["total"] = sum(publish.values())

        # --- Logs 24h ---
        logs_24h = s.execute(
            select(func.count()).select_from(TaskLog)
            .where(TaskLog.created_at >= since_24h)
        ).scalar_one()

        errors_24h = s.execute(
            select(func.count()).select_from(TaskLog)
            .where(TaskLog.created_at >= since_24h, TaskLog.level == "ERROR")
        ).scalar_one()

        # --- Last sync ---
        last_sync = s.execute(
            select(func.max(SyncCursor.updated_at))
        ).scalar_one()

        # --- Today activity ---
        plans_today = s.execute(
            select(func.count()).select_from(Plan)
            .where(Plan.started_at >= today_start)
        ).scalar_one()

        contents_today = s.execute(
            select(func.count()).select_from(Content)
            .where(Content.created_at >= today_start)
        ).scalar_one()

    return {
        "plans": {
            "total": plans.get("total", 0),
            "待执行": plans.get("待执行", 0),
            "执行中": plans.get("执行中", 0),
            "完成": plans.get("完成", 0),
            "失败": plans.get("失败", 0),
            "today": plans_today,
        },
        "contents": {
            "total": contents.get("total", 0),
            "待审核": contents.get("待审核", 0),
            "已通过": contents.get("已通过", 0),
            "已拒绝": contents.get("已拒绝", 0),
            "today": contents_today,
        },
        "publish": {
            "total": publish.get("total", 0),
            "待发布": publish.get("待发布", 0),
            "已发布": publish.get("已发布", 0),
            "发布失败": publish.get("发布失败", 0),
        },
        "logs": {
            "count_24h": logs_24h,
            "errors_24h": errors_24h,
        },
        "last_sync_at": last_sync.strftime("%Y-%m-%d %H:%M") if last_sync else None,
    }
