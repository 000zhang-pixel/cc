"""
SQLAlchemy ORM models — shared between middleware and admin-server.

Database: SQLite (WAL mode), path configured via LOCAL_DB_PATH env var.
Default: D:/AI-Content-Hub/data/hub.db  (Windows)
         ~/openclaw/workspace/AI-Content-Hub/data/hub.db  (Mac)
"""
import os
import platform
from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Index,
    Integer, Text, Float, create_engine, event,
)
from sqlalchemy.orm import DeclarativeBase, relationship, Session


# ---------------------------------------------------------------------------
# Engine factory
# ---------------------------------------------------------------------------

def _default_db_path() -> str:
    system = platform.system()
    if system == "Windows":
        return "D:/AI-Content-Hub/data/hub.db"
    elif system == "Darwin":
        return str(Path.home() / "openclaw/workspace/AI-Content-Hub/data/hub.db")
    else:
        return str(Path.home() / "AI-Content-Hub/data/hub.db")


def make_engine(db_path: str | None = None):
    path = db_path or os.environ.get("LOCAL_DB_PATH") or _default_db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA journal_mode=WAL")
        dbapi_conn.execute("PRAGMA synchronous=NORMAL")
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
        dbapi_conn.execute("PRAGMA busy_timeout=5000")

    return engine


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

class Sku(Base):
    __tablename__ = "skus"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    feishu_record_id    = Column(Text, unique=True, nullable=False)
    sku_code            = Column(Text, unique=True, nullable=False)   # MC-IP15-001
    sku_name            = Column(Text, nullable=False)
    spu_code            = Column(Text)
    product_alias       = Column(Text)          # 产品简称，Prompt拼接用
    display_name        = Column(Text)          # 平台展示标题
    category            = Column(Text)          # 手机壳/手机挂架/其他
    model               = Column(Text)          # 适配机型
    material            = Column(Text)          # JSON数组
    color               = Column(Text)          # JSON数组
    style               = Column(Text)          # JSON数组
    target_audience     = Column(Text)          # JSON数组
    selling_point_1     = Column(Text)
    selling_point_2     = Column(Text)
    selling_point_3     = Column(Text)
    price_range         = Column(Float)
    platforms           = Column(Text)          # JSON数组 ["得物","小红书"]
    listing_status      = Column(Text, default="待上架")   # 待上架/已上架/下架
    white_bg_urls       = Column(Text)          # JSON数组，飞书附件URL
    synced_at           = Column(DateTime)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    plans               = relationship("Plan", back_populates="sku")
    contents            = relationship("Content", back_populates="sku")


class Plan(Base):
    __tablename__ = "plans"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    feishu_record_id    = Column(Text, unique=True)     # 同步后填入，本地创建时可为NULL
    plan_code           = Column(Text, unique=True, nullable=False)   # T_260404_020
    sku_id              = Column(Integer, ForeignKey("skus.id"))
    task_name           = Column(Text)
    task_type           = Column(Text, nullable=False)  # AI全创作/图片实拍+AI文案/视频实拍+AI文案
    content_types       = Column(Text)                  # JSON数组
    target_platforms    = Column(Text)                  # JSON数组
    img_count           = Column(Integer, default=3)
    img_per_post        = Column(Integer, default=4)
    video_count         = Column(Integer, default=0)
    video_min_sec       = Column(Integer)
    video_max_sec       = Column(Integer)
    tag_inject_n        = Column(Integer, default=5)
    text_model          = Column(Text)
    image_model         = Column(Text)
    video_model         = Column(Text)
    # 状态机（本地权威）
    exec_status         = Column(Text, default="待执行")  # 待执行/执行中/完成/失败
    confirmed_exec      = Column(Boolean, default=False)  # 已触发过（防重复）
    started_at          = Column(DateTime)
    finished_at         = Column(DateTime)
    error_msg           = Column(Text)
    notes               = Column(Text)
    synced_at           = Column(DateTime)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sku                 = relationship("Sku", back_populates="plans")
    contents            = relationship("Content", back_populates="plan")
    prompts             = relationship("Prompt", back_populates="plan")
    logs                = relationship("TaskLog",
                                       primaryjoin="and_(TaskLog.entity_type=='plan', "
                                                   "foreign(TaskLog.entity_id)==Plan.id)",
                                       viewonly=True)


class Prompt(Base):
    __tablename__ = "prompts"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    feishu_record_id    = Column(Text, unique=True)
    prompt_code         = Column(Text, unique=True, nullable=False)   # P_T_260329_089_img01_C
    plan_id             = Column(Integer, ForeignKey("plans.id"))
    sku_id              = Column(Integer, ForeignKey("skus.id"))
    group_id            = Column(Text)          # img01/vid01
    prompt_type         = Column(Text)          # 图文正文/图片生成/视频内容/视频脚本
    master_prompt       = Column(Text)          # 总Prompt
    sub_prompts         = Column(Text)          # JSON数组，每张图一条（_I 记录专用）
    version             = Column(Integer, default=1)
    source              = Column(Text)          # AI自动生成/人工编写/素材库反推
    model_used          = Column(Text)
    status              = Column(Text, default="草稿")  # 草稿/已确认/已使用/已废弃
    quality_score       = Column(Integer)
    synced_at           = Column(DateTime)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    plan                = relationship("Plan", back_populates="prompts")
    sku                 = relationship("Sku")


