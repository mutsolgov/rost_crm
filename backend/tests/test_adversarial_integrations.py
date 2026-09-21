"""Adversarial stress test suite for Resilient Integrations Contour.

Empirical verification of:
1. Deduplication engine under repeated and concurrent sync operations.
2. Direct database unique constraint enforcement (uq_inbox_dedup, uq_learning_metric_source_external).
3. Reconciliation engine already-resolved conflict defense (409 Conflict).
4. Idempotency-Key replay attack defense (cached replay on match, 409 IDEMPOTENCY_CONFLICT on payload mismatch).
5. Validation boundaries on Idempotency-Key (empty, whitespace, >200 chars).
6. 152-FZ manager and admin scope isolation on interactions created via reconciliation (strictly 404).
7. Demand metrics multi-tenant scope isolation (manager-a cannot see org-2 metrics).
8. RBAC gatekeeper enforcement (403 Forbidden for line managers on all admin endpoints).
"""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import (
    IntegrationInbox,
    Interaction,
    LearningMetric,
    utcnow,
)


def headers(user="supervisor", key=None):
    res = {"X-Demo-User": user}
    if key:
        res["Idempotency-Key"] = key
    return res


# ==============================================================================
# 1. Deduplication Engine Stress Tests
# ==============================================================================

def test_deduplication_repeated_sequential_sync(client, app):
    """Stress test: 10 repeated syncs of LMS and Website produce 0 duplicate records."""
    for i in range(10):
        res_lms = client.post("/api/v1/integrations/sync/lms", headers=headers("supervisor"))
        assert res_lms.status_code == 200
        lms_json = res_lms.json()
        if i == 0:
            assert lms_json["received_count"] == 12
            assert lms_json["processed_count"] == 12
            assert lms_json["skipped_count"] == 0
        else:
            assert lms_json["received_count"] == 12
            assert lms_json["processed_count"] == 0
            assert lms_json["skipped_count"] == 12

        res_web = client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
        assert res_web.status_code == 200
        web_json = res_web.json()
        if i == 0:
            assert web_json["received_count"] == 4
            assert web_json["pending_count"] == 4
            assert web_json["skipped_count"] == 0
        else:
            assert web_json["received_count"] == 4
            assert web_json["pending_count"] == 0
            assert web_json["skipped_count"] == 4

    # Empirical assertion on DB state: strictly 12 metrics and 16 inbox items
    with app.state.session_factory() as session:
        metric_count = session.scalar(select(func.count(LearningMetric.id)))
        assert metric_count == 12, f"Expected exactly 12 metrics, found {metric_count}"

        inbox_count = session.scalar(select(func.count(IntegrationInbox.id)))
        assert inbox_count == 16, f"Expected exactly 16 inbox items, found {inbox_count}"

        # Ensure no duplicates on composite key
        dup_query = (
            select(
                IntegrationInbox.source,
                IntegrationInbox.entity_type,
                IntegrationInbox.external_id,
                IntegrationInbox.source_revision,
                func.count(IntegrationInbox.id).label("cnt"),
            )
            .group_by(
                IntegrationInbox.source,
                IntegrationInbox.entity_type,
                IntegrationInbox.external_id,
                IntegrationInbox.source_revision,
            )
            .having(func.count(IntegrationInbox.id) > 1)
        )
        duplicates = list(session.execute(dup_query))
        assert len(duplicates) == 0, f"Found duplicate inbox entries: {duplicates}"


def test_deduplication_concurrent_sync_with_idempotency_key(client, app):
    """Stress test: Concurrently firing sync requests with Idempotency-Key handles race conditions safely."""
    key = str(uuid4())

    def run_sync():
        return client.post("/api/v1/integrations/sync/lms", headers=headers("supervisor", key))

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(run_sync) for _ in range(4)]
        results = [f.result() for f in futures]

    # At least one request succeeds (200), others either get cached 200 or 409 IDEMPOTENCY_CONFLICT
    status_codes = [r.status_code for r in results]
    assert 200 in status_codes
    for code in status_codes:
        assert code in (200, 409)

    # Database strictly has 12 metrics and 12 inbox items (no duplicates)
    with app.state.session_factory() as session:
        metric_count = session.scalar(select(func.count(LearningMetric.id)))
        assert metric_count == 12
        inbox_count = session.scalar(select(func.count(IntegrationInbox.id)))
        assert inbox_count == 12


