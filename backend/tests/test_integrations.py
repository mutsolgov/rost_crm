"""Comprehensive test suite for the Resilient Integrations Contour.

Covers:
- RBAC permissions (supervisor/admin allowed, manager forbidden)
- Adapter synchronization and ingestion from mock LMS and mock Website
- Deduplication and idempotency on repeat ingestions
- Website partnership applications ingestion into inbox in pending state
- Inbox listing, filtering by source/status, and pagination
- Application reconciliation: link_existing (with interaction creation)
- Application reconciliation: create_new (new organization, contact, interaction)
- Application reconciliation: reject (status=rejected, error_message recorded)
- Conflict handling on already processed/resolved inbox items (409 Conflict)
- Idempotency-Key replay caching (prevents duplicate interactions)
- Demand metrics summary aggregation and breakdown by program and university
- 152-FZ scope isolation on created interactions (404 for unassigned managers)
"""
from uuid import uuid4

from sqlalchemy import func, select
from app.models import IntegrationInbox, Interaction, LearningMetric, Organization


def headers(user="supervisor", key=None):
    res = {"X-Demo-User": user}
    if key:
        res["Idempotency-Key"] = key
    return res


def test_integrations_status_rbac(client):
    """Supervisor and admin can read integration status; manager is rejected with 403."""
    # Manager receives 403 Forbidden
    res_mgr = client.get("/api/v1/integrations/status", headers=headers("manager-a"))
    assert res_mgr.status_code == 403
    assert res_mgr.json()["error"]["code"] == "FORBIDDEN"

    # Manager attempting sync receives 403 Forbidden
    res_sync_mgr = client.post("/api/v1/integrations/sync/lms", headers=headers("manager-a"))
    assert res_sync_mgr.status_code == 403

    # Supervisor receives 200 OK
    res_sup = client.get("/api/v1/integrations/status", headers=headers("supervisor"))
    assert res_sup.status_code == 200
    data_sup = res_sup.json()
    assert "adapters" in data_sup
    assert len(data_sup["adapters"]) == 2
    assert data_sup["total_inbox"] == 0
    assert data_sup["total_metrics"] == 0

    # Admin receives 200 OK
    res_adm = client.get("/api/v1/integrations/status", headers=headers("administrator"))
    assert res_adm.status_code == 200


def test_lms_sync_and_learning_metrics(client, app):
    """Syncing LMS ingests 12 educational metric envelopes and stores LearningMetric records."""
    res_sync = client.post("/api/v1/integrations/sync/lms", headers=headers("supervisor"))
    assert res_sync.status_code == 200
    sync_data = res_sync.json()
    assert sync_data["source"] == "lms"
    assert sync_data["received_count"] == 12
    assert sync_data["processed_count"] == 12
    assert sync_data["skipped_count"] == 0

    # Verify metrics in database
    with app.state.session_factory() as session:
        metric_count = session.scalar(select(func.count(LearningMetric.id)))
        assert metric_count == 12

        inbox_count = session.scalar(select(func.count(IntegrationInbox.id)))
        assert inbox_count == 12

    # Status endpoint reflects synced metrics
    res_status = client.get("/api/v1/integrations/status", headers=headers("supervisor"))
    assert res_status.status_code == 200
    assert res_status.json()["total_metrics"] == 12
    assert res_status.json()["total_processed"] == 12


def test_sync_deduplication_and_idempotency(client, app):
    """Repeat LMS sync calls skip existing records without database constraint errors."""
    # First sync
    res1 = client.post("/api/v1/integrations/sync/lms", headers=headers("supervisor"))
    assert res1.status_code == 200
    assert res1.json()["processed_count"] == 12
    assert res1.json()["skipped_count"] == 0

    # Second sync (duplicate envelopes)
    res2 = client.post("/api/v1/integrations/sync/lms", headers=headers("supervisor"))
    assert res2.status_code == 200
    assert res2.json()["received_count"] == 12
    assert res2.json()["processed_count"] == 0
    assert res2.json()["skipped_count"] == 12

    # Verify no duplicate metrics were created
    with app.state.session_factory() as session:
        metric_count = session.scalar(select(func.count(LearningMetric.id)))
        assert metric_count == 12
        inbox_count = session.scalar(select(func.count(IntegrationInbox.id)))
        assert inbox_count == 12


def test_website_sync_creates_pending_inbox_items(client, app):
    """Syncing website generates 4 partnership application envelopes in pending state."""
    res_sync = client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    assert res_sync.status_code == 200
    data = res_sync.json()
    assert data["source"] == "website"
    assert data["received_count"] == 4
    assert data["pending_count"] == 4
    assert data["processed_count"] == 0

    # Verify status in database
    with app.state.session_factory() as session:
        pending_items = list(session.scalars(select(IntegrationInbox).where(IntegrationInbox.source == "website")))
        assert len(pending_items) == 4
        for item in pending_items:
            assert item.status == "pending"

        # Check that known institutions are automatically matched by name
        mtu = next(i for i in pending_items if "Московский" in (i.payload.get("organization_name") or ""))
        assert mtu.matched_organization_id == "org-1"

        north = next(i for i in pending_items if "Северный" in (i.payload.get("organization_name") or ""))
        assert north.matched_organization_id == "org-2"

        # Unknown institutions are left unlinked
        kai = next(i for i in pending_items if "Туполева" in (i.payload.get("organization_name") or ""))
        assert kai.matched_organization_id is None