class Content(Base):
    __tablename__ = "contents"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    feishu_record_id    = Column(Text, unique=True)
    content_code        = Column(Text, unique=True, nullable=False)   # T_260404_020_img01
    plan_id             = Column(Integer, ForeignKey("plans.id"))
    sku_id              = Column(Integer, ForeignKey("skus.id"))
    task_type           = Column(Text)
    target_platform     = Column(Text)
    content_type        = Column(Text)
    content_form        = Column(Text)          # 单图文/图文/视频
    title               = Column(Text)
    body                = Column(Text)
    tags                = Column(Text)
    local_dir           = Column(Text)          # Pending_Content/{plan_code}/{group_id}/ 绝对路径
    # 状态机（本地权威）
    gen_status          = Column(Text, default="生成中")   # 生成中/已生成/生成失败
    migrate_needed      = Column(Boolean, default=False)
    migrate_status      = Column(Text)          # 待搬迁/搬迁中/已完成/搬迁失败
    review_status       = Column(Text, default="待审核")  # 待审核/已通过/已拒绝
    review_note         = Column(Text)
    error_msg           = Column(Text)
    generated_at        = Column(DateTime)
    synced_at           = Column(DateTime)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    plan                = relationship("Plan", back_populates="contents")
    sku                 = relationship("Sku", back_populates="contents")
    publish_records     = relationship("PublishRecord", back_populates="content")


class PublishRecord(Base):
    __tablename__ = "publish_records"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    feishu_record_id    = Column(Text, unique=True)
    pub_code            = Column(Text, unique=True, nullable=False)   # Pub_260404_020_img01
    content_id          = Column(Integer, ForeignKey("contents.id"))
    publish_method      = Column(Text, default="待定")  # 待定/得物自动发布/小红书手动/其他手动
    scheduled_at        = Column(DateTime)
    # 状态机（本地权威）
    pub_status          = Column(Text, default="待发布")  # 待发布/发布中/已发布/发布失败
    published_at        = Column(DateTime)
    post_url            = Column(Text)
    error_msg           = Column(Text)
    notes               = Column(Text)
    synced_at           = Column(DateTime)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    content             = relationship("Content", back_populates="publish_records")


class Material(Base):
    """飞书表6：素材知识库镜像"""
    __tablename__ = "materials"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    feishu_record_id    = Column(Text, unique=True, nullable=False)
    material_code       = Column(Text, unique=True)     # SM_YYMMDD_XXX
    source_url          = Column(Text)
    original_title      = Column(Text)
    original_body       = Column(Text)
    like_count          = Column(Integer)
    collect_count       = Column(Integer)
    # 中台识别字段
    source_platform     = Column(Text)          # 得物/小红书/其他
    content_form        = Column(Text)
    category            = Column(Text)
    content_type        = Column(Text)
    # AI分析结果
    title_formula       = Column(Text)
    body_structure      = Column(Text)
    emotion_triggers    = Column(Text)          # JSON数组
    selling_style       = Column(Text)
    composition_style   = Column(Text)
    color_tone          = Column(Text)
    scene_props         = Column(Text)
    tag_strategy        = Column(Text)
    # 状态
    analysis_status     = Column(Text, default="待分析")  # 待分析/分析中/已完成/分析失败
    applied_to_engine   = Column(Boolean, default=False)
    error_msg           = Column(Text)
    synced_at           = Column(DateTime)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Tag(Base):
    """飞书表7：标签库镜像"""
    __tablename__ = "tags"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    feishu_record_id    = Column(Text, unique=True, nullable=False)
    tag_code            = Column(Text, unique=True)     # Tag_YYMMDD_XXX
    tag_name            = Column(Text, nullable=False)  # 含#号，如 #手机壳
    platforms           = Column(Text)                  # JSON数组
    industry            = Column(Text)
    category            = Column(Text)
    topic_heat          = Column(Integer)
    weight_score        = Column(Integer)
    use_count           = Column(Integer, default=0)
    enabled             = Column(Boolean, default=True)
    last_updated_at     = Column(DateTime)
    synced_at           = Column(DateTime)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TaskLog(Base):
    """本地任务执行日志（不同步飞书）"""
    __tablename__ = "task_logs"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(Text, nullable=False)  # plan/content/publish_record/material
    entity_id   = Column(Integer, nullable=False)
    entity_code = Column(Text)                  # 便于识别，如 T_260404_020
    level       = Column(Text, nullable=False)  # INFO/WARNING/ERROR
    message     = Column(Text, nullable=False)
    detail      = Column(Text)                  # 完整堆栈 / API响应原文
    created_at  = Column(DateTime, default=datetime.utcnow)


class SyncCursor(Base):
    """飞书增量同步游标"""
    __tablename__ = "sync_cursors"

    table_name      = Column(Text, primary_key=True)   # feishu_plan / feishu_content / …
    last_sync_at    = Column(DateTime)
    last_page_token = Column(Text)                     # 飞书分页续传 token
    sync_count      = Column(Integer, default=0)       # 累计同步记录数
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------

Index("idx_plans_exec_status",          Plan.exec_status)
Index("idx_contents_gen_status",        Content.gen_status)
Index("idx_contents_review_status",     Content.review_status)
Index("idx_contents_plan_id",           Content.plan_id)
Index("idx_publish_records_pub_status", PublishRecord.pub_status)
Index("idx_publish_records_content_id", PublishRecord.content_id)
Index("idx_task_logs_entity",           TaskLog.entity_type, TaskLog.entity_id)
Index("idx_task_logs_created",          TaskLog.created_at)
Index("idx_tags_category_platform",     Tag.category, Tag.enabled)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_all(engine=None):
    """Create all tables. Safe to call multiple times (idempotent)."""
    eng = engine or make_engine()
    Base.metadata.create_all(eng)
    return eng


def get_session(engine=None) -> Session:
    from sqlalchemy.orm import sessionmaker
    eng = engine or make_engine()
    SessionLocal = sessionmaker(bind=eng, expire_on_commit=False)
    return SessionLocal()