def test_deduplication_concurrent_sync_without_key_db_safety(client, app):
    """Stress test: Concurrently firing uncoordinated syncs without Idempotency-Key.
    
    Database UNIQUE constraint ensures that even if race condition occurs on commit,
    zero duplicate rows are persisted into IntegrationInbox or LearningMetric.
    """
    def run_sync():
        return client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(run_sync) for _ in range(4)]
        results = []
        for f in futures:
            try:
                results.append(f.result())
            except Exception as e:
                # Thread raised exception during race
                results.append(e)

    # Invariant: Database state MUST NEVER contain duplicate inbox records
    with app.state.session_factory() as session:
        inbox_count = session.scalar(select(func.count(IntegrationInbox.id)))
        assert inbox_count == 4, f"Expected 4 website inbox items, found {inbox_count}"


def test_deduplication_database_constraint_enforcement(app):
    """Stress test: Database UNIQUE constraint (uq_inbox_dedup) rejects duplicate entries at DB layer."""
    with app.state.session_factory() as session:
        # First entry
        entry1 = IntegrationInbox(
            id=str(uuid4()),
            source="lms",
            entity_type="learning_metric",
            external_id="ext-adversarial-1",
            source_revision="rev-1",
            payload={"test": "data"},
            status="pending",
            received_at=utcnow(),
        )
        session.add(entry1)
        session.commit()

        # Duplicate entry with different UUID but identical composite key
        entry2 = IntegrationInbox(
            id=str(uuid4()),
            source="lms",
            entity_type="learning_metric",
            external_id="ext-adversarial-1",
            source_revision="rev-1",
            payload={"test": "data-modified"},
            status="pending",
            received_at=utcnow(),
        )
        session.add(entry2)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_deduplication_learning_metric_constraint(app):
    """Stress test: Database UNIQUE constraint rejects duplicate source+external_id in LearningMetric."""
    with app.state.session_factory() as session:
        m1 = LearningMetric(
            id=str(uuid4()),
            organization_id="org-1",
            program_id="program-devops",
            metric_code="active_cohorts",
            value=5.0,
            unit="cohorts",
            as_of=utcnow(),
            source="lms",
            external_id="metric-unique-001",
            created_at=utcnow(),
        )
        session.add(m1)
        session.commit()

        m2 = LearningMetric(
            id=str(uuid4()),
            organization_id="org-1",
            program_id="program-devops",
            metric_code="students_enrolled",
            value=50.0,
            unit="students",
            as_of=utcnow(),
            source="lms",
            external_id="metric-unique-001",  # Same external_id & source!
            created_at=utcnow(),
        )
        session.add(m2)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


# ==============================================================================
# 2. Reconciliation Engine Conflict & Re-resolution Defense (409 Conflict)
# ==============================================================================

