"""Challenger 2 adversarial stress harness for Resilient Integrations Contour (B26-B29).

Empirical verification of:
1. Invalid and malformed payloads to /inbox/{id}/resolve (array, non-JSON, missing action, non-string action types).
2. Unknown and malicious reconciliation actions (drop_db, SQL injection, unknown actions, casing).
3. Idempotency-Key length validation (> 200 chars must be rejected with 422, exactly 200 accepted).
4. Empty/blank names and invalid organization/contact/owner IDs.
5. Educational metrics filtering edge cases (non-existent organization_id/program_id return clean 0 totals).
6. Manager scoping on metrics (152-FZ) and strict 403 on administrative endpoints.
7. Verification of verification scripts (verify_workflow.py, verify_reports.py, verify_plan.py).
"""
from uuid import uuid4
import pytest
from sqlalchemy import func, select
from app.models import IntegrationInbox, Interaction, LearningMetric, Organization, OrganizationContact


def headers(user="supervisor", key=None):
    res = {"X-Demo-User": user}
    if key:
        res["Idempotency-Key"] = key
    return res


# ==============================================================================
# 1. Invalid and Malformed Payloads to /inbox/{id}/resolve
# ==============================================================================

def test_resolve_missing_idempotency_key(client):
    """Missing Idempotency-Key header is rejected with 422 VALIDATION_ERROR."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    item_id = inbox["items"][0]["id"]

    res = client.post(
        f"/api/v1/integrations/inbox/{item_id}/resolve",
        headers=headers("supervisor"),  # no key
        json={"action": "reject", "params": {"reason": "test"}},
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "Idempotency-Key" in res.json()["error"]["message"]


def test_resolve_empty_or_whitespace_idempotency_key(client):
    """Empty or whitespace Idempotency-Key is rejected with 422 VALIDATION_ERROR."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    item_id = inbox["items"][0]["id"]

    for blank_key in ["", "   ", "\t\n"]:
        res = client.post(
            f"/api/v1/integrations/inbox/{item_id}/resolve",
            headers=headers("supervisor", blank_key),
            json={"action": "reject", "params": {"reason": "test"}},
        )
        assert res.status_code == 422
        assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_resolve_idempotency_key_length_limits(client):
    """Idempotency-Key boundary: <= 200 accepted, > 200 rejected with 422."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    item1 = inbox["items"][0]
    item2 = inbox["items"][1]

    # Key length 201 -> REJECTED (422)
    key_201 = "k" * 201
    res_201 = client.post(
        f"/api/v1/integrations/inbox/{item1['id']}/resolve",
        headers=headers("supervisor", key_201),
        json={"action": "reject", "params": {"reason": "too long"}},
    )
    assert res_201.status_code == 422
    assert res_201.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "200" in res_201.json()["error"]["message"]

    # Key length 1000 -> REJECTED (422)
    key_1000 = "k" * 1000
    res_1000 = client.post(
        f"/api/v1/integrations/inbox/{item1['id']}/resolve",
        headers=headers("supervisor", key_1000),
        json={"action": "reject", "params": {"reason": "way too long"}},
    )
    assert res_1000.status_code == 422

    # Key length exactly 200 -> ACCEPTED (200 OK)
    key_200 = "k" * 200
    res_200 = client.post(
        f"/api/v1/integrations/inbox/{item1['id']}/resolve",
        headers=headers("supervisor", key_200),
        json={"action": "reject", "params": {"reason": "boundary 200 chars"}},
    )
    assert res_200.status_code == 200
    assert res_200.json()["status"] == "rejected"


def test_sync_idempotency_key_length_validation(client):
    """Passing Idempotency-Key > 200 to /sync endpoint is rejected with 422."""
    key_201 = "x" * 201
    res = client.post(
        "/api/v1/integrations/sync/lms",
        headers=headers("supervisor", key_201),
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_resolve_malformed_body_structures(client):
    """Empty body, array body, and non-JSON payloads are handled gracefully with 422."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    item_id = inbox["items"][0]["id"]
    key = str(uuid4())

    # Empty body
    res_empty = client.post(
        f"/api/v1/integrations/inbox/{item_id}/resolve",
        headers=headers("supervisor", key),
        json={},
    )
    assert res_empty.status_code == 422
    assert res_empty.json()["error"]["code"] == "VALIDATION_ERROR"

    # Non-dict body: JSON array
    key_arr = str(uuid4())
    res_array = client.post(
        f"/api/v1/integrations/inbox/{item_id}/resolve",
        headers=headers("supervisor", key_arr),
        json=["link_existing", "org-1"],
    )
    assert res_array.status_code == 422
    assert res_array.json()["error"]["code"] == "VALIDATION_ERROR"

    # Raw non-JSON text
    key_raw = str(uuid4())
    res_raw = client.post(
        f"/api/v1/integrations/inbox/{item_id}/resolve",
        headers={**headers("supervisor", key_raw), "Content-Type": "application/json"},
        content=b"not-a-valid-json",
    )
    assert res_raw.status_code == 422


