"""
db/migrate.py — programmatic Alembic runner.

Call db.run_migrations() on startup instead of create_all(),
so that schema changes are applied automatically via Alembic revisions.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from db.models import Base, _default_db_path

logger = logging.getLogger(__name__)


_EXPECTED_TABLES = set(Base.metadata.tables.keys())


def _db_url() -> tuple[str, str]:
    db_path = os.environ.get("LOCAL_DB_PATH") or _default_db_path()
    return f"sqlite:///{db_path}", db_path


def _get_existing_tables(db_url: str) -> set[str]:
    engine = create_engine(db_url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _get_current_revision(db_url: str) -> str | None:
    engine = create_engine(db_url)
    try:
        inspector = inspect(engine)
        if "alembic_version" not in inspector.get_table_names():
            return None
        with engine.connect() as conn:
            return conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).scalar_one_or_none()
    finally:
        engine.dispose()


def _stamp_if_initialized_but_unversioned(cfg) -> bool:
    """
    Legacy databases were sometimes created via Base.metadata.create_all(),
    which produced the full schema but no Alembic revision row.

    In that state `upgrade head` replays the initial migration and fails on the
    first CREATE TABLE. If the full expected schema already exists, stamp the
    current head first, then continue with normal upgrades.
    """
    db_url, db_path = _db_url()
    existing_tables = _get_existing_tables(db_url)
    current_revision = _get_current_revision(db_url)

    if current_revision:
        return False

    user_tables = existing_tables - {"alembic_version"}
    if not user_tables:
        return False

    missing_tables = _EXPECTED_TABLES - user_tables
    if missing_tables:
        logger.warning(
            "[Migrate] Database has pre-existing tables but is not fully initialized; "
            "missing=%s db=%s",
            sorted(missing_tables),
            db_path,
        )
        return False

    from alembic import command

    logger.warning(
        "[Migrate] Detected initialized schema without Alembic revision; stamping head for db=%s",
        db_path,
    )
    command.stamp(cfg, "head")
    return True



def run_migrations() -> None:
    """
    Run `alembic upgrade head` programmatically.
    Safe to call on every startup — no-op if schema is already current.
    """
    try:
        from alembic.config import Config
        from alembic import command

        # alembic.ini lives at the project root (one level above this file)
        ini_path = str(Path(__file__).parent.parent / "alembic.ini")
        cfg = Config(ini_path)
        stamped = _stamp_if_initialized_but_unversioned(cfg)
        command.upgrade(cfg, "head")
        if stamped:
            logger.info("[Migrate] Alembic head stamped and upgrade completed")
        else:
            logger.info("[Migrate] Alembic upgrade head completed")
    except Exception as exc:
        logger.error("[Migrate] Alembic upgrade failed: %s", exc)
        # Fall back to create_all so the app can still start
        logger.warning("[Migrate] Falling back to create_all()")
        from db.models import create_all
        create_all()