def test_inbox_pagination_and_filtering(client):
    """Inbox items can be filtered by source and status with pagination."""
    # Seed both LMS and Website
    client.post("/api/v1/integrations/sync/lms", headers=headers("supervisor"))
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))

    # Filter by status=pending (website applications only)
    res_pending = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor"))
    assert res_pending.status_code == 200
    data_pending = res_pending.json()
    assert data_pending["total"] == 4
    assert len(data_pending["items"]) == 4
    assert all(i["status"] == "pending" for i in data_pending["items"])

    # Filter by status=processed (LMS metrics only)
    res_proc = client.get("/api/v1/integrations/inbox?status=processed", headers=headers("supervisor"))
    assert res_proc.status_code == 200
    assert res_proc.json()["total"] == 12

    # Filter by source=website
    res_web = client.get("/api/v1/integrations/inbox?source=website", headers=headers("supervisor"))
    assert res_web.status_code == 200
    assert res_web.json()["total"] == 4

    # Pagination: page_size=2
    res_page = client.get("/api/v1/integrations/inbox?status=pending&page=1&page_size=2", headers=headers("supervisor"))
    assert res_page.status_code == 200
    data_page = res_page.json()
    assert data_page["total"] == 4
    assert len(data_page["items"]) == 2
    assert data_page["page"] == 1
    assert data_page["page_size"] == 2


def test_reconcile_link_existing_with_interaction(client, app):
    """Reconciling with link_existing associates organization, creates contact and interaction in contact_search."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    mtu_item = next(i for i in inbox["items"] if "Московский" in (i["payload"].get("organization_name") or ""))

    key = str(uuid4())
    res_resolve = client.post(
        f"/api/v1/integrations/inbox/{mtu_item['id']}/resolve",
        headers=headers("supervisor", key),
        json={
            "action": "link_existing",
            "organization_id": "org-1",
            "owner_id": "manager-a",
            "create_interaction": True,
            "program_id": "program-devops",
            "interaction_title": "Партнёрство с МТУ (через сайт)",
        },
    )
    assert res_resolve.status_code == 200
    resolved = res_resolve.json()
    assert resolved["status"] == "processed"
    assert resolved["matched_organization_id"] == "org-1"
    assert resolved["matched_interaction_id"] is not None

    interaction_id = resolved["matched_interaction_id"]

    # Verify created interaction
    res_inter = client.get(f"/api/v1/interactions/{interaction_id}", headers=headers("manager-a"))
    assert res_inter.status_code == 200
    inter_data = res_inter.json()
    assert inter_data["state"] == "contact_search"
    assert inter_data["revision"] == 1
    assert inter_data["owner_id"] == "manager-a"
    assert inter_data["organization_id"] == "org-1"
    assert inter_data["program_id"] == "program-devops"
    assert inter_data["contact_id"] is not None


def test_reconcile_create_new_organization(client, app):
    """Reconciling with create_new creates new organization, access grant, contact, and interaction."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    kai_item = next(i for i in inbox["items"] if "Туполева" in (i["payload"].get("organization_name") or ""))

    key = str(uuid4())
    res_resolve = client.post(
        f"/api/v1/integrations/inbox/{kai_item['id']}/resolve",
        headers=headers("supervisor", key),
        json={
            "action": "create_new",
            "organization_name": "Казанский национальный исследовательский технический университет им. А.Н. Туполева",
            "organization_type": "university",
            "representative_name": "Иванов Иван Иванович",
            "representative_position": "Заведующий кафедрой",
            "representative_email": "ivanov@kai.ru",
            "representative_phone": "+7 (843) 231-01-01",
            "create_interaction": True,
            "owner_id": "manager-a",
            "program_id": "program-devops",
            "interaction_title": "Сотрудничество с КНИТУ-КАИ",
        },
    )
    assert res_resolve.status_code == 200
    resolved = res_resolve.json()
    assert resolved["status"] == "processed"
    assert resolved["organization_id"] is not None
    assert resolved["contact_id"] is not None
    assert resolved["interaction_id"] is not None

    new_org_id = resolved["organization_id"]

    # Verify organization exists in DB
    with app.state.session_factory() as session:
        org = session.get(Organization, new_org_id)
        assert org is not None
        assert "Туполева" in org.name

    # Verify interaction exists and manager has access
    inter = client.get(f"/api/v1/interactions/{resolved['interaction_id']}", headers=headers("manager-a")).json()
    assert inter["organization_id"] == new_org_id
    assert inter["state"] == "contact_search"