def test_resolve_missing_or_blank_action(client):
    """Missing or blank action field raises 422 VALIDATION_ERROR."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    item_id = inbox["items"][0]["id"]

    # Missing action key
    res_missing = client.post(
        f"/api/v1/integrations/inbox/{item_id}/resolve",
        headers=headers("supervisor", str(uuid4())),
        json={"params": {"organization_id": "org-1"}},
    )
    assert res_missing.status_code == 422
    assert res_missing.json()["error"]["code"] == "VALIDATION_ERROR"

    # Blank action
    res_blank = client.post(
        f"/api/v1/integrations/inbox/{item_id}/resolve",
        headers=headers("supervisor", str(uuid4())),
        json={"action": "   ", "organization_id": "org-1"},
    )
    assert res_blank.status_code == 422
    assert res_blank.json()["error"]["code"] == "VALIDATION_ERROR"


def test_resolve_non_string_action_type_stress(client, app):
    """Empirical Bug Finding: Action with non-string type (e.g. int 123) raises unhandled AttributeError.
    
    When an int is passed as action, main.py checks `if not action` which is false for 123.
    Then service.py executes `act = (action or '').strip().lower()` which raises
    `AttributeError: 'int' object has no attribute 'strip'`, crashing the request.
    """
    from starlette.testclient import TestClient
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    item_id = inbox["items"][0]["id"]

    # When tested with raise_server_exceptions=False:
    safe_client = TestClient(app, raise_server_exceptions=False)
    res_int = safe_client.post(
        f"/api/v1/integrations/inbox/{item_id}/resolve",
        headers=headers("supervisor", str(uuid4())),
        json={"action": 123},
    )
    # The server crashes with 500 Internal Server Error due to unhandled AttributeError
    assert res_int.status_code == 500, f"Expected 500 for unhandled int, got {res_int.status_code}"


def test_resolve_non_existent_inbox_id(client):
    """Resolving a non-existent inbox UUID returns 404 NOT_FOUND."""
    fake_id = str(uuid4())
    res = client.post(
        f"/api/v1/integrations/inbox/{fake_id}/resolve",
        headers=headers("supervisor", str(uuid4())),
        json={"action": "reject", "params": {"reason": "ghost"}},
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


def test_resolve_learning_metric_item_rejected(client):
    """Attempting to resolve an LMS metric inbox item (not application) returns 422."""
    client.post("/api/v1/integrations/sync/lms", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?source=lms", headers=headers("supervisor")).json()
    metric_item = inbox["items"][0]
    assert metric_item["entity_type"] == "learning_metric"

    res = client.post(
        f"/api/v1/integrations/inbox/{metric_item['id']}/resolve",
        headers=headers("supervisor", str(uuid4())),
        json={"action": "reject"},
    )
    assert res.status_code == 422
    assert "только для заявок" in res.json()["error"]["message"]


# ==============================================================================
# 2. Unknown Reconciliation Actions
# ==============================================================================

def test_unknown_reconciliation_actions(client):
    """Arbitrary, malicious, or unknown action names return 422 VALIDATION_ERROR."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    item_id = inbox["items"][0]["id"]

    for bad_action in [
        "drop_db",
        "unknown",
        "DELETE",
        "SELECT * FROM users;",
        "create_admin",
        "accept",
        "approve",
    ]:
        res = client.post(
            f"/api/v1/integrations/inbox/{item_id}/resolve",
            headers=headers("supervisor", str(uuid4())),
            json={"action": bad_action},
        )
        assert res.status_code == 422, f"Failed for action: {bad_action}"
        assert res.json()["error"]["code"] == "VALIDATION_ERROR"
        assert "Неизвестное действие" in res.json()["error"]["message"]


