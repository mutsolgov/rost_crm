import concurrent.futures
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.db import Base
from app.models import BackgroundJob, CommandResult, Interaction, ReportRun, User, utcnow
from app.services import bump_authz_epoch, process_background_job


def headers(user="supervisor", key=None):
    res = {"X-Demo-User": user}
    if key is not None:
        res["Idempotency-Key"] = key
    return res


def test_zero_oracle_interactions_isolation(client, app):
    """
    152-FZ Zero-Oracle Invariant for Interactions:
    Foreign interaction IDs must produce HTTP 404 responses that are completely
    indistinguishable in HTTP status, error code, and error message from non-existent IDs.
    """
    # Manager A owns ix-1, ix-2, ix-3. Manager B owns ix-4, ix-5, ix-6.
    foreign_id = "ix-4"
    non_existent_id = "ix-99999-non-existent"

    with app.state.session_factory() as session:
        # Verify foreign_id exists in DB
        assert session.get(Interaction, foreign_id) is not None
        # Verify non_existent_id does NOT exist in DB
        assert session.get(Interaction, non_existent_id) is None

    # Endpoints to probe as manager-a
    endpoints = [
        ("GET", f"/api/v1/interactions/{foreign_id}", f"/api/v1/interactions/{non_existent_id}", None),
        ("PATCH", f"/api/v1/interactions/{foreign_id}", f"/api/v1/interactions/{non_existent_id}", {"expected_revision": 1, "title": "Hacked"}),
        ("POST", f"/api/v1/interactions/{foreign_id}/transitions", f"/api/v1/interactions/{non_existent_id}/transitions", {"transition_code": "to_meeting", "expected_revision": 1, "comment": "test"}),
        ("POST", f"/api/v1/interactions/{foreign_id}/comments", f"/api/v1/interactions/{non_existent_id}/comments", {"body": "Unauthorized comment", "expected_revision": 1}),
        ("POST", f"/api/v1/interactions/{foreign_id}/assignments", f"/api/v1/interactions/{non_existent_id}/assignments", {"owner_id": "manager-a", "expected_revision": 1, "reason": "Unauthorized assign"}),
        ("GET", f"/api/v1/interactions/{foreign_id}/attachments", f"/api/v1/interactions/{non_existent_id}/attachments", None),
        ("GET", f"/api/v1/interactions/{foreign_id}/deliveries", f"/api/v1/interactions/{non_existent_id}/deliveries", None),
    ]

    for method, foreign_url, fake_url, payload in endpoints:
        h = headers("manager-a", key="test-key-oracle")
        if method == "GET":
            resp_foreign = client.get(foreign_url, headers=h)
            resp_fake = client.get(fake_url, headers=h)
        elif method == "PATCH":
            resp_foreign = client.patch(foreign_url, json=payload, headers=h)
            resp_fake = client.patch(fake_url, json=payload, headers=h)
        elif method == "POST":
            resp_foreign = client.post(foreign_url, json=payload, headers=h)
            resp_fake = client.post(fake_url, json=payload, headers=h)

        # Both must return 404
        assert resp_foreign.status_code == 404, f"Failed on {method} {foreign_url}: got {resp_foreign.status_code}"
        assert resp_fake.status_code == 404, f"Failed on {method} {fake_url}: got {resp_fake.status_code}"

        # Error codes and messages must match identically (Zero-Oracle)
        err_foreign = resp_foreign.json().get("error", {})
        err_fake = resp_fake.json().get("error", {})
        assert err_foreign.get("code") == err_fake.get("code") == "NOT_FOUND"
        assert err_foreign.get("message") == err_fake.get("message") == "Взаимодействие не найдено."


