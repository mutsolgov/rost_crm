from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Base
from app.main import create_app
from app.seed import seed_database


@pytest.fixture
def app(tmp_path: Path):
    application = create_app(Settings(
        database_url=f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        app_env="development",
        auth_mode="demo",
    ))
    Base.metadata.create_all(application.state.engine)
    with application.state.session_factory() as session:
        seed_database(session)
        session.commit()
    yield application
    application.state.engine.dispose()


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client

