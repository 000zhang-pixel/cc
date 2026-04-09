"""
Contents router — /api/v1/contents
"""
from __future__ import annotations

import base64
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Query, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session

import db
from db.models import Content, get_session
from schemas import ContentOut, PagedResponse, MigrateRequest

router = APIRouter()


@router.get("", response_model=PagedResponse)
def list_contents(
    plan_code: str | None = Query(None),
    gen_status: str | None = Query(None),
    review_status: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    with Session(db._get_engine()) as s:
        q = select(Content)
        if plan_code:
            q = q.where(Content.content_code.startswith(plan_code))
        if gen_status:
            q = q.where(Content.gen_status == gen_status)
        if review_status:
            q = q.where(Content.review_status == review_status)
        total = s.execute(select(func.count()).select_from(q.subquery())).scalar_one()
        items = s.execute(
            q.order_by(Content.updated_at.desc()).offset((page - 1) * limit).limit(limit)
        ).scalars().all()
        return PagedResponse(
            total=total, page=page, limit=limit,
            items=[ContentOut.model_validate(c) for c in items],
        )


@router.get("/{content_code}", response_model=ContentOut)
def get_content(content_code: str):
    with Session(db._get_engine()) as s:
        content = s.execute(
            select(Content).where(Content.content_code == content_code)
        ).scalar_one_or_none()
        if content is None:
            raise HTTPException(404, f"Content {content_code!r} not found")
        return ContentOut.model_validate(content)


class ReviewBody(BaseModel):
    action: str    # "approve" or "reject"
    note: str = ""


@router.post("/{content_code}/review")
def review_content(content_code: str, body: ReviewBody):
    if body.action not in ("approve", "reject"):
        raise HTTPException(400, "action must be 'approve' or 'reject'")
    new_status = "已通过" if body.action == "approve" else "已拒绝"
    result = db.update_content_status(content_code, review_status=new_status)
    if result is None:
        raise HTTPException(404, f"Content {content_code!r} not found")
    db.log_task("content", result, "INFO",
                f"Review action={body.action} note={body.note!r}",
                entity_code=content_code)

    pub_code = None
    if body.action == "approve":
        # Derive pub_code: T_xxx → Pub_xxx  (strip leading "T_" prefix)
        base = content_code[2:] if content_code.startswith("T_") else content_code
        pub_code = f"Pub_{base}"
        # Link via content_id FK if the content row exists
        with Session(db._get_engine()) as s:
            content_row = s.execute(
                select(Content).where(Content.content_code == content_code)
            ).scalar_one_or_none()
            content_id = content_row.id if content_row else None
        db.upsert_publish_record(pub_code, pub_status="待发布", content_id=content_id)
        db.log_task("publish", None, "INFO",
                    f"Auto-created publish record on approve",
                    entity_code=pub_code)

    return {"ok": True, "content_code": content_code, "review_status": new_status,
            "pub_code": pub_code}


@router.get("/{content_code}/preview")
def preview_content(content_code: str, max_images: int = Query(8, ge=1, le=20)):
    """Return base64-encoded images from local_dir plus title/body text."""
    MAX_SIZE = 5 * 1024 * 1024  # 5 MB per image
    SUPPORTED = {".jpg", ".jpeg", ".png", ".webp"}

    with Session(db._get_engine()) as s:
        content = s.execute(
            select(Content).where(Content.content_code == content_code)
        ).scalar_one_or_none()
        if content is None:
            raise HTTPException(404, f"Content {content_code!r} not found")

        result = {"title": content.title, "body": content.body, "images": []}

        if not content.local_dir:
            return result

        p = Path(content.local_dir)
        if not p.exists():
            result["dir_missing"] = True
            return result

        count = 0
        for f in sorted(p.iterdir()):
            if count >= max_images:
                break
            if not f.is_file() or f.suffix.lower() not in SUPPORTED:
                continue
            size = f.stat().st_size
            if size > MAX_SIZE:
                result["images"].append({"name": f.name, "skipped": True, "reason": "too_large"})
                continue
            mime_map = {".png": "image/png", ".webp": "image/webp"}
            mime = mime_map.get(f.suffix.lower(), "image/jpeg")
            data_url = f"data:{mime};base64,{base64.b64encode(f.read_bytes()).decode()}"
            result["images"].append({"name": f.name, "data_url": data_url, "size": size})
            count += 1

        return result


@router.post("/{content_code}/migrate")
def trigger_migrate(content_code: str, body: MigrateRequest,
                    background_tasks: BackgroundTasks, request: Request):
    """Trigger MaterialMigrationHandler for this content record."""
    if not request.app.state.handlers_ready:
        raise HTTPException(503, "Handler singletons not initialized")

    with Session(db._get_engine()) as s:
        content = s.execute(
            select(Content).where(Content.content_code == content_code)
        ).scalar_one_or_none()
        if content is None:
            raise HTTPException(404, f"Content {content_code!r} not found")
        if not content.feishu_record_id:
            raise HTTPException(400, "Content has no feishu_record_id — cannot trigger migration")
        feishu_record_id = content.feishu_record_id

    feishu = request.app.state.feishu
    tables = request.app.state.tables
    migrate_handler = request.app.state.migrate_handler

    # Update Feishu 表4 with source folder path and trigger flag
    try:
        feishu.update_record(tables["content"], feishu_record_id, {
            "素材文件夹路径": body.source_folder,
            "确认搬迁素材": "是",
            "搬迁状态": "待搬迁",
        })
    except Exception as exc:
        raise HTTPException(502, f"Failed to update Feishu content record: {exc}")

    from core.task import Task, TASK_MATERIAL_MIGRATION
    task = Task(
        task_type=TASK_MATERIAL_MIGRATION,
        table_id=tables["content"],
        record_id=feishu_record_id,
        payload={"content_code": content_code},
    )
    background_tasks.add_task(migrate_handler, task)
    db.log_task("content", 0, "INFO", f"Admin triggered material migration from {body.source_folder}",
                entity_code=content_code)
    return {"ok": True, "content_code": content_code, "source_folder": body.source_folder}


@router.get("/{content_code}/files")
def list_files(content_code: str):
    """List files in the local_dir for this content record."""
    with Session(db._get_engine()) as s:
        content = s.execute(
            select(Content).where(Content.content_code == content_code)
        ).scalar_one_or_none()
        if content is None:
            raise HTTPException(404, f"Content {content_code!r} not found")
        if not content.local_dir:
            return {"files": []}
        p = Path(content.local_dir)
        if not p.exists():
            return {"files": [], "dir": str(p), "exists": False}
        files = [
            {"name": f.name, "size": f.stat().st_size, "suffix": f.suffix.lower()}
            for f in sorted(p.iterdir()) if f.is_file()
        ]
        return {"files": files, "dir": str(p), "exists": True}