def test_zero_oracle_background_jobs_isolation(client, app):
    """
    152-FZ Zero-Oracle Invariant for BackgroundJobs:
    Jobs created by another user must return strict 404 to non-privileged users,
    indistinguishable from a non-existent job ID.
    """
    # Manager A enqueues a job
    req_body = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "knowledge_cutoff": datetime.now(timezone.utc).isoformat(),
    }
    resp = client.post("/api/v1/jobs/reports/snapshot", json=req_body, headers=headers("manager-a"))
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    fake_job_id = "job-non-existent-uuid-9999"

    # Manager B attempts GET /api/v1/jobs/{job_id} vs fake_job_id
    resp_b_job = client.get(f"/api/v1/jobs/{job_id}", headers=headers("manager-b"))
    resp_b_fake = client.get(f"/api/v1/jobs/{fake_job_id}", headers=headers("manager-b"))

    assert resp_b_job.status_code == 404
    assert resp_b_fake.status_code == 404
    assert resp_b_job.json()["error"]["code"] == resp_b_fake.json()["error"]["code"] == "NOT_FOUND"
    assert resp_b_job.json()["error"]["message"] == resp_b_fake.json()["error"]["message"] == "Фоновая задача не найдена."

    # Manager B attempts GET /api/v1/jobs/{job_id}/download vs fake_job_id
    resp_b_dl = client.get(f"/api/v1/jobs/{job_id}/download?format=xlsx", headers=headers("manager-b"))
    resp_b_dl_fake = client.get(f"/api/v1/jobs/{fake_job_id}/download?format=xlsx", headers=headers("manager-b"))

    assert resp_b_dl.status_code == 404
    assert resp_b_dl_fake.status_code == 404
    assert resp_b_dl.json()["error"]["code"] == resp_b_dl_fake.json()["error"]["code"] == "NOT_FOUND"
    assert resp_b_dl.json()["error"]["message"] == resp_b_dl_fake.json()["error"]["message"] == "Фоновая задача не найдена."


def test_supervisor_cross_team_isolation_and_download(client, app):
    """
    Supervisor can view and download completed jobs of members of their own team,
    but gets 404 on jobs created by members of other teams.
    """
    with app.state.session_factory() as session:
        # Create supervisor-south in team 'south'
        south_sup = User(
            id="supervisor-south",
            keycloak_subject="south-sup-sub",
            name="Южный Руководитель",
            role="supervisor",
            team_id="south",
            active=True,
        )
        session.add(south_sup)
        session.commit()

    # Manager A (team 'north') enqueues a job
    req_body = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "knowledge_cutoff": datetime.now(timezone.utc).isoformat(),
    }
    resp = client.post("/api/v1/jobs/reports/snapshot", json=req_body, headers=headers("manager-a"))
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    # Process job to completed
    with app.state.session_factory() as session:
        job = process_background_job(session, job_id)
        assert job.status == "completed"

    # Supervisor North (same team as Manager A: 'north')
    # 1. Can view job status
    resp_sup_north = client.get(f"/api/v1/jobs/{job_id}", headers=headers("supervisor"))
    assert resp_sup_north.status_code == 200
    assert resp_sup_north.json()["status"] == "completed"

    # 2. Can download in all 4 formats
    for fmt in ("xlsx", "pdf", "csv", "json"):
        dl = client.get(f"/api/v1/jobs/{job_id}/download?format={fmt}", headers=headers("supervisor"))
        assert dl.status_code == 200, f"Supervisor failed downloading format {fmt}: {dl.text}"
        assert dl.headers["X-Report-Format"] == fmt

    # Supervisor South (team 'south' - DIFFERENT team)
    # 1. Querying job status returns strict 404
    resp_sup_south = client.get(f"/api/v1/jobs/{job_id}", headers=headers("supervisor-south"))
    assert resp_sup_south.status_code == 404
    assert resp_sup_south.json()["error"]["code"] == "NOT_FOUND"

    # 2. Downloading report returns strict 404
    dl_sup_south = client.get(f"/api/v1/jobs/{job_id}/download?format=xlsx", headers=headers("supervisor-south"))
    assert dl_sup_south.status_code == 404
    assert dl_sup_south.json()["error"]["code"] == "NOT_FOUND"
    assert dl_sup_south.json()["error"]["message"] == "Фоновая задача не найдена."