def test_reconciliation_conflict_on_already_resolved(client):
    """Adversarial test: Attempting to resolve an already-processed item via any action yields 409 Conflict."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    assert len(inbox["items"]) >= 2
    item1 = inbox["items"][0]
    item2 = inbox["items"][1]

    # 1. Resolve item1 via link_existing
    res1 = client.post(
        f"/api/v1/integrations/inbox/{item1['id']}/resolve",
        headers=headers("supervisor", "key-first-resolve"),
        json={"action": "link_existing", "organization_id": "org-1", "owner_id": "manager-a", "create_interaction": True},
    )
    assert res1.status_code == 200

    # Attempt to re-resolve item1 with action: reject -> Must return 409 Conflict
    res_re_reject = client.post(
        f"/api/v1/integrations/inbox/{item1['id']}/resolve",
        headers=headers("supervisor", "key-attack-1"),
        json={"action": "reject", "reason": "Tainted resolve attempt"},
    )
    assert res_re_reject.status_code == 409
    err = res_re_reject.json()["error"]
    assert "уже обработана" in err["message"]
    assert err["code"] == "VALIDATION_ERROR"

    # Attempt to re-resolve item1 with action: create_new -> Must return 409 Conflict
    res_re_new = client.post(
        f"/api/v1/integrations/inbox/{item1['id']}/resolve",
        headers=headers("supervisor", "key-attack-2"),
        json={"action": "create_new", "organization_name": "Хакерский Вуз"},
    )
    assert res_re_new.status_code == 409

    # 2. Resolve item2 via reject
    res2 = client.post(
        f"/api/v1/integrations/inbox/{item2['id']}/resolve",
        headers=headers("supervisor", "key-reject-resolve"),
        json={"action": "reject", "reason": "Первичный отказ"},
    )
    assert res2.status_code == 200

    # Attempt to re-resolve item2 with action: link_existing -> Must return 409 Conflict
    res_re_link = client.post(
        f"/api/v1/integrations/inbox/{item2['id']}/resolve",
        headers=headers("supervisor", "key-attack-3"),
        json={"action": "link_existing", "organization_id": "org-2"},
    )
    assert res_re_link.status_code == 409


def test_reconciliation_cannot_resolve_learning_metric_inbox_item(client):
    """Adversarial test: Attempting to resolve a learning_metric inbox item returns Validation Error."""
    client.post("/api/v1/integrations/sync/lms", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?source=lms", headers=headers("supervisor")).json()
    assert len(inbox["items"]) > 0
    metric_item = inbox["items"][0]

    res = client.post(
        f"/api/v1/integrations/inbox/{metric_item['id']}/resolve",
        headers=headers("supervisor", str(uuid4())),
        json={"action": "link_existing", "organization_id": "org-1"},
    )
    # Rejection occurs either because entity_type != application or because it's already processed
    assert res.status_code in (409, 422)
    assert "application" in res.json()["error"]["message"] or "уже обработана" in res.json()["error"]["message"]


def test_reconciliation_unknown_action_returns_validation_error(client):
    """Adversarial test: Unknown action returns 422 VALIDATION_ERROR."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    item = inbox["items"][0]

    res = client.post(
        f"/api/v1/integrations/inbox/{item['id']}/resolve",
        headers=headers("supervisor", str(uuid4())),
        json={"action": "arbitrary_exploit_action"},
    )
    assert res.status_code in (400, 422)
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


# ==============================================================================
# 3. Idempotency-Key Replay Attack & Conflict Verification
# ==============================================================================

def test_idempotency_key_replay_and_conflict_defense(client, app):
    """Adversarial test: Same key with identical payload succeeds; same key with altered payload yields 409 IDEMPOTENCY_CONFLICT."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    item = inbox["items"][0]

    shared_key = f"idemp-test-{uuid4()}"
    original_payload = {
        "action": "link_existing",
        "organization_id": "org-1",
        "owner_id": "manager-a",
        "create_interaction": True,
        "interaction_title": "Первоначальное взаимодействие",
    }

    # Step 1: Execute first command
    res1 = client.post(
        f"/api/v1/integrations/inbox/{item['id']}/resolve",
        headers=headers("supervisor", shared_key),
        json=original_payload,
    )
    assert res1.status_code == 200
    data1 = res1.json()
    inter_id = data1["interaction_id"]

    # Step 2: Exact same key and exact same payload -> Idempotent replay (200 OK)
    res2 = client.post(
        f"/api/v1/integrations/inbox/{item['id']}/resolve",
        headers=headers("supervisor", shared_key),
        json=original_payload,
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["interaction_id"] == inter_id

    # Step 3: Replay attack! Same key, altered payload (different owner_id) -> Must return 409 IDEMPOTENCY_CONFLICT
    altered_payload = {
        "action": "link_existing",
        "organization_id": "org-1",
        "owner_id": "manager-b",  # Attacker tries to switch owner!
        "create_interaction": True,
        "interaction_title": "Поддельное взаимодействие",
    }
    res3 = client.post(
        f"/api/v1/integrations/inbox/{item['id']}/resolve",
        headers=headers("supervisor", shared_key),
        json=altered_payload,
    )
    assert res3.status_code == 409
    err3 = res3.json()["error"]
    assert err3["code"] == "IDEMPOTENCY_CONFLICT"
    assert "уже использован с другим содержимым" in err3["message"]

    # Verify only 1 interaction was ever created
    with app.state.session_factory() as session:
        count = session.scalar(select(func.count(Interaction.id)).where(Interaction.id == inter_id))
        assert count == 1


def test_idempotency_key_validation_boundaries(client):
    """Adversarial test: Missing, empty, whitespace-only, and >200 chars Idempotency-Key rejected."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    item_id = inbox["items"][0]["id"]
    payload = {"action": "reject", "reason": "Test"}

    # Missing header
    res_none = client.post(f"/api/v1/integrations/inbox/{item_id}/resolve", headers={"X-Demo-User": "supervisor"}, json=payload)
    assert res_none.status_code in (400, 422)

    # Empty string
    res_empty = client.post(f"/api/v1/integrations/inbox/{item_id}/resolve", headers=headers("supervisor", ""), json=payload)
    assert res_empty.status_code in (400, 422)

    # Whitespace only
    res_ws = client.post(f"/api/v1/integrations/inbox/{item_id}/resolve", headers=headers("supervisor", "   "), json=payload)
    assert res_ws.status_code in (400, 422)

    # >200 characters (201 'a's)
    res_long = client.post(f"/api/v1/integrations/inbox/{item_id}/resolve", headers=headers("supervisor", "a" * 201), json=payload)
    assert res_long.status_code in (400, 422)


