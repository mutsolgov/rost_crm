from functools import lru_cache

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

from .config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine(url=None):
    url = url or get_settings().database_url
    options = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False, "timeout": 20}
        if ":memory:" in url:
            options["poolclass"] = StaticPool
    engine = create_engine(url, **options)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def sqlite_options(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=20000")
    return engine


def get_db(request: Request):
    with request.app.state.session_factory() as session:
        yield session


def runtime_settings(request: Request):
    return request.app.state.settings


def init_db():
    from . import models  # Register model metadata; schema creation is explicit only.
    Base.metadata.create_all(get_engine())
