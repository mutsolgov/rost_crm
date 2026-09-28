"""Tests for Background Jobs, Process Decoupling & Transactional Outbox (TASK-O01).

Verifies:
1. Full background job lifecycle: queued -> running -> completed with result_id.
2. Transactional outbox event creation (pending -> processed).
3. 152-FZ invariant: stale authz_epoch causes immediate cancellation with REPORT_SCOPE_CHANGED.
4. 152-FZ visibility scoping: unauthorized direct access returns 404 (no existence leak).
5. API endpoints: POST /api/v1/jobs/reports/snapshot (HTTP 202 Accepted) and GET /api/v1/jobs/{job_id}.
6. Supervisor and Administrator role-based access to background jobs.
7. Default parameter handling and edge cases (inactive requester, non-existent job).
"""
from datetime import datetime, timezone
import pytest
from sqlalchemy import select

from app.errors import APIError
from app.models import BackgroundJob, ReportRun, TransactionalOutbox, User, utcnow
from app.services import (
    bump_authz_epoch,
    enqueue_background_job,
    get_authz_epoch,
    get_background_job_scoped,
    get_frozen_report_rows,
    process_background_job,
)


def headers(user="manager-a", key=None):
    result = {"X-Demo-User": user}
    if key:
        result["Idempotency-Key"] = key
    return result


def test_background_job_full_lifecycle(app):
    """Verify queued -> running -> completed lifecycle, outbox transitions, and frozen report creation."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")
        initial_epoch = get_authz_epoch(session)

        # 1. Enqueue job
        params = {"as_of": "2026-06-30T00:00:00Z"}
        job = enqueue_background_job(session, user, kind="report_snapshot", parameters=params)

        assert job.id is not None
        assert job.kind == "report_snapshot"
        assert job.status == "queued"
        assert job.progress == 0
        assert job.requester_id == "manager-a"
        assert job.authz_epoch == initial_epoch
        assert job.result_id is None
        assert job.error_message is None

        # Verify pending transactional outbox record
        outbox = session.scalars(
            select(TransactionalOutbox).where(TransactionalOutbox.status == "pending")
        ).all()
        matching_outbox = [o for o in outbox if o.payload.get("job_id") == job.id]
        assert len(matching_outbox) == 1
        assert matching_outbox[0].event_type == "job_queued:report_snapshot"
        assert matching_outbox[0].processed_at is None

        # 2. Process job
        processed = process_background_job(session, job.id)
        assert processed.status == "completed"
        assert processed.progress == 100
        assert processed.result_id is not None
        assert processed.error_message is None

        # 3. Verify ReportRun was created and frozen rows exist
        report_run = session.get(ReportRun, processed.result_id)
        assert report_run is not None
        assert report_run.requested_by == "manager-a"
        assert report_run.report_type == "snapshot"

        frozen_rows = get_frozen_report_rows(session, processed.result_id)
        assert isinstance(frozen_rows, list)

        # 4. Verify transactional outbox transitioned to processed
        session.refresh(matching_outbox[0])
        assert matching_outbox[0].status == "processed"
        assert matching_outbox[0].processed_at is not None


def test_152fz_authz_epoch_cancellation(app):
    """152-FZ Security Invariant: rights change during queue wait cancels job with REPORT_SCOPE_CHANGED."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")

        # 1. Enqueue job under initial epoch
        params = {"as_of": "2026-06-30T00:00:00Z"}
        job = enqueue_background_job(session, user, kind="report_snapshot", parameters=params)
        job_epoch = job.authz_epoch

        # 2. Access policy epoch changes while job is queued (e.g., manager reassigned or role altered)
        new_epoch = bump_authz_epoch(session)
        assert new_epoch > job_epoch

        # 3. Worker picks up job for execution
        processed = process_background_job(session, job.id)

        # 4. Must be cancelled immediately without generating or leaking report data
        assert processed.status == "cancelled"
        assert processed.error_message == "REPORT_SCOPE_CHANGED"
        assert processed.result_id is None
        assert processed.progress < 100