def test_idempotency_key_replay_and_concurrency(client, app):
    """
    Idempotency-Key validation:
    1. Exact replay returns 202 with identical job_id and Location header, no duplicate jobs created.
    2. Replay with altered payload returns 409 IDEMPOTENCY_CONFLICT.
    3. Multi-threaded race condition with same key creates exactly 1 job.
    4. Validation errors for invalid keys (empty, > 200 chars).
    """
    idempotency_key = "emp-challenge-idem-key-001"
    req_body_1 = {
        "as_of": "2026-06-01T12:00:00Z",
        "knowledge_cutoff": "2026-06-01T12:00:00Z",
        "organization_ids": ["org-1"],
    }

    # 1. Initial request
    resp1 = client.post(
        "/api/v1/jobs/reports/snapshot",
        json=req_body_1,
        headers=headers("manager-a", key=idempotency_key),
    )
    assert resp1.status_code == 202
    job_id_1 = resp1.json()["job_id"]
    loc_1 = resp1.headers["Location"]
    assert loc_1 == f"/api/v1/jobs/{job_id_1}"

    # 2. Exact replay
    resp2 = client.post(
        "/api/v1/jobs/reports/snapshot",
        json=req_body_1,
        headers=headers("manager-a", key=idempotency_key),
    )
    assert resp2.status_code == 202
    assert resp2.json()["job_id"] == job_id_1
    assert resp2.headers["Location"] == loc_1

    # Verify only ONE job in DB
    with app.state.session_factory() as session:
        jobs = session.scalars(select(BackgroundJob).where(BackgroundJob.id == job_id_1)).all()
        assert len(jobs) == 1
        cmd_count = session.scalar(select(func.count(CommandResult.id)).where(CommandResult.key == idempotency_key))
        assert cmd_count == 1

    # 3. Replay with modified payload -> 409 Conflict
    req_body_altered = dict(req_body_1)
    req_body_altered["as_of"] = "2026-07-01T12:00:00Z"
    resp_conflict = client.post(
        "/api/v1/jobs/reports/snapshot",
        json=req_body_altered,
        headers=headers("manager-a", key=idempotency_key),
    )
    assert resp_conflict.status_code == 409
    assert resp_conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    # 4. Multi-threaded race condition
    race_key = "emp-challenge-race-key-002"
    race_body = {
        "as_of": "2026-08-01T12:00:00Z",
        "knowledge_cutoff": "2026-08-01T12:00:00Z",
    }

    def fire_request():
        return client.post(
            "/api/v1/jobs/reports/snapshot",
            json=race_body,
            headers=headers("manager-a", key=race_key),
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(fire_request) for _ in range(5)]
        responses = [f.result() for f in futures]

    # Every response should either be 202 (first caller or replay) or 409 (in-flight conflict)
    job_ids = set()
    for r in responses:
        if r.status_code == 202:
            job_ids.add(r.json()["job_id"])
        else:
            assert r.status_code == 409
            assert r.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    # Exactly 1 unique job_id must have been produced
    assert len(job_ids) == 1
    created_job_id = list(job_ids)[0]

    with app.state.session_factory() as session:
        job_count = session.scalar(select(func.count(BackgroundJob.id)).where(BackgroundJob.id == created_job_id))
        assert job_count == 1

    # 5. Invalid / Boundary Idempotency Keys
    # Empty string
    r_empty = client.post("/api/v1/jobs/reports/snapshot", json=req_body_1, headers=headers("manager-a", key=""))
    assert r_empty.status_code == 422
    assert r_empty.json()["error"]["code"] == "VALIDATION_ERROR"

    # Whitespace only
    r_ws = client.post("/api/v1/jobs/reports/snapshot", json=req_body_1, headers=headers("manager-a", key="   "))
    assert r_ws.status_code == 422
    assert r_ws.json()["error"]["code"] == "VALIDATION_ERROR"

    # Exceeding 200 chars
    long_key = "x" * 201
    r_long = client.post("/api/v1/jobs/reports/snapshot", json=req_body_1, headers=headers("manager-a", key=long_key))
    assert r_long.status_code == 422
    assert r_long.json()["error"]["code"] == "VALIDATION_ERROR"


