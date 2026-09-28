import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
import sqlalchemy as sa
from sqlalchemy import engine_from_config, event, pool

# Ensure backend directory is in sys.path
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.config import get_settings  # noqa: E402
from app.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def get_url() -> str:
    # 1. Explicitly configured option in alembic config (CLI -x, Config object, tests)
    cfg_url = config.get_main_option("sqlalchemy.url")
    if cfg_url and cfg_url.strip():
        return cfg_url.strip()
    # 2. Environment variable DATABASE_URL (Docker, production, CI)
    env_url = os.getenv("DATABASE_URL")
    if env_url and env_url.strip():
        return env_url.strip()
    # 3. Dynamic settings from app.config
    try:
        settings_url = get_settings().database_url
        if settings_url and settings_url.strip():
            return settings_url.strip()
    except Exception:
        pass
    return "postgresql+psycopg://rtk:rtk@localhost:5432/rtk_crm"


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    is_sqlite = url.startswith("sqlite")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=is_sqlite,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = config.attributes.get("connection", None)

    if connectable is None:
        url = get_url()
        is_sqlite = url.startswith("sqlite")
        configuration = config.get_section(config.config_ini_section, {})
        configuration["sqlalchemy.url"] = url

        engine_kwargs = {"prefix": "sqlalchemy."}
        if is_sqlite:
            engine_kwargs["poolclass"] = pool.StaticPool
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        else:
            engine_kwargs["poolclass"] = pool.NullPool

        connectable = engine_from_config(configuration, **engine_kwargs)

        if is_sqlite:
            @event.listens_for(connectable, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=OFF")
                cursor.close()

        try:
            with connectable.connect() as connection:
                context.configure(
                    connection=connection,
                    target_metadata=target_metadata,
                    render_as_batch=is_sqlite,
                )

                with context.begin_transaction():
                    context.run_migrations()
        finally:
            connectable.dispose()
    else:
        is_sqlite = (
            connectable.dialect.name == "sqlite"
            if hasattr(connectable, "dialect")
            else str(getattr(connectable, "engine", connectable).url).startswith("sqlite")
        )
        if is_sqlite:
            connectable.execute(sa.text("PRAGMA foreign_keys=OFF"))
        context.configure(
            connection=connectable,
            target_metadata=target_metadata,
            render_as_batch=is_sqlite,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