def test_reconcile_reject(client, app):
    """Reconciling with reject transitions inbox status to rejected and stores error_message."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    sib_item = next(i for i in inbox["items"] if "Сибирский" in (i["payload"].get("organization_name") or ""))

    key = str(uuid4())
    res_reject = client.post(
        f"/api/v1/integrations/inbox/{sib_item['id']}/resolve",
        headers=headers("supervisor", key),
        json={
            "action": "reject",
            "reason": "Не соответствует критериям партнерской программы",
        },
    )
    assert res_reject.status_code == 200
    rejected = res_reject.json()
    assert rejected["status"] == "rejected"
    assert rejected["error_message"] == "Не соответствует критериям партнерской программы"
    assert rejected["matched_interaction_id"] is None

    # Verify in DB
    with app.state.session_factory() as session:
        item = session.get(IntegrationInbox, sib_item["id"])
        assert item.status == "rejected"
        assert item.error_message == "Не соответствует критериям партнерской программы"


def test_reconcile_conflict_already_processed(client):
    """Attempting to resolve an already resolved/rejected item raises 409 Conflict."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    item_id = inbox["items"][0]["id"]

    # First resolution: reject
    client.post(
        f"/api/v1/integrations/inbox/{item_id}/resolve",
        headers=headers("supervisor", "key-first"),
        json={"action": "reject", "reason": "Первичный отказ"},
    )

    # Second resolution with different key -> 409 Conflict
    res_conflict = client.post(
        f"/api/v1/integrations/inbox/{item_id}/resolve",
        headers=headers("supervisor", "key-second"),
        json={"action": "link_existing", "organization_id": "org-1"},
    )
    assert res_conflict.status_code == 409
    assert "уже обработана" in res_conflict.json()["error"]["message"]


def test_reconcile_idempotency_key_replay(client, app):
    """Repeating resolution with same Idempotency-Key returns cached response without duplicate interactions."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    item = inbox["items"][0]

    replay_key = f"replay-key-{uuid4()}"
    payload = {
        "action": "link_existing",
        "organization_id": "org-1",
        "owner_id": "manager-a",
        "create_interaction": True,
    }

    res1 = client.post(
        f"/api/v1/integrations/inbox/{item['id']}/resolve",
        headers=headers("supervisor", replay_key),
        json=payload,
    )
    assert res1.status_code == 200
    data1 = res1.json()
    interaction_id = data1["interaction_id"]

    # Second call with exact same key
    res2 = client.post(
        f"/api/v1/integrations/inbox/{item['id']}/resolve",
        headers=headers("supervisor", replay_key),
        json=payload,
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["interaction_id"] == interaction_id

    # Verify only 1 interaction was created from this inbox item
    with app.state.session_factory() as session:
        inter_count = session.scalar(
            select(func.count(Interaction.id)).where(Interaction.id == interaction_id)
        )
        assert inter_count == 1


def test_learning_metrics_summary_aggregation(client):
    """Metrics endpoint aggregates cohort counts, enrolled/completed students, and breakdown by program."""
    client.post("/api/v1/integrations/sync/lms", headers=headers("supervisor"))

    # Overall summary for supervisor
    res = client.get("/api/v1/integrations/metrics", headers=headers("supervisor"))
    assert res.status_code == 200
    data = res.json()
    assert data["total_cohorts"] > 0
    assert data["total_enrolled"] > 0
    assert data["total_completed"] > 0
    assert data["avg_attendance_rate"] > 0.0

    assert len(data["by_program"]) > 0
    assert len(data["by_organization"]) > 0

    # Scoped filter by organization_id
    res_org = client.get("/api/v1/integrations/metrics?organization_id=org-1", headers=headers("supervisor"))
    assert res_org.status_code == 200
    data_org = res_org.json()
    assert data_org["total_cohorts"] > 0
    assert all(o["organization_id"] == "org-1" for o in data_org["by_organization"])

    # Scoped filter by program_id
    res_prog = client.get("/api/v1/integrations/metrics?program_id=program-devops", headers=headers("supervisor"))
    assert res_prog.status_code == 200
    data_prog = res_prog.json()
    assert all(p["program_id"] == "program-devops" for p in data_prog["by_program"])


def test_scope_isolation_152_fz_on_created_interaction(client):
    """Interactions created from integration queue respect 152-FZ scope isolation (404 for other managers)."""
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    item = inbox["items"][0]

    # Resolve and assign to manager-a
    res = client.post(
        f"/api/v1/integrations/inbox/{item['id']}/resolve",
        headers=headers("supervisor", str(uuid4())),
        json={
            "action": "link_existing",
            "organization_id": "org-1",
            "owner_id": "manager-a",
            "create_interaction": True,
        },
    )
    inter_id = res.json()["interaction_id"]

    # Assigned manager-a can access interaction
    res_a = client.get(f"/api/v1/interactions/{inter_id}", headers=headers("manager-a"))
    assert res_a.status_code == 200

    # Unassigned manager-b in a different team receives 404 Not Found (152-FZ invariant)
    res_b = client.get(f"/api/v1/interactions/{inter_id}", headers=headers("manager-b"))
    assert res_b.status_code == 404
    assert res_b.json()["error"]["code"] == "NOT_FOUND"
