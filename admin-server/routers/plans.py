"""
Plans router — /api/v1/plans
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import db
from db.models import Plan, Prompt, TaskLog, Sku, get_session
from schemas import PlanOut, PromptOut, TaskLogOut, PagedResponse, CreatePlanRequest, CreatePlanResponse

router = APIRouter()


def _session() -> Session:
    return get_session(db._get_engine())


@router.get("", response_model=PagedResponse)
def list_plans(
    status: str | None = Query(None, description="exec_status filter"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
):
    with Session(db._get_engine()) as s:
        q = select(Plan)
        if status:
            q = q.where(Plan.exec_status == status)
        total = s.execute(select(func.count()).select_from(q.subquery())).scalar_one()
        items = s.execute(
            q.order_by(Plan.updated_at.desc()).offset((page - 1) * limit).limit(limit)
        ).scalars().all()
        return PagedResponse(
            total=total, page=page, limit=limit,
            items=[PlanOut.model_validate(p) for p in items],
        )


@router.post("/create", response_model=CreatePlanResponse)
def create_plan(body: CreatePlanRequest, background_tasks: BackgroundTasks, request: Request):
    """Manually create a content generation task: write to local DB + Feishu table 2, then trigger ContentGenerationHandler."""
    if not request.app.state.handlers_ready:
        raise HTTPException(503, "Handler singletons not initialized — check middleware config")

    feishu = request.app.state.feishu
    tables = request.app.state.tables
    gen_handler = request.app.state.gen_handler

    with Session(db._get_engine()) as s:
        # Lookup SKU
        sku = s.get(Sku, body.sku_id)
        if sku is None:
            raise HTTPException(404, f"SKU id={body.sku_id} not found")
        if not sku.feishu_record_id:
            raise HTTPException(400, f"SKU id={body.sku_id} has no feishu_record_id — sync SKU from Feishu first")

        # Generate plan_code (count-based, retry on collision)
        plan_code = _generate_plan_code(s)

        # Write Plan to local DB first
        plan = Plan(
            plan_code=plan_code,
            sku_id=body.sku_id,
            task_type=body.task_type,
            target_platforms=json.dumps(body.target_platforms, ensure_ascii=False),
            img_count=body.img_count,
            img_per_post=body.img_per_post,
            video_count=body.video_count,
            video_min_sec=body.video_min_sec,
            video_max_sec=body.video_max_sec,
            tag_inject_n=body.tag_inject_n,
            text_model=body.text_model,
            image_model=body.image_model,
            video_model=body.video_model,
            notes=body.notes,
            exec_status="待执行",
        )
        try:
            s.add(plan)
            s.commit()
            s.refresh(plan)
        except IntegrityError:
            s.rollback()
            # Retry with incremented seq
            plan_code = _generate_plan_code(s, extra_offset=1)
            plan.plan_code = plan_code
            s.add(plan)
            s.commit()
            s.refresh(plan)

        sku_feishu_id = sku.feishu_record_id

    # Create Feishu 表2 record (synchronously before background task)
    try:
        feishu_fields = {
            "规划编号": plan_code,
            "关联SKU": [sku_feishu_id],
            "任务类型": body.task_type,
            "目标平台": body.target_platforms,
            "生成图文篇数": body.img_count,
            "每篇图片数": body.img_per_post,
            "生成视频篇数": body.video_count,
            "注入标签数(N)": body.tag_inject_n,
            "文案模型": body.text_model,
            "图片模型": body.image_model,
            "视频模型": body.video_model,
            "执行状态": "待执行",
        }
        if body.video_count > 0:
            feishu_fields["视频最短时长(秒)"] = body.video_min_sec
            feishu_fields["视频最长时长(秒)"] = body.video_max_sec
        if body.notes:
            feishu_fields["备注"] = body.notes

        feishu_record_id = feishu.create_record(tables["plan"], feishu_fields)
    except Exception as exc:
        # Roll back local DB record if Feishu creation fails
        with Session(db._get_engine()) as s:
            plan_row = s.execute(select(Plan).where(Plan.plan_code == plan_code)).scalar_one_or_none()
            if plan_row:
                s.delete(plan_row)
                s.commit()
        raise HTTPException(502, f"Failed to create Feishu plan record: {exc}")

    # Store feishu_record_id in local DB
    with Session(db._get_engine()) as s:
        plan_row = s.execute(select(Plan).where(Plan.plan_code == plan_code)).scalar_one()
        plan_row.feishu_record_id = feishu_record_id
        s.commit()

    # Launch ContentGenerationHandler in background
    background_tasks.add_task(
        _run_generation, gen_handler, plan_code, feishu_record_id, tables
    )

    db.log_task("plan", 0, "INFO", f"Admin manually created plan, triggering generation",
                entity_code=plan_code)

    return CreatePlanResponse(ok=True, plan_code=plan_code, feishu_record_id=feishu_record_id,
                              message="任务已提交，后台生成中")


def _generate_plan_code(s: Session, extra_offset: int = 0) -> str:
    today = datetime.now().strftime("%y%m%d")
    prefix = f"T_{today}_"
    count = s.execute(
        select(func.count()).select_from(Plan).where(Plan.plan_code.startswith(prefix))
    ).scalar_one()
    return f"T_{today}_{count + 1 + extra_offset:03d}"


def _run_generation(gen_handler, plan_code: str, feishu_record_id: str, tables: dict):
    from core.task import Task, TASK_CONTENT_GENERATION
    task = Task(
        task_type=TASK_CONTENT_GENERATION,
        table_id=tables["plan"],
        record_id=feishu_record_id,
        payload={"plan_code": plan_code},
    )
    task.extra = {"plan_code": plan_code}
    try:
        gen_handler(task)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("Background generation failed for %s: %s", plan_code, exc, exc_info=True)
        db.log_task("plan", 0, "ERROR", f"Background generation failed: {exc}", entity_code=plan_code)


@router.get("/{plan_code}", response_model=PlanOut)
def get_plan(plan_code: str):
    with Session(db._get_engine()) as s:
        plan = s.execute(
            select(Plan).where(Plan.plan_code == plan_code)
        ).scalar_one_or_none()
        if plan is None:
            raise HTTPException(404, f"Plan {plan_code!r} not found")
        return PlanOut.model_validate(plan)


@router.post("/{plan_code}/retry")
def retry_plan(plan_code: str):
    """Reset a failed plan back to 待执行."""
    plan_id = db.update_plan_status(plan_code, "待执行", error_msg="")
    if plan_id is None:
        raise HTTPException(404, f"Plan {plan_code!r} not found")
    return {"ok": True, "plan_code": plan_code, "new_status": "待执行"}


@router.get("/{plan_code}/prompts", response_model=list[PromptOut])
def plan_prompts(plan_code: str):
    """Return all Prompt records linked to this plan."""
    with Session(db._get_engine()) as s:
        plan = s.execute(
            select(Plan).where(Plan.plan_code == plan_code)
        ).scalar_one_or_none()
        if plan is None:
            raise HTTPException(404, f"Plan {plan_code!r} not found")
        prompts = s.execute(
            select(Prompt)
            .where(Prompt.plan_id == plan.id)
            .order_by(Prompt.group_id, Prompt.prompt_type)
        ).scalars().all()
        return [PromptOut.model_validate(p) for p in prompts]


@router.get("/{plan_code}/logs", response_model=list[TaskLogOut])
def plan_logs(plan_code: str, limit: int = Query(100, ge=1, le=500)):
    with Session(db._get_engine()) as s:
        rows = s.execute(
            select(TaskLog)
            .where(TaskLog.entity_code == plan_code)
            .order_by(TaskLog.created_at.desc())
            .limit(limit)
        ).scalars().all()
        return [TaskLogOut.model_validate(r) for r in rows]