def test_visibility_isolation_152fz_404(app, client):
    """152-FZ Isolation: other users receive 404 to avoid leaking existence of jobs."""
    with app.state.session_factory() as session:
        user_a = session.get(User, "manager-a")
        user_b = session.get(User, "manager-b")
        job = enqueue_background_job(session, user_a, kind="report_snapshot", parameters={"as_of": "2026-01-01T00:00:00Z"})
        job_id = job.id

        # Direct service call: manager-b cannot access manager-a's job
        with pytest.raises(APIError) as exc_info:
            get_background_job_scoped(session, user_b, job_id)
        assert exc_info.value.status_code == 404

        # Add supervisor for team-south to test cross-team supervisor isolation
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

        with pytest.raises(APIError) as exc_south:
            get_background_job_scoped(session, south_sup, job_id)
        assert exc_south.value.status_code == 404

        # Supervisor of manager-a's team ('north') CAN see the job
        supervisor_north = session.get(User, "supervisor")
        scoped_sup = get_background_job_scoped(session, supervisor_north, job_id)
        assert scoped_sup.id == job_id

        # Administrator CAN see any job
        admin = session.get(User, "administrator")
        scoped_admin = get_background_job_scoped(session, admin, job_id)
        assert scoped_admin.id == job_id

        # Creator manager-a CAN see the job
        scoped_own = get_background_job_scoped(session, user_a, job_id)
        assert scoped_own.id == job_id

    # HTTP API verification of 404 isolation
    # manager-b gets 404
    resp_b = client.get(f"/api/v1/jobs/{job_id}", headers=headers("manager-b"))
    assert resp_b.status_code == 404

    # manager-a gets 200
    resp_a = client.get(f"/api/v1/jobs/{job_id}", headers=headers("manager-a"))
    assert resp_a.status_code == 200
    assert resp_a.json()["id"] == job_id
    assert resp_a.json()["status"] == "queued"

    # supervisor gets 200
    resp_sup = client.get(f"/api/v1/jobs/{job_id}", headers=headers("supervisor"))
    assert resp_sup.status_code == 200

    # administrator gets 200
    resp_admin = client.get(f"/api/v1/jobs/{job_id}", headers=headers("administrator"))
    assert resp_admin.status_code == 200


def test_api_endpoints_enqueue_and_polling(app, client):
    """Verify POST /api/v1/jobs/reports/snapshot (202 Accepted) and GET /api/v1/jobs/{job_id} polling."""
    # 1. Enqueue via API
    req_body = {
        "as_of": "2026-06-30T00:00:00Z",
        "organization_ids": ["org-1"],
    }
    resp = client.post("/api/v1/jobs/reports/snapshot", json=req_body, headers=headers("manager-a"))
    assert resp.status_code == 202
    assert "Location" in resp.headers
    data = resp.json()
    job_id = data["job_id"]
    assert data["status"] == "queued"
    assert resp.headers["Location"] == f"/api/v1/jobs/{job_id}"

    # 2. Poll initial state
    resp_poll = client.get(f"/api/v1/jobs/{job_id}", headers=headers("manager-a"))
    assert resp_poll.status_code == 200
    poll_data = resp_poll.json()
    assert poll_data["id"] == job_id
    assert poll_data["status"] == "queued"
    assert poll_data["progress"] == 0
    assert poll_data["result_id"] is None

    # 3. Simulate worker background processing
    with app.state.session_factory() as session:
        process_background_job(session, job_id)

    # 4. Poll completed state
    resp_done = client.get(f"/api/v1/jobs/{job_id}", headers=headers("manager-a"))
    assert resp_done.status_code == 200
    done_data = resp_done.json()
    assert done_data["status"] == "completed"
    assert done_data["progress"] == 100
    assert done_data["result_id"] is not None
    assert done_data["error_message"] is None


def test_api_enqueue_default_parameters(app, client):
    """Verify POST /api/v1/jobs/reports/snapshot with empty/default body succeeds."""
    resp = client.post("/api/v1/jobs/reports/snapshot", json={}, headers=headers("supervisor"))
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    with app.state.session_factory() as session:
        job = process_background_job(session, job_id)
        assert job.status == "completed"
        assert job.progress == 100
        assert job.result_id is not None