# ==============================================================================
# 4. RBAC Gatekeeper Enforcement (403 Forbidden for Managers)
# ==============================================================================

def test_rbac_manager_forbidden_on_all_integration_endpoints(client):
    """Adversarial test: Line manager gets 403 Forbidden on all integration control endpoints."""
    # GET /status
    r1 = client.get("/api/v1/integrations/status", headers=headers("manager-a"))
    assert r1.status_code == 403
    assert r1.json()["error"]["code"] == "FORBIDDEN"

    # POST /sync/lms
    r2 = client.post("/api/v1/integrations/sync/lms", headers=headers("manager-a"))
    assert r2.status_code == 403
    assert r2.json()["error"]["code"] == "FORBIDDEN"

    # POST /sync/website
    r3 = client.post("/api/v1/integrations/sync/website", headers=headers("manager-a"))
    assert r3.status_code == 403
    assert r3.json()["error"]["code"] == "FORBIDDEN"

    # GET /inbox
    r4 = client.get("/api/v1/integrations/inbox", headers=headers("manager-a"))
    assert r4.status_code == 403
    assert r4.json()["error"]["code"] == "FORBIDDEN"

    # POST /inbox/{id}/resolve
    r5 = client.post(
        "/api/v1/integrations/inbox/dummy-id/resolve",
        headers=headers("manager-a", str(uuid4())),
        json={"action": "reject"},
    )
    assert r5.status_code == 403
    assert r5.json()["error"]["code"] == "FORBIDDEN"


# ==============================================================================
# 5. 152-FZ Scope Isolation on Reconciled Interactions
# ==============================================================================

