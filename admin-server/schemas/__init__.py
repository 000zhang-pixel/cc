"""
Pydantic schemas for admin-server API responses.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class PlanOut(BaseModel):
    id: int
    plan_code: str
    task_name: str | None
    task_type: str
    exec_status: str
    started_at: datetime | None
    finished_at: datetime | None
    error_msg: str | None
    synced_at: datetime | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class ContentOut(BaseModel):
    id: int
    content_code: str
    plan_id: int | None
    task_type: str | None
    target_platform: str | None
    content_type: str | None
    content_form: str | None
    title: str | None
    body: str | None
    tags: str | None
    gen_status: str | None
    review_status: str | None
    migrate_status: str | None
    local_dir: str | None
    generated_at: datetime | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class PublishOut(BaseModel):
    id: int
    pub_code: str
    content_id: int | None
    publish_method: str | None
    pub_status: str | None
    scheduled_at: datetime | None
    published_at: datetime | None
    post_url: str | None
    notes: str | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class TaskLogOut(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    entity_code: str | None
    level: str
    message: str
    detail: str | None
    created_at: datetime | None

    model_config = {"from_attributes": True}


class SyncCursorOut(BaseModel):
    table_name: str
    last_sync_at: datetime | None
    sync_count: int | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class PagedResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: list[Any]


class SkuOut(BaseModel):
    id: int
    sku_code: str
    sku_name: str
    product_alias: str | None
    display_name: str | None
    category: str | None
    model: str | None
    material: str | None
    color: str | None
    style: str | None
    target_audience: str | None
    selling_point_1: str | None
    selling_point_2: str | None
    selling_point_3: str | None
    price_range: float | None
    platforms: str | None
    listing_status: str | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class PromptOut(BaseModel):
    id: int
    prompt_code: str
    group_id: str | None
    prompt_type: str | None
    master_prompt: str | None
    sub_prompts: str | None
    status: str | None
    version: int | None
    model_used: str | None
    source: str | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class CreatePlanRequest(BaseModel):
    sku_id: int
    task_type: str
    target_platforms: list[str]
    img_count: int = 3
    img_per_post: int = 4
    video_count: int = 0
    video_min_sec: int = 5
    video_max_sec: int = 12
    tag_inject_n: int = 5
    text_model: str = "kimi-k2.5"
    image_model: str = "gpt-image-2"
    video_model: str = "volcengine-seedance"
    notes: str = ""


class CreatePlanResponse(BaseModel):
    ok: bool
    plan_code: str
    feishu_record_id: str | None = None
    message: str = ""


class ExecutePublishRequest(BaseModel):
    publish_method: str   # 得物自动发布 / 小红书手动 / 立即发布


class MigrateRequest(BaseModel):
    source_folder: str    # 素材源文件夹绝对路径