def test_temporal_authorization_revocation(client, app):
    """
    Temporal Authorization Revocation:
    When access policy state (authz_epoch) is bumped, any download of an earlier
    report job must immediately fail with HTTP 403 REPORT_SCOPE_CHANGED.
    """
    # 1. Enqueue and process a job as manager-a
    req_body = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "knowledge_cutoff": datetime.now(timezone.utc).isoformat(),
    }
    resp = client.post("/api/v1/jobs/reports/snapshot", json=req_body, headers=headers("manager-a"))
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    with app.state.session_factory() as session:
        job = process_background_job(session, job_id)
        assert job.status == "completed"

    # 2. Download succeeds initially
    dl1 = client.get(f"/api/v1/jobs/{job_id}/download?format=xlsx", headers=headers("manager-a"))
    assert dl1.status_code == 200

    # Also succeeds for team supervisor
    dl_sup = client.get(f"/api/v1/jobs/{job_id}/download?format=xlsx", headers=headers("supervisor"))
    assert dl_sup.status_code == 200

    # 3. Simulate security event: authz_epoch bump (e.g. role change, team transfer, org revocation)
    with app.state.session_factory() as session:
        bump_authz_epoch(session)
        session.commit()

    # 4. Immediate revocation: download is blocked for all users with HTTP 403
    dl_stale_mgr = client.get(f"/api/v1/jobs/{job_id}/download?format=xlsx", headers=headers("manager-a"))
    assert dl_stale_mgr.status_code == 403
    assert dl_stale_mgr.json()["error"]["code"] == "REPORT_SCOPE_CHANGED"
    assert dl_stale_mgr.json()["error"]["message"] == "Область видимости пользователя изменилась."

    dl_stale_sup = client.get(f"/api/v1/jobs/{job_id}/download?format=xlsx", headers=headers("supervisor"))
    assert dl_stale_sup.status_code == 403
    assert dl_stale_sup.json()["error"]["code"] == "REPORT_SCOPE_CHANGED"

    # 5. New job enqueued AFTER epoch bump succeeds
    resp_new = client.post("/api/v1/jobs/reports/snapshot", json=req_body, headers=headers("manager-a"))
    assert resp_new.status_code == 202
    new_job_id = resp_new.json()["job_id"]

    with app.state.session_factory() as session:
        new_job = process_background_job(session, new_job_id)
        assert new_job.status == "completed"

    dl_new = client.get(f"/api/v1/jobs/{new_job_id}/download?format=xlsx", headers=headers("manager-a"))
    assert dl_new.status_code == 200


def test_in_memory_jwt_invariant_source_and_bundle():
    """
    152-FZ / FSTEC #117 Invariant:
    Zero token persistence in Web Storage (localStorage/sessionStorage).
    Tokens must reside strictly in-memory.
    """
    root_dir = Path(__file__).resolve().parent.parent.parent
    frontend_src = root_dir / "frontend" / "src"
    frontend_dist = root_dir / "frontend" / "dist"

    # 1. Verify frontend/src:
    # No source file invokes setItem / getItem or writes tokens to localStorage / sessionStorage
    for src_file in frontend_src.rglob("*.[t,j]s*"):
        text = src_file.read_text(encoding="utf-8")
        assert ".setItem" not in text, f"Illegal Web Storage write found in {src_file}"
        assert ".getItem" not in text, f"Illegal Web Storage read found in {src_file}"
        if src_file.name != "ReferenceViews.tsx":
            assert "localStorage" not in text, f"Forbidden localStorage reference in {src_file}"
            assert "sessionStorage" not in text, f"Forbidden sessionStorage reference in {src_file}"

    # 2. Verify auth.tsx implementation:
    # Keycloak client is stored in React useRef (in-memory) and token is never persisted to storage
    auth_text = (frontend_src / "auth.tsx").read_text(encoding="utf-8")
    assert "useRef<Keycloak" in auth_text
    assert "Authorization: 'Bearer ' + client.token" in auth_text
    assert "localStorage" not in auth_text
    assert "sessionStorage" not in auth_text

    # 3. Verify built bundle frontend/dist:
    # Production bundle must contain zero calls to store auth tokens in localStorage or sessionStorage
    if frontend_dist.exists():
        for asset in frontend_dist.rglob("*.js"):
            bundle_text = asset.read_text(encoding="utf-8")
            # Verify no token storage calls
            forbidden_tokens = [
                'localStorage.setItem("token"',
                'localStorage.setItem("jwt"',
                'localStorage.setItem("access_token"',
                'localStorage.setItem("refresh_token"',
                'sessionStorage.setItem("token"',
                'sessionStorage.setItem("jwt"',
                'sessionStorage.setItem("access_token"',
                'sessionStorage.setItem("refresh_token"',
            ]
            for pattern in forbidden_tokens:
                assert pattern not in bundle_text, f"Token leakage pattern {pattern} in {asset}"