def test_nonexistent_job_and_edge_cases(app, client):
    """Verify 404 for missing jobs, idempotent processing, and inactive requester handling."""
    # 1. Non-existent job GET returns 404
    resp = client.get("/api/v1/jobs/non-existent-uuid", headers=headers("administrator"))
    assert resp.status_code == 404

    with app.state.session_factory() as session:
        # 2. Direct process_background_job on missing id raises 404
        with pytest.raises(APIError) as exc_404:
            process_background_job(session, "missing-uuid")
        assert exc_404.value.status_code == 404

        # 3. Inactive requester cancels job
        user = session.get(User, "manager-b")
        job_inactive = enqueue_background_job(session, user, kind="report_snapshot", parameters={})
        user.active = False
        session.commit()

        # Inactive user cannot enqueue new jobs
        with pytest.raises(APIError) as exc_inactive:
            enqueue_background_job(session, user, kind="report_snapshot", parameters={})
        assert exc_inactive.value.status_code == 401

        processed_inactive = process_background_job(session, job_inactive.id)
        assert processed_inactive.status == "cancelled"
        assert processed_inactive.error_message == "REQUESTER_INACTIVE"

        # 4. Idempotent processing of already completed job
        user.active = True
        session.commit()
        job_normal = enqueue_background_job(session, user, kind="report_snapshot", parameters={})
        processed_first = process_background_job(session, job_normal.id)
        assert processed_first.status == "completed"

        # Calling again returns same job cleanly
        processed_second = process_background_job(session, job_normal.id)
        assert processed_second.status == "completed"
        assert processed_second.result_id == processed_first.result_id


def test_job_failure_on_invalid_parameters_and_outbox_transition(app):
    """Verify job failure handling, rollback safety, and outbox transition to processed on error."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")
        # Invalid parameters causing Pydantic ValidationError in SnapshotRequest
        job = enqueue_background_job(
            session,
            user,
            kind="report_snapshot",
            parameters={"as_of": "invalid-datetime-without-tz"},
        )
        job_id = job.id

        # Verify initial outbox entry is pending
        outbox = session.scalars(
            select(TransactionalOutbox).where(TransactionalOutbox.status == "pending")
        ).all()
        matching_outbox = [o for o in outbox if o.payload.get("job_id") == job_id]
        assert len(matching_outbox) == 1
        assert matching_outbox[0].status == "pending"

        # Process job - must cleanly catch exception, roll back, and mark job failed
        processed = process_background_job(session, job_id)
        assert processed.status == "failed"
        assert processed.error_message is not None
        assert processed.result_id is None

        # Verify outbox entry was NOT left orphaned as pending
        session.refresh(matching_outbox[0])
        assert matching_outbox[0].status == "processed"
        assert matching_outbox[0].processed_at is not None


def test_outbox_transitioned_on_epoch_and_inactive_cancellation(app):
    """Verify outbox entry transitions to processed when job is cancelled via 152-FZ epoch or inactive user."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")

        # Case 1: Cancelled via authz_epoch bump
        job1 = enqueue_background_job(session, user, kind="report_snapshot", parameters={"as_of": "2026-06-30T00:00:00Z"})
        bump_authz_epoch(session)
        processed1 = process_background_job(session, job1.id)
        assert processed1.status == "cancelled"
        assert processed1.error_message == "REPORT_SCOPE_CHANGED"

        outbox1 = session.scalars(
            select(TransactionalOutbox)
        ).all()
        matching1 = [o for o in outbox1 if o.payload.get("job_id") == job1.id]
        assert len(matching1) == 1
        assert matching1[0].status == "processed"
        assert matching1[0].processed_at is not None

        # Case 2: Cancelled via inactive requester
        user_b = session.get(User, "manager-b")
        job2 = enqueue_background_job(session, user_b, kind="report_snapshot", parameters={"as_of": "2026-06-30T00:00:00Z"})
        user_b.active = False
        session.commit()

        processed2 = process_background_job(session, job2.id)
        assert processed2.status == "cancelled"
        assert processed2.error_message == "REQUESTER_INACTIVE"

        outbox2 = session.scalars(
            select(TransactionalOutbox)
        ).all()
        matching2 = [o for o in outbox2 if o.payload.get("job_id") == job2.id]
        assert len(matching2) == 1
        assert matching2[0].status == "processed"
        assert matching2[0].processed_at is not None

        # Reset user_b
        user_b.active = True
        session.commit()