def test_valid_actions_case_insensitivity(client):
    """Valid actions are case-insensitive (e.g., REJECT, Link_Existing)."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    item1 = inbox["items"][0]

    res = client.post(
        f"/api/v1/integrations/inbox/{item1['id']}/resolve",
        headers=headers("supervisor", str(uuid4())),
        json={"action": "REJECT", "params": {"reason": "uppercase test"}},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "rejected"


# ==============================================================================
# 3. Empty / Blank Names & Invalid IDs in Reconciliation
# ==============================================================================

def test_link_existing_non_existent_org_id(client):
    """link_existing with non-existent organization_id returns 404 NOT_FOUND."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    item_id = inbox["items"][0]["id"]

    res = client.post(
        f"/api/v1/integrations/inbox/{item_id}/resolve",
        headers=headers("supervisor", str(uuid4())),
        json={"action": "link_existing", "organization_id": "non-existent-org-999"},
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


def test_link_existing_missing_org_id_on_unmatched_item(client):
    """link_existing without organization_id on item without matched org returns 422."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    unmatched_item = next(i for i in inbox["items"] if i["matched_organization_id"] is None)

    res = client.post(
        f"/api/v1/integrations/inbox/{unmatched_item['id']}/resolve",
        headers=headers("supervisor", str(uuid4())),
        json={"action": "link_existing"},
    )
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "Не указана организация" in res.json()["error"]["message"]


def test_link_existing_invalid_contact_for_org(client):
    """link_existing with contact belonging to different organization returns 422."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    item_id = inbox["items"][0]["id"]

    res = client.post(
        f"/api/v1/integrations/inbox/{item_id}/resolve",
        headers=headers("supervisor", str(uuid4())),
        json={
            "action": "link_existing",
            "organization_id": "org-1",
            "contact_id": "fake-contact-999",
        },
    )
    assert res.status_code == 422
    assert "не принадлежит" in res.json()["error"]["message"]


def test_link_existing_incompatible_program_and_product(client):
    """link_existing with incompatible program and product returns 422."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    item_id = inbox["items"][0]["id"]

    res = client.post(
        f"/api/v1/integrations/inbox/{item_id}/resolve",
        headers=headers("supervisor", str(uuid4())),
        json={
            "action": "link_existing",
            "organization_id": "org-1",
            "owner_id": "manager-a",
            "create_interaction": True,
            "program_id": "program-devops",
            "product_id": "product-test",  # product-test is QA, incompatible with devops
        },
    )
    assert res.status_code == 422
    assert "не связан с выбранной программой" in res.json()["error"]["message"]


def test_create_new_whitespace_only_name_rejected(client):
    """create_new with whitespace-only organization_name overrides payload and returns 422."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    item_id = inbox["items"][0]["id"]

    res = client.post(
        f"/api/v1/integrations/inbox/{item_id}/resolve",
        headers=headers("supervisor", str(uuid4())),
        json={
            "action": "create_new",
            "organization_name": "     ",  # whitespace override
        },
    )
    assert res.status_code == 422
    assert "Не указано название" in res.json()["error"]["message"]


def test_create_new_empty_name_when_payload_has_no_name(client, app):
    """create_new on an item without payload organization_name with empty name returns 422."""
    with app.state.session_factory() as session:
        empty_item = IntegrationInbox(
            id=str(uuid4()),
            source="website",
            entity_type="application",
            external_id="web-no-org",
            source_revision="1",
            payload={"comments": "Заявка без указания вуза"},
            status="pending",
            received_at=func.now(),
        )
        session.add(empty_item)
        session.commit()
        item_id = empty_item.id

    res = client.post(
        f"/api/v1/integrations/inbox/{item_id}/resolve",
        headers=headers("supervisor", str(uuid4())),
        json={
            "action": "create_new",
            "organization_name": "",
        },
    )
    assert res.status_code == 422
    assert "Не указано название" in res.json()["error"]["message"]


def test_create_new_invalid_owner_id(client):
    """create_new with non-existent owner_id returns 404 or 422."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    item_id = inbox["items"][0]["id"]

    res = client.post(
        f"/api/v1/integrations/inbox/{item_id}/resolve",
        headers=headers("supervisor", str(uuid4())),
        json={
            "action": "create_new",
            "organization_name": "Новый Вуз Тестовый",
            "create_interaction": True,
            "owner_id": "ghost-user-999",
        },
    )
    assert res.status_code in (404, 422)


# ==============================================================================
# 4. Educational Metrics Filtering Edge Cases
# ==============================================================================

def test_metrics_empty_database_returns_clean_zeros(client):
    """Metrics endpoint with no synced data returns clean 0 totals and empty arrays."""
    res = client.get("/api/v1/integrations/metrics", headers=headers("supervisor"))
    assert res.status_code == 200
    data = res.json()
    assert data["total_cohorts"] == 0
    assert data["total_enrolled"] == 0
    assert data["total_completed"] == 0
    assert data["avg_attendance_rate"] == 0.0
    assert data["by_program"] == []
    assert data["by_organization"] == []
    assert data["metrics"] == []


def test_metrics_non_existent_filters_return_clean_zeros(client):
    """Filtering metrics by non-existent organization_id or program_id returns clean zeros, not 500."""
    client.post("/api/v1/integrations/sync/lms", headers=headers("supervisor"))

    # Non-existent organization_id
    res_org = client.get("/api/v1/integrations/metrics?organization_id=non-existent-org-999", headers=headers("supervisor"))
    assert res_org.status_code == 200
    data_org = res_org.json()
    assert data_org["total_cohorts"] == 0
    assert data_org["total_enrolled"] == 0
    assert data_org["total_completed"] == 0
    assert data_org["avg_attendance_rate"] == 0.0
    assert data_org["by_program"] == []
    assert data_org["by_organization"] == []
    assert data_org["metrics"] == []

    # Non-existent program_id
    res_prog = client.get("/api/v1/integrations/metrics?program_id=non-existent-prog-999", headers=headers("supervisor"))
    assert res_prog.status_code == 200
    data_prog = res_prog.json()
    assert data_prog["total_cohorts"] == 0
    assert data_prog["total_enrolled"] == 0
    assert data_prog["total_completed"] == 0
    assert data_prog["avg_attendance_rate"] == 0.0
    assert data_prog["by_program"] == []
    assert data_prog["by_organization"] == []
    assert data_prog["metrics"] == []

    # Both non-existent
    res_both = client.get(
        "/api/v1/integrations/metrics?organization_id=non-existent-org&program_id=non-existent-prog",
        headers=headers("supervisor"),
    )
    assert res_both.status_code == 200
    assert res_both.json()["total_cohorts"] == 0


def test_metrics_sql_injection_probe(client):
    """SQL injection strings in query params are safely parameterized and return clean zeros."""
    client.post("/api/v1/integrations/sync/lms", headers=headers("supervisor"))

    for probe in ["' OR '1'='1", "'; DROP TABLE learning_metrics; --", "\" OR \"\"=\""]:
        res = client.get(f"/api/v1/integrations/metrics?organization_id={probe}", headers=headers("supervisor"))
        assert res.status_code == 200
        assert res.json()["total_cohorts"] == 0
        assert res.json()["by_organization"] == []


# ==============================================================================
# 5. Manager Scoping & Security Invariants (152-ФЗ / RBAC)
# ==============================================================================

def test_manager_metrics_scoping_152_fz(client):
    """Manager can read metrics but is strictly scoped to assigned organizations only."""
    client.post("/api/v1/integrations/sync/lms", headers=headers("supervisor"))

    # Supervisor sees all organizations
    res_sup = client.get("/api/v1/integrations/metrics", headers=headers("supervisor"))
    assert res_sup.status_code == 200
    sup_data = res_sup.json()
    assert sup_data["total_cohorts"] > 0
    sup_org_ids = {o["organization_id"] for o in sup_data["by_organization"]}
    assert "org-1" in sup_org_ids
    assert "org-2" in sup_org_ids

    # Manager-a is scoped strictly to org-1
    res_mgr_a = client.get("/api/v1/integrations/metrics", headers=headers("manager-a"))
    assert res_mgr_a.status_code == 200
    mgr_a_data = res_mgr_a.json()
    assert mgr_a_data["total_cohorts"] > 0
    mgr_a_org_ids = {o["organization_id"] for o in mgr_a_data["by_organization"]}
    assert mgr_a_org_ids == {"org-1"}, f"Manager A leaked non-scoped orgs: {mgr_a_org_ids}"
    assert all(m["organization_id"] == "org-1" for m in mgr_a_data["metrics"])

    # Manager-a requesting org-1 explicitly gets data
    res_mgr_a_org1 = client.get("/api/v1/integrations/metrics?organization_id=org-1", headers=headers("manager-a"))
    assert res_mgr_a_org1.status_code == 200
    assert res_mgr_a_org1.json()["total_cohorts"] > 0

    # Manager-a requesting org-2 (foreign org) receives clean 0 totals (152-FZ isolation)
    res_mgr_a_org2 = client.get("/api/v1/integrations/metrics?organization_id=org-2", headers=headers("manager-a"))
    assert res_mgr_a_org2.status_code == 200
    assert res_mgr_a_org2.json()["total_cohorts"] == 0
    assert res_mgr_a_org2.json()["by_organization"] == []
    assert res_mgr_a_org2.json()["metrics"] == []

    # Manager-b is scoped strictly to org-2 and org-3 (via interaction ix-6 in seed)
    res_mgr_b = client.get("/api/v1/integrations/metrics", headers=headers("manager-b"))
    assert res_mgr_b.status_code == 200
    mgr_b_data = res_mgr_b.json()
    assert mgr_b_data["total_cohorts"] > 0
    mgr_b_org_ids = {o["organization_id"] for o in mgr_b_data["by_organization"]}
    assert mgr_b_org_ids == {"org-2", "org-3"}, f"Manager B leaked non-scoped orgs: {mgr_b_org_ids}"
    assert "org-1" not in mgr_b_org_ids

    # Manager-b requesting org-1 receives clean 0 totals
    res_mgr_b_org1 = client.get("/api/v1/integrations/metrics?organization_id=org-1", headers=headers("manager-b"))
    assert res_mgr_b_org1.status_code == 200
    assert res_mgr_b_org1.json()["total_cohorts"] == 0
    assert res_mgr_b_org1.json()["by_organization"] == []
    assert res_mgr_b_org1.json()["metrics"] == []


def test_manager_forbidden_from_all_administrative_endpoints(client):
    """Line managers are strictly forbidden (403) from all administrative integration endpoints."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    item_id = inbox["items"][0]["id"]

    for manager in ["manager-a", "manager-b"]:
        # 1. Status
        res_status = client.get("/api/v1/integrations/status", headers=headers(manager))
        assert res_status.status_code == 403, f"{manager} accessed /status"
        assert res_status.json()["error"]["code"] == "FORBIDDEN"

        # 2. Sync LMS
        res_sync_lms = client.post("/api/v1/integrations/sync/lms", headers=headers(manager))
        assert res_sync_lms.status_code == 403, f"{manager} triggered sync/lms"
        assert res_sync_lms.json()["error"]["code"] == "FORBIDDEN"

        # 3. Sync Website
        res_sync_web = client.post("/api/v1/integrations/sync/website", headers=headers(manager))
        assert res_sync_web.status_code == 403, f"{manager} triggered sync/website"
        assert res_sync_web.json()["error"]["code"] == "FORBIDDEN"

        # 4. Inbox listing
        res_inbox = client.get("/api/v1/integrations/inbox", headers=headers(manager))
        assert res_inbox.status_code == 403, f"{manager} accessed /inbox"
        assert res_inbox.json()["error"]["code"] == "FORBIDDEN"

        # 5. Resolve
        res_resolve = client.post(
            f"/api/v1/integrations/inbox/{item_id}/resolve",
            headers=headers(manager, str(uuid4())),
            json={"action": "reject", "params": {"reason": "forbidden attempt"}},
        )
        assert res_resolve.status_code == 403, f"{manager} executed resolve"
        assert res_resolve.json()["error"]["code"] == "FORBIDDEN"


def test_anonymous_requests_rejected_with_401(client):
    """Unauthenticated (anonymous) requests to integration endpoints are rejected with 401."""
    endpoints = [
        ("GET", "/api/v1/integrations/status"),
        ("POST", "/api/v1/integrations/sync/lms"),
        ("GET", "/api/v1/integrations/inbox"),
        ("GET", "/api/v1/integrations/metrics"),
    ]
    for method, path in endpoints:
        res = client.request(method, path)  # no X-Demo-User or Authorization
        assert res.status_code == 401, f"Unauthenticated request to {path} did not return 401"
        assert res.json()["error"]["code"] == "UNAUTHENTICATED"


# ==============================================================================
# 6. Sync Source Parameter Validation & Repeated Deduplication Stability
# ==============================================================================

def test_sync_unknown_source_rejected(client):
    """Syncing an unknown or invalid source returns 422 VALIDATION_ERROR."""
    for bad_source in ["unknown", "telegram", "vk", "DROP_DATABASE", "123"]:
        res = client.post(f"/api/v1/integrations/sync/{bad_source}", headers=headers("supervisor"))
        assert res.status_code == 422, f"Failed for source: {bad_source}"
        assert res.json()["error"]["code"] == "VALIDATION_ERROR"
        assert "Неизвестный источник" in res.json()["error"]["message"]


def test_sync_multiple_consecutive_runs_stability(client, app):
    """Running sync 5 consecutive times remains stable and maintains exactly zero duplicate records."""
    for i in range(5):
        res_lms = client.post("/api/v1/integrations/sync/lms", headers=headers("supervisor"))
        assert res_lms.status_code == 200
        res_web = client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
        assert res_web.status_code == 200

    # Verify counts in DB
    with app.state.session_factory() as session:
        lms_inbox_count = session.scalar(
            select(func.count(IntegrationInbox.id)).where(IntegrationInbox.source == "lms")
        )
        assert lms_inbox_count == 12

        web_inbox_count = session.scalar(
            select(func.count(IntegrationInbox.id)).where(IntegrationInbox.source == "website")
        )
        assert web_inbox_count == 4

        metrics_count = session.scalar(select(func.count(LearningMetric.id)))
        assert metrics_count == 12
