import sys
from pathlib import Path
from uuid import uuid4

backend_dir = Path(__file__).resolve().parents[2]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Base
from app.main import create_app
from app.seed import seed_database
from tests.e2e.helpers import (
    admin_headers,
    auth_headers,
    create_e2e_interaction,
    manager_headers,
    route_exists,
    supervisor_headers,
)


@pytest.fixture
def app(tmp_path: Path):
    db_file = tmp_path / f"e2e_test_{uuid4().hex[:8]}.db"
    application = create_app(
        Settings(
            database_url=f"sqlite:///{db_file.as_posix()}",
            app_env="development",
            auth_mode="demo",
        )
    )
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