def test_idempotency_key_replay_on_snapshot_endpoint(app, client):
    """Verify Idempotency-Key prevents double enqueueing and replays HTTP 202 response."""
    key = "idemp-snapshot-test-key-001"
    req_body = {
        "as_of": "2026-06-30T00:00:00Z",
        "organization_ids": ["org-1"],
    }
    h = headers("manager-a", key=key)

    # First submission
    resp1 = client.post("/api/v1/jobs/reports/snapshot", json=req_body, headers=h)
    assert resp1.status_code == 202
    job_id_1 = resp1.json()["job_id"]
    location_1 = resp1.headers["Location"]
    assert location_1 == f"/api/v1/jobs/{job_id_1}"

    # Second submission with same Idempotency-Key
    resp2 = client.post("/api/v1/jobs/reports/snapshot", json=req_body, headers=h)
    assert resp2.status_code == 202
    job_id_2 = resp2.json()["job_id"]
    location_2 = resp2.headers.get("Location")

    assert job_id_1 == job_id_2
    assert location_1 == location_2

    # Verify only 1 background job exists in database with this id
    with app.state.session_factory() as session:
        jobs = session.scalars(
            select(BackgroundJob).where(BackgroundJob.id == job_id_1)
        ).all()
        assert len(jobs) == 1


def test_inactive_user_access_rejected_in_scoping(app):
    """Verify deactivated user is denied access to background jobs with 401 UNAUTHORIZED."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")
        job = enqueue_background_job(session, user, kind="report_snapshot", parameters={})
        job_id = job.id

        # Deactivate user
        user.active = False
        with pytest.raises(APIError) as exc_info:
            get_background_job_scoped(session, user, job_id)
        assert exc_info.value.status_code == 401
        assert exc_info.value.code == "UNAUTHORIZED"

        # Restore user
        user.active = True
        session.commit()


def test_152fz_authz_epoch_cancellation_during_execution(app, monkeypatch):
    """Verify that if authz_epoch is bumped DURING report calculation, job aborts with REPORT_SCOPE_CHANGED."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")
        job = enqueue_background_job(session, user, kind="report_snapshot", parameters={"as_of": "2026-06-30T00:00:00Z"})

        from app import services
        original_snapshot = services.snapshot

        def patched_snapshot(db, u, body):
            bump_authz_epoch(db)
            return original_snapshot(db, u, body)

        monkeypatch.setattr(services, "snapshot", patched_snapshot)

        processed = process_background_job(session, job.id)
        assert processed.status == "cancelled"
        assert processed.error_message == "REPORT_SCOPE_CHANGED"
        assert processed.result_id is None


def test_idempotency_key_replay_with_default_body(app, client):
    """Verify Idempotency-Key replay works on empty/default body without false-positive 409 conflict."""
    import time
    key = "idemp-default-body-key-999"
    h = headers("manager-a", key=key)

    resp1 = client.post("/api/v1/jobs/reports/snapshot", json={}, headers=h)
    assert resp1.status_code == 202
    job_id_1 = resp1.json()["job_id"]
    loc_1 = resp1.headers.get("Location")

    # Slight pause to ensure utcnow() would change if dynamically generated
    time.sleep(0.02)

    resp2 = client.post("/api/v1/jobs/reports/snapshot", json={}, headers=h)
    assert resp2.status_code == 202
    job_id_2 = resp2.json()["job_id"]
    loc_2 = resp2.headers.get("Location")

    assert job_id_1 == job_id_2
    assert loc_1 == loc_2


def test_concurrent_job_processing_atomic_cas(app):
    """Verify atomic CAS ensures two concurrent callers do not duplicate execution."""
    import threading
    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")
        job = enqueue_background_job(session, user, kind="report_snapshot", parameters={"as_of": "2026-06-30T00:00:00Z"})
        job_id = job.id

    results = []
    errors = []

    def worker_run():
        try:
            with app.state.session_factory() as s:
                res = process_background_job(s, job_id)
                results.append(res.status)
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=worker_run)
    t2 = threading.Thread(target=worker_run)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
    assert len(results) == 2
    assert all(status in ("running", "completed") for status in results)

    with app.state.session_factory() as session:
        final_job = session.get(BackgroundJob, job_id)
        assert final_job.status == "completed"
        assert final_job.result_id is not None
        # Verify exactly one ReportRun was created
        report_runs = session.scalars(select(ReportRun).where(ReportRun.id == final_job.result_id)).all()
        assert len(report_runs) == 1


