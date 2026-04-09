import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool
from alembic import context

# Make project root importable so `db.models` can be resolved
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from db.models import Base, _default_db_path

config = context.config

if config.config_file_name is not None:
    # Only apply alembic's logging config when logging hasn't been set up yet
    # (i.e., when running alembic CLI directly, not from within the middleware process).
    import logging
    if not logging.root.handlers:
        fileConfig(config.config_file_name)

# Wire up ORM metadata for autogenerate
target_metadata = Base.metadata

# Use LOCAL_DB_PATH env var or platform default
_db_path = os.environ.get("LOCAL_DB_PATH") or _default_db_path()
config.set_main_option("sqlalchemy.url", f"sqlite:///{_db_path}")


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
