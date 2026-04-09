"""
db/migrate.py — programmatic Alembic runner.

Call db.run_migrations() on startup instead of create_all(),
so that schema changes are applied automatically via Alembic revisions.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


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
        command.upgrade(cfg, "head")
        logger.info("[Migrate] Alembic upgrade head completed")
    except Exception as exc:
        logger.error("[Migrate] Alembic upgrade failed: %s", exc)
        # Fall back to create_all so the app can still start
        logger.warning("[Migrate] Falling back to create_all()")
        from db.models import create_all
        create_all()
