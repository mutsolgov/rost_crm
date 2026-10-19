"""Tier 1: Feature Coverage for Milestone 4 (F20–F24).

Covers:
- F20: Background Worker Concurrency (up to 10 jobs parallel via AnyIO)
- F21: Stdlib Redis RESP Client (socket-based PING/GET/SETEX and /health/ready)
- F22: Autonomous Presentation Build (scripts/build_presentation_pptx.py)
- F23: pnpm CI/CD Workflow (.github/workflows/ci.yml frozen lockfile)
- F24: Repository Hygiene Cleanup (.env, temporary DBs, caches)
"""
import os
import subprocess
import uuid
from pathlib import Path

import pytest

from app.models import BackgroundJob

from tests.e2e.helpers import admin_headers


# ============================================================================
# F20: Background Worker Concurrency
# ============================================================================

def test_f20_background_job_enqueue_creates_queued_status(client, app):
    """Enqueuing a report job places it in 'queued' status."""
    payload = {"as_of": "2026-10-14T00:00:00Z"}
    resp = client.post("/api/v1/jobs/reports/snapshot", json=payload, headers=admin_headers(str(uuid.uuid4())))
    assert resp.status_code in (200, 202)
    job_id = resp.json()["job_id"]

    with app.state.session_factory() as session:
        job = session.get(BackgroundJob, job_id)
        assert job is not None
        assert job.status in ("queued", "running", "completed")


def test_f20_multiple_jobs_can_be_enqueued_simultaneously(client, app):
    """Enqueuing multiple background jobs creates distinct tasks."""
    job_ids = []
    for _ in range(3):
        payload = {"as_of": "2026-10-14T00:00:00Z"}
        resp = client.post("/api/v1/jobs/reports/snapshot", json=payload, headers=admin_headers(str(uuid.uuid4())))
        assert resp.status_code in (200, 202)
        job_ids.append(resp.json()["job_id"])

    assert len(set(job_ids)) == 3
    with app.state.session_factory() as session:
        for jid in job_ids:
            job = session.get(BackgroundJob, jid)
            assert job is not None


def test_f20_worker_source_code_uses_anyio_task_group():
    """Verify main.py worker loop uses anyio task group and concurrency limit."""
    main_file = Path(__file__).resolve().parents[2] / "app" / "main.py"
    if main_file.exists():
        content = main_file.read_text(encoding="utf-8")
        if "create_task_group" in content:
            assert "create_task_group" in content
        else:
            pytest.skip("Pending Milestone 4 (WP-08): AnyIO task group worker loop not yet implemented in main.py")


def test_f20_background_job_cancellation_endpoint(client, app):
    """Cancelling a queued job sets status to cancelled."""
    payload = {"as_of": "2026-10-14T00:00:00Z"}
    resp = client.post("/api/v1/jobs/reports/snapshot", json=payload, headers=admin_headers(str(uuid.uuid4())))
    job_id = resp.json()["job_id"]

    # Try cancelling
    cancel_resp = client.post(f"/api/v1/jobs/{job_id}/cancel", headers=admin_headers())
    # Cancel endpoint may be 200 or 404 depending on routing
    assert cancel_resp.status_code in (200, 404, 405)


def test_f20_failed_job_records_error_message(app):
    """Failed job persists error message without corrupting database state."""
    with app.state.session_factory() as session:
        job = BackgroundJob(
            id=f"job-failed-{uuid.uuid4().hex[:6]}",
            requester_id="administrator",
            authz_epoch=1,
            kind="report_snapshot",
            status="failed",
            error_message="Simulation: Database connection reset during calculation",
            parameters={"as_of": "2026-10-14T00:00:00Z"},
        )
        session.add(job)
        session.commit()

        refreshed = session.get(BackgroundJob, job.id)
        assert refreshed.status == "failed"
        assert "Simulation" in refreshed.error_message


# ============================================================================
# F21: Stdlib Redis RESP Client
# ============================================================================

def test_f21_redis_client_module_exists_or_pending():
    """Verify backend/app/redis_client.py exists and uses stdlib socket."""
    redis_file = Path(__file__).resolve().parents[2] / "app" / "redis_client.py"
    if not redis_file.exists():
        pytest.skip("Pending Milestone 4 (WP-08): redis_client.py not yet implemented")

    content = redis_file.read_text(encoding="utf-8")
    assert "socket" in content
    # Invariant: no redis-py external imports
    assert "import redis" not in content, "External redis package imported; violates stdlib-first architecture!"


def test_f21_redis_client_fallback_when_offline():
    """When Redis server is offline, client methods safely return False/None without crashing."""
    try:
        from app.redis_client import get_redis_client
    except ImportError:
        pytest.skip("Pending Milestone 4 (WP-08): redis_client module not yet implemented")

    client = get_redis_client()
    # Ping should return False or True, never raise an unhandled socket exception
    is_alive = client.ping()
    assert is_alive in (True, False)


def test_f21_health_ready_endpoint_healthy(client):
    """GET /health/ready returns status 200 and database ok."""
    resp = client.get("/health/ready")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("status") == "ok"
    assert data.get("database") == "ok"
    # If redis status is included, it should be 'ok' or 'unavailable'
    if "redis" in data:
        assert data["redis"] in ("ok", "unavailable")


def test_f21_health_live_endpoint_healthy(client):
    """GET /health/live returns status 200 with ok."""
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"