def test_job_whitespace_handling_and_kind_validation(app, client):
    """Verify whitespace handling in job_id and rejection of invalid job kind."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")
        # Empty or whitespace kind raises 422
        with pytest.raises(APIError) as exc_kind:
            enqueue_background_job(session, user, kind="   ")
        assert exc_kind.value.status_code == 422

        job = enqueue_background_job(session, user, kind="report_snapshot", parameters={})
        job_id = job.id

        # Query with leading/trailing spaces
        scoped = get_background_job_scoped(session, user, f"  {job_id}  ")
        assert scoped.id == job_id

        # Process with leading/trailing spaces
        processed = process_background_job(session, f"  {job_id}  ")
        assert processed.id == job_id
        assert processed.status == "completed"

    # API call with leading/trailing spaces in URL
    resp = client.get(f"/api/v1/jobs/%20%20{job_id}%20%20", headers=headers("manager-a"))
    assert resp.status_code == 200
    assert resp.json()["id"] == job_id


def test_job_parameters_validation_and_datetime_serialization(app):
    """Verify non-dict parameters rejected with 422 and datetime objects in parameters serialize safely."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")

        # 1. Non-dict parameters rejected with 422
        for bad_param in ["not-a-dict", 12345, [1, 2, 3]]:
            with pytest.raises(APIError) as exc_info:
                enqueue_background_job(session, user, kind="report_snapshot", parameters=bad_param)
            assert exc_info.value.status_code == 422
            assert exc_info.value.code == "VALIDATION_ERROR"

        # 2. Datetime objects in parameters safely converted via _json_safe (no TypeError on commit)
        now_utc = datetime(2026, 6, 30, 12, 0, 0, tzinfo=timezone.utc)
        job = enqueue_background_job(
            session,
            user,
            kind="report_snapshot",
            parameters={"as_of": now_utc, "organization_ids": ["org-1"]},
        )
        assert job.id is not None
        assert isinstance(job.parameters, dict)
        assert job.parameters["as_of"] == "2026-06-30 12:00:00+00:00"

        # 3. Process job with datetime parameters successfully
        processed = process_background_job(session, job.id)
        assert processed.status == "completed"
        assert processed.progress == 100
        assert processed.result_id is not None

        # Verify ReportRun recorded resolved parameters
        report_run = session.get(ReportRun, processed.result_id)
        assert report_run is not None
        assert "as_of" in report_run.parameters


def test_api_timezone_validation_and_malformed_timestamps(app, client):
    """Verify API strictly enforces timezone-aware timestamps and rejects malformed dates with 422."""
    h = headers("manager-a")

    # 1. Naive timestamp without timezone rejected with 422
    resp_naive = client.post(
        "/api/v1/jobs/reports/snapshot",
        json={"as_of": "2026-06-30T12:00:00"},
        headers=h,
    )
    assert resp_naive.status_code == 422

    # 2. Malformed non-ISO timestamp rejected with 422
    resp_invalid = client.post(
        "/api/v1/jobs/reports/snapshot",
        json={"as_of": "invalid-datetime-value"},
        headers=h,
    )
    assert resp_invalid.status_code == 422

    # 3. Valid ISO-8601 with UTC timezone accepted with 202
    resp_valid = client.post(
        "/api/v1/jobs/reports/snapshot",
        json={"as_of": "2026-06-30T12:00:00Z"},
        headers=h,
    )
    assert resp_valid.status_code == 202
    assert "Location" in resp_valid.headers


def test_job_security_sql_injection_and_escaping(app, client):
    """Verify SQL injection payloads and malicious strings in job_id safely return 404 without leaking errors."""
    attack_payloads = [
        "' OR '1'='1",
        "'; DROP TABLE background_jobs; --",
        "<script>alert('xss')</script>",
        "../../../../etc/passwd",
        "%27%20OR%201=1--",
        "\\x00\\x27",
    ]

    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")
        for payload in attack_payloads:
            # Direct service call returns 404
            with pytest.raises(APIError) as exc_info:
                get_background_job_scoped(session, user, payload)
            assert exc_info.value.status_code == 404

            with pytest.raises(APIError) as exc_proc:
                process_background_job(session, payload)
            assert exc_proc.value.status_code == 404

    # HTTP API call returns 404
    for payload in attack_payloads:
        resp = client.get(f"/api/v1/jobs/{payload}", headers=headers("manager-a"))
        assert resp.status_code == 404

    # Verify database integrity: background_jobs table intact
    with app.state.session_factory() as session:
        count = session.scalars(select(BackgroundJob)).all()
        assert isinstance(count, list)