def test_152_fz_manager_and_admin_isolation_on_reconciled_interaction(client):
    """Adversarial test: Interaction created via reconciliation is strictly isolated.
    
    Manager-a owns it.
    Manager-b receives 404 on GET, PATCH, comments, transitions, attachments.
    Administrator receives 404 (no implicit business scope).
    """
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    item = inbox["items"][0]

    # Supervisor resolves application and assigns to manager-a
    res_resolve = client.post(
        f"/api/v1/integrations/inbox/{item['id']}/resolve",
        headers=headers("supervisor", str(uuid4())),
        json={
            "action": "link_existing",
            "organization_id": "org-1",
            "owner_id": "manager-a",
            "create_interaction": True,
            "interaction_title": "152-FZ Scope Test Card",
        },
    )
    assert res_resolve.status_code == 200
    inter_id = res_resolve.json()["interaction_id"]

    # 1. Manager-A (legitimate owner) has full access
    get_a = client.get(f"/api/v1/interactions/{inter_id}", headers=headers("manager-a"))
    assert get_a.status_code == 200
    assert get_a.json()["owner_id"] == "manager-a"

    # 2. Manager-B (adversary from another scope) receives 404 on ALL operations
    get_b = client.get(f"/api/v1/interactions/{inter_id}", headers=headers("manager-b"))
    assert get_b.status_code == 404
    assert get_b.json()["error"]["code"] == "NOT_FOUND"

    patch_b = client.patch(
        f"/api/v1/interactions/{inter_id}",
        headers=headers("manager-b", str(uuid4())),
        json={"expected_revision": 1, "title": "Tampered Title"},
    )
    assert patch_b.status_code == 404
    assert patch_b.json()["error"]["code"] == "NOT_FOUND"

    comment_b = client.post(
        f"/api/v1/interactions/{inter_id}/comments",
        headers=headers("manager-b", str(uuid4())),
        json={"body": "Tampered comment", "expected_revision": 1},
    )
    assert comment_b.status_code == 404
    assert comment_b.json()["error"]["code"] == "NOT_FOUND"

    transition_b = client.post(
        f"/api/v1/interactions/{inter_id}/transitions",
        headers=headers("manager-b", str(uuid4())),
        json={"transition_code": "appointed_presentation", "expected_revision": 1},
    )
    assert transition_b.status_code == 404
    assert transition_b.json()["error"]["code"] == "NOT_FOUND"

    att_list_b = client.get(f"/api/v1/interactions/{inter_id}/attachments", headers=headers("manager-b"))
    assert att_list_b.status_code == 404
    assert att_list_b.json()["error"]["code"] == "NOT_FOUND"

    # 3. Technical Administrator receives 404 (no implicit business scope under 152-FZ)
    get_admin = client.get(f"/api/v1/interactions/{inter_id}", headers=headers("administrator"))
    assert get_admin.status_code == 404
    assert get_admin.json()["error"]["code"] == "NOT_FOUND"

    patch_admin = client.patch(
        f"/api/v1/interactions/{inter_id}",
        headers=headers("administrator", str(uuid4())),
        json={"expected_revision": 1, "title": "Admin Tamper"},
    )
    assert patch_admin.status_code == 404
    assert patch_admin.json()["error"]["code"] == "NOT_FOUND"


# ==============================================================================
# 6. Demand Metrics Scope Isolation (152-FZ on /metrics)
# ==============================================================================

def test_demand_metrics_scope_isolation_manager(client):
    """Adversarial test: Manager-a can only see metrics for org-1; accessing org-2 returns 0 metrics."""
    client.post("/api/v1/integrations/sync/lms", headers=headers("supervisor"))

    # Supervisor sees all 3 organizations
    res_sup = client.get("/api/v1/integrations/metrics", headers=headers("supervisor"))
    assert res_sup.status_code == 200
    org_ids_sup = {o["organization_id"] for o in res_sup.json()["by_organization"]}
    assert "org-1" in org_ids_sup
    assert "org-2" in org_ids_sup

    # Manager-A only sees org-1
    res_mgr_a = client.get("/api/v1/integrations/metrics", headers=headers("manager-a"))
    assert res_mgr_a.status_code == 200
    mgr_a_data = res_mgr_a.json()
    org_ids_a = {o["organization_id"] for o in mgr_a_data["by_organization"]}
    assert org_ids_a == {"org-1"}, f"Manager-a leaked metrics for other orgs: {org_ids_a}"
    assert all(m["organization_id"] == "org-1" for m in mgr_a_data["metrics"])

    # Manager-A explicitly requesting org-2 (which they have no grant for) gets 0 metrics
    res_mgr_a_org2 = client.get("/api/v1/integrations/metrics?organization_id=org-2", headers=headers("manager-a"))
    assert res_mgr_a_org2.status_code == 200
    mgr_a_org2_data = res_mgr_a_org2.json()
    assert mgr_a_org2_data["total_cohorts"] == 0
    assert mgr_a_org2_data["total_enrolled"] == 0
    assert len(mgr_a_org2_data["metrics"]) == 0
    assert len(mgr_a_org2_data["by_organization"]) == 0
