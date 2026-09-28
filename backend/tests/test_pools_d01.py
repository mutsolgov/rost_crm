"""Tests for TASK-D01: AnyIO thread limiter and SQLAlchemy QueuePool synchronization."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import anyio
import anyio.to_thread
import pytest
from sqlalchemy import text
from sqlalchemy.exc import TimeoutError as SATimeoutError
from sqlalchemy.pool import QueuePool, StaticPool

from app.config import Settings
from app.db import get_engine
from app.main import create_app


@pytest.mark.anyio
async def test_anyio_thread_limiter_synchronized_in_lifespan(tmp_path):
    """Verify that lifespan initializes AnyIO default thread limiter with 120 tokens
    and successfully handles full 120 concurrent workers without starvation deadlock.
    """
    app = create_app(Settings(
        database_url=f"sqlite:///{(tmp_path / 'limiter_test.db').as_posix()}",
        app_env="development",
        auth_mode="demo",
    ))
    try:
        async with app.router.lifespan_context(app):
            limiter = anyio.to_thread.current_default_thread_limiter()
            assert limiter.total_tokens == 120

            # Concurrency verification: AnyIO default limiter is 40 tokens.
            # With total_tokens=120, full 120 workers must run concurrently without deadlock.
            workers = 120
            barrier = threading.Barrier(workers)

            def sync_worker():
                barrier.wait(timeout=5)
                return True

            async with anyio.create_task_group() as tg:
                for _ in range(workers):
                    tg.start_soon(anyio.to_thread.run_sync, sync_worker)
    finally:
        app.state.engine.dispose()
        get_engine.cache_clear()


def test_sqlite_file_engine_queue_pool_and_pragmas(tmp_path):
    """Verify SQLite file engine uses QueuePool with pool_size=30, max_overflow=90, and WAL pragmas."""
    db_file = (tmp_path / "queue_pool.db").as_posix()
    engine = get_engine(f"sqlite:///{db_file}")

    try:
        assert isinstance(engine.pool, QueuePool)
        assert engine.pool.size() == 30
        assert engine.pool._max_overflow == 90
        assert engine.pool._timeout == 30

        with engine.connect() as conn:
            journal_mode = conn.execute(text("PRAGMA journal_mode")).scalar()
            assert str(journal_mode).lower() == "wal"

            busy_timeout = conn.execute(text("PRAGMA busy_timeout")).scalar()
            assert busy_timeout == 30000

            synchronous = conn.execute(text("PRAGMA synchronous")).scalar()
            assert synchronous == 1  # 1 corresponds to NORMAL in SQLite

            foreign_keys = conn.execute(text("PRAGMA foreign_keys")).scalar()
            assert foreign_keys == 1
    finally:
        engine.dispose()
        get_engine.cache_clear()


def test_sqlite_memory_engine_uses_static_pool():
    """Verify in-memory SQLite uses StaticPool without raising pool argument errors and enables foreign keys."""
    engine = get_engine("sqlite:///:memory:")
    try:
        assert isinstance(engine.pool, StaticPool)
        with engine.connect() as conn:
            foreign_keys = conn.execute(text("PRAGMA foreign_keys")).scalar()
            assert foreign_keys == 1
    finally:
        engine.dispose()
        get_engine.cache_clear()


def test_postgres_engine_pool_configuration(monkeypatch):
    """Verify PostgreSQL engine is configured with pool_size=30, max_overflow=90, pool_timeout=30, and no SQLite connect_args
    for both psycopg2 and psycopg drivers.
    """
    captured_calls = []

    from app import db as db_module
    orig_create_engine = db_module.create_engine

    def fake_create_engine(url, **kwargs):
        captured_calls.append((url, kwargs))
        return orig_create_engine("sqlite:///:memory:", poolclass=StaticPool)

    monkeypatch.setattr(db_module, "create_engine", fake_create_engine)
    get_engine.cache_clear()
    try:
        for pg_url in [
            "postgresql+psycopg2://user:pass@localhost:5432/crm_test",
            "postgresql+psycopg://rtk_crm:secret@postgres:5432/rtk_crm",
        ]:
            get_engine(pg_url)
            get_engine.cache_clear()

        assert len(captured_calls) == 2
        for url, options in captured_calls:
            assert options["pool_size"] == 30
            assert options["max_overflow"] == 90
            assert options["pool_timeout"] == 30
            assert options["pool_pre_ping"] is True
            assert "connect_args" not in options
    finally:
        get_engine.cache_clear()


def test_sqlite_concurrent_connections_exceeding_old_pool_limit(tmp_path):
    """Adversarial Advisory 1 verification:
    Verify QueuePool can handle full 120 simultaneous checked-out connections without starvation.
    The old configuration (pool_size=5, max_overflow=10 = 15 total) starved and timed out on >15 threads.
    With pool_size=30 + max_overflow=90 = 120 total, 120 concurrent connections fully exercise
    both the base pool (30) and the entire overflow capacity (90).
    """
    db_file = (tmp_path / "concurrent_pool.db").as_posix()
    engine = get_engine(f"sqlite:///{db_file}")

    with engine.connect() as init_conn:
        init_conn.execute(text("CREATE TABLE ping (id INT)"))
        init_conn.commit()

    workers_count = 120
    barrier = threading.Barrier(workers_count)
    checked_out_levels = []
    overflow_levels = []

    def worker(idx):
        with engine.connect() as conn:
            barrier.wait(timeout=5)
            checked_out_levels.append(engine.pool.checkedout())
            overflow_levels.append(engine.pool.overflow())
            return conn.execute(text("SELECT 1")).scalar()

    try:
        with ThreadPoolExecutor(max_workers=workers_count) as executor:
            results = list(executor.map(worker, range(workers_count)))

        assert len(results) == workers_count
        assert all(r == 1 for r in results)
        assert max(checked_out_levels) == 120, "Expected all 120 connections to be simultaneously checked out"
        assert max(overflow_levels) == 90, "Expected max_overflow (90) to be fully utilized at peak"
    finally:
        engine.dispose()
        get_engine.cache_clear()


def test_sqlite_pool_saturation_and_timeout(tmp_path):
    """Verify that when 120 connections are actively checked out, an additional 121st connection
    request times out and raises SQLAlchemy TimeoutError, proving pool size + overflow boundary.
    """
    db_file = (tmp_path / "timeout_pool.db").as_posix()
    engine = get_engine(f"sqlite:///{db_file}")

    with engine.connect() as init_conn:
        init_conn.execute(text("CREATE TABLE ping (id INT)"))
        init_conn.commit()

    # Shorten pool_timeout for fast deterministic test execution
    engine.pool._timeout = 0.3

    workers = 121
    barrier_120 = threading.Barrier(120)
    timed_out_indices = []

    def worker(idx):
        try:
            with engine.connect() as conn:
                if idx < 120:
                    barrier_120.wait(timeout=2)
                    time.sleep(0.5)
                conn.execute(text("SELECT 1"))
        except SATimeoutError:
            timed_out_indices.append(idx)

    try:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            list(executor.map(worker, range(workers)))

        assert len(timed_out_indices) == 1, "Exactly 1 worker beyond 120 must time out"
        assert timed_out_indices[0] == 120, "Worker #120 (the 121st worker) must be the timed out one"
    finally:
        engine.dispose()
        get_engine.cache_clear()