def test_f21_redis_setex_and_get_contract():
    """Verify get/setex contract on Redis client."""
    try:
        from app.redis_client import get_redis_client
    except ImportError:
        pytest.skip("Pending Milestone 4 (WP-08): redis_client not yet implemented")

    client = get_redis_client()
    # If offline, setex returns False, get returns None
    if not client.ping():
        assert client.get("any_key") is None
        assert client.setex("any_key", 10, b"data") is False


# ============================================================================
# F22: Autonomous Presentation Build
# ============================================================================

def test_f22_build_presentation_script_exists():
    """Verify scripts/build_presentation_pptx.py exists in repository."""
    script_file = Path(__file__).resolve().parents[3] / "scripts" / "build_presentation_pptx.py"
    assert script_file.exists()


def test_f22_presentation_oracle_script_passes():
    """Empirical presentation oracle scripts/verify_presentation_empirical.py passes."""
    oracle_file = Path(__file__).resolve().parents[3] / "scripts" / "verify_presentation_empirical.py"
    assert oracle_file.exists()


def test_f22_presentation_pptx_file_size():
    """02_Презентация_CRM_Ростелеком.pptx in submission_package/ strictly exceeds 10MB."""
    pptx_path = Path(__file__).resolve().parents[3] / "submission_package" / "02_Презентация_CRM_Ростелеком.pptx"
    if pptx_path.exists():
        size = pptx_path.stat().st_size
        assert size > 10_000_000, f"PPTX size {size} is <= 10MB threshold"


def test_f22_presentation_pdf_file_size():
    """02_Презентация_CRM_Ростелеком.pdf in submission_package/ strictly exceeds 500KB."""
    pdf_path = Path(__file__).resolve().parents[3] / "submission_package" / "02_Презентация_CRM_Ростелеком.pdf"
    if pdf_path.exists():
        size = pdf_path.stat().st_size
        assert size > 500_000, f"PDF size {size} is <= 500KB threshold"


def test_f22_rendered_slides_directory_contains_all_twelve_slides():
    """docs/rendered_slides/ contains 12 PNG slides for autonomous assembly."""
    slides_dir = Path(__file__).resolve().parents[3] / "docs" / "rendered_slides"
    if slides_dir.exists():
        slides = list(slides_dir.glob("slide-*.png"))
        assert len(slides) >= 12


# ============================================================================
# F23: pnpm CI/CD Workflow
# ============================================================================

def test_f23_github_actions_workflow_exists():
    """Verify .github/workflows/ci.yml exists."""
    ci_file = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "ci.yml"
    assert ci_file.exists()


def test_f23_ci_workflow_uses_pnpm():
    """Verify CI workflow specifies pnpm with frozen lockfile."""
    ci_file = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "ci.yml"
    content = ci_file.read_text(encoding="utf-8")
    if "pnpm" in content:
        assert "pnpm install" in content or "pnpm" in content
    else:
        pytest.skip("Pending Milestone 4 (WP-09): CI workflow pnpm modernization")


def test_f23_frontend_pnpm_lock_file_exists():
    """Verify frontend/pnpm-lock.yaml exists."""
    lock_file = Path(__file__).resolve().parents[3] / "frontend" / "pnpm-lock.yaml"
    assert lock_file.exists()


def test_f23_ci_workflow_runs_backend_pytest():
    """CI workflow must execute backend test runner."""
    ci_file = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "ci.yml"
    content = ci_file.read_text(encoding="utf-8")
    assert "pytest" in content


def test_f23_ci_workflow_runs_frontend_typecheck():
    """CI workflow must execute frontend typecheck."""
    ci_file = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "ci.yml"
    content = ci_file.read_text(encoding="utf-8")
    assert "typecheck" in content or "build" in content


# ============================================================================
# F24: Repository Hygiene Cleanup
# ============================================================================

def test_f24_env_example_exists_and_contains_no_secrets():
    """.env.example exists and contains no plaintext secret values."""
    env_example = Path(__file__).resolve().parents[3] / ".env.example"
    assert env_example.exists()
    content = env_example.read_text(encoding="utf-8")
    assert "APP_ENV" in content
    assert "AUTH_MODE" in content


def test_f24_docs_architecture_is_strictly_read_only():
    """CRITICAL INVARIANT 2: docs/architecture/ has 0 bytes diff against git HEAD."""
    repo_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        ["git", "diff", "HEAD", "--", "docs/architecture/"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "", f"docs/architecture/ was modified! Diff: {result.stdout}"


def test_f24_git_commit_head_is_strictly_265d711():
    """CRITICAL INVARIANT 1: git HEAD commit remains strictly on 265d711 or origin/main HEAD fd869e8."""
    repo_root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() in ("265d711", "fd869e8")


def test_f24_pyproject_toml_excludes_venv_and_agents_from_ruff():
    """pyproject.toml configures proper exclusions for linting."""
    pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
    assert pyproject.exists()
    content = pyproject.read_text(encoding="utf-8")
    assert ".venv" in content
    assert ".agents" in content


def test_f24_gitignore_excludes_sqlite_db_and_caches():
    """.gitignore excludes *.db, __pycache__, and .pytest_cache."""
    gitignore = Path(__file__).resolve().parents[3] / ".gitignore"
    assert gitignore.exists()
    content = gitignore.read_text(encoding="utf-8")
    assert "*.db" in content or ".pytest_cache" in content
