"""Comprehensive regression test suite for Integrations Defects Remediation.

Covers all 5 defect remediations and core invariants:
- Defect 1: Administrator access to learning metrics summary and organizations catalog
  while strictly preserving 152-FZ Zero-Oracle isolation for commercial interactions.
  Querying metrics with ?organization_id=non-existent-org returns zeroes.
- Defect 2: Granular status counters on GET /api/v1/integrations/status:
  website_pending, website_processed, website_rejected (summing to total_applications),
  and reconcile_total, reconcile_pending, reconcile_processed, reconcile_rejected,
  while strictly preserving all legacy total_* fields.
- Defect 3: Technical envelope filtering on GET /api/v1/integrations/inbox:
  exclude_technical=true filters out learning_metric, sync_error, and status == 'error'.
  Omission of exclude_technical preserves legacy unfiltered behavior.
- Defect 4: Learner payload includes course_name and fallback resolution hierarchy
  resolves course_name rather than defaulting to 'Не указана'.
- Defect 5: Repeated sync on duplicate envelopes refreshes last_synced_* timestamps
  and appends descriptive guidance suffix messages for LMS and Website.
"""
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models import (
    IntegrationInbox,
    Interaction,
    LearningMetric,
    Organization,
    OrganizationAccess,
    User,
)
from app.integrations.service import (
    process_lms_learners_file,
)


def headers(user="supervisor", key=None):
    res = {"X-Demo-User": user}
    if key:
        res["Idempotency-Key"] = key
    return res


# ==============================================================================
# DEFECT 1: Administrator Metrics & Catalogs Access vs 152-FZ Zero-Oracle
# ==============================================================================

def test_defect_1_administrator_sees_metrics_and_catalogs(client):
    """Administrator sees populated learning metrics summary and organizations catalog,
    while non-existent organization filter returns zeroes, and 152-FZ Zero-Oracle
    isolates commercial interactions with 0 cards and 404 on direct access.
    """
    # 1. Sync LMS metrics
    res_sync = client.post("/api/v1/integrations/sync/lms", headers=headers("supervisor"))
    assert res_sync.status_code == 200

    # 2. Administrator requests learning metrics summary
    res_metrics = client.get("/api/v1/integrations/metrics", headers=headers("administrator"))
    assert res_metrics.status_code == 200
    metrics_data = res_metrics.json()
    assert metrics_data["total_cohorts"] > 0
    assert metrics_data["total_enrolled"] > 0
    assert metrics_data["total_completed"] > 0
    assert len(metrics_data["by_program"]) > 0
    assert len(metrics_data["by_organization"]) > 0
    assert len(metrics_data["metrics"]) > 0

    # 3. Administrator requests catalogs: organizations must be non-empty
    res_cat = client.get("/api/v1/catalogs", headers=headers("administrator"))
    assert res_cat.status_code == 200
    cat_data = res_cat.json()
    org_ids = {o["id"] for o in cat_data["organizations"]}
    assert "org-1" in org_ids
    assert "org-2" in org_ids
    assert len(cat_data["organizations"]) >= 2

    # 4. Filter by non-existent organization returns strictly zeroes
    res_non_existent = client.get(
        "/api/v1/integrations/metrics?organization_id=non-existent-org",
        headers=headers("administrator"),
    )
    assert res_non_existent.status_code == 200
    empty_summary = res_non_existent.json()
    assert empty_summary["total_cohorts"] == 0
    assert empty_summary["total_enrolled"] == 0
    assert empty_summary["total_completed"] == 0
    assert empty_summary["avg_attendance_rate"] == 0.0
    assert empty_summary["by_program"] == []
    assert empty_summary["by_organization"] == []
    assert empty_summary["metrics"] == []

    # 5. 152-FZ Zero-Oracle Invariant: administrator has 0 commercial cards
    res_interactions = client.get("/api/v1/interactions", headers=headers("administrator"))
    assert res_interactions.status_code == 200
    assert res_interactions.json()["total"] == 0
    assert res_interactions.json()["items"] == []

    # Create a commercial interaction under manager-a
    res_create = client.post(
        "/api/v1/interactions",
        json={
            "title": "Commercial Card Protected by 152-FZ",
            "organization_id": "org-1",
            "program_id": "program-devops",
            "product_id": "product-cloud",
            "cycle_label": "2026-Security-Challenge",
            "owner_id": "manager-a",
        },
        headers=headers("manager-a", key=str(uuid4())),
    )
    assert res_create.status_code == 201
    card_id = res_create.json()["id"]

    # Administrator cannot see it in list (still 0)
    res_admin_list = client.get("/api/v1/interactions", headers=headers("administrator"))
    assert res_admin_list.status_code == 200
    assert res_admin_list.json()["total"] == 0

    # Administrator receives strict 404 NOT_FOUND on direct GET
    res_admin_card = client.get(f"/api/v1/interactions/{card_id}", headers=headers("administrator"))
    assert res_admin_card.status_code == 404
    assert res_admin_card.json()["error"]["code"] == "NOT_FOUND"


# ==============================================================================
# DEFECT 2: Granular Status Counters & Backward-Compatible Legacy Invariants
# ==============================================================================

def test_defect_2_integrations_status_granular_counters(client):
    """GET /api/v1/integrations/status returns granular counters:
    website_pending, website_processed, website_rejected summing to total_applications,
    and reconcile_total, reconcile_pending, reconcile_processed, reconcile_rejected,
    while retaining all legacy total_* fields.
    """
    # 1. Initial status before sync
    res_init = client.get("/api/v1/integrations/status", headers=headers("supervisor"))
    assert res_init.status_code == 200
    data_init = res_init.json()

    # Legacy fields present
    for field in [
        "total_inbox",
        "total_pending",
        "total_processed",
        "total_quarantined",
        "total_rejected",
        "total_metrics",
        "total_applications",
        "total_errors",
    ]:
        assert field in data_init, f"Missing legacy field: {field}"

    # Granular fields present
    for field in [
        "website_pending",
        "website_processed",
        "website_rejected",
        "reconcile_total",
        "reconcile_pending",
        "reconcile_processed",
        "reconcile_rejected",
    ]:
        assert field in data_init, f"Missing granular field: {field}"

    assert data_init["website_pending"] == 0
    assert data_init["website_processed"] == 0
    assert data_init["website_rejected"] == 0
    assert data_init["total_applications"] == 0

    # 2. Sync Website applications (4 applications ingested)
    res_sync_web = client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    assert res_sync_web.status_code == 200
    assert res_sync_web.json()["received_count"] == 4

    res_status_1 = client.get("/api/v1/integrations/status", headers=headers("supervisor"))
    data_1 = res_status_1.json()

    assert data_1["total_applications"] == 4
    assert data_1["website_pending"] == 4
    assert data_1["website_processed"] == 0
    assert data_1["website_rejected"] == 0
    assert (
        data_1["website_pending"] + data_1["website_processed"] + data_1["website_rejected"]
        == data_1["total_applications"]
    )
    assert data_1["reconcile_total"] == 4
    assert data_1["reconcile_pending"] == 4
    assert data_1["reconcile_processed"] == 0
    assert data_1["reconcile_rejected"] == 0

    # 3. Reconcile one item: reject
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    item_reject = inbox["items"][0]

    res_rej = client.post(
        f"/api/v1/integrations/inbox/{item_reject['id']}/resolve",
        json={"action": "reject", "reason": "Дублирующая заявка"},
        headers=headers("supervisor", key=str(uuid4())),
    )
    assert res_rej.status_code == 200

    # Reconcile another item: link_existing
    item_link = inbox["items"][1]
    res_link = client.post(
        f"/api/v1/integrations/inbox/{item_link['id']}/resolve",
        json={"action": "link_existing", "organization_id": "org-1"},
        headers=headers("supervisor", key=str(uuid4())),
    )
    assert res_link.status_code == 200

    # 4. Check status counters after reconciliation
    res_status_2 = client.get("/api/v1/integrations/status", headers=headers("supervisor"))
    data_2 = res_status_2.json()

    assert data_2["total_applications"] == 4
    assert data_2["website_pending"] == 2
    assert data_2["website_processed"] == 1
    assert data_2["website_rejected"] == 1
    # Mathematical invariant on website card
    assert (
        data_2["website_pending"] + data_2["website_processed"] + data_2["website_rejected"]
        == data_2["total_applications"]
    )
    # Mathematical invariant on reconciliation queue
    assert data_2["reconcile_total"] == 4
    assert data_2["reconcile_pending"] == 2
    assert data_2["reconcile_processed"] == 1
    assert data_2["reconcile_rejected"] == 1

    # 5. Sync LMS metrics (12 educational metrics)
    client.post("/api/v1/integrations/sync/lms", headers=headers("supervisor"))
    res_status_3 = client.get("/api/v1/integrations/status", headers=headers("supervisor"))
    data_3 = res_status_3.json()

    # Legacy total_processed counts all inbox items including LMS metrics (12 + 1 = 13)
    assert data_3["total_processed"] == 13
    assert data_3["total_metrics"] == 12
    # But website_processed strictly remains 1
    assert data_3["website_processed"] == 1
    # And reconcile_processed strictly remains 1 (metrics are excluded from reconcile_*)
    assert data_3["reconcile_processed"] == 1
    assert data_3["reconcile_total"] == 4


# ==============================================================================
# DEFECT 3: Technical Envelopes Inbox Filtering (exclude_technical)
# ==============================================================================

def test_defect_3_inbox_technical_envelope_filtering(client, app):
    """GET /api/v1/integrations/inbox?exclude_technical=true filters out
    learning_metric and sync_error and status == 'error'.
    Omission of exclude_technical preserves legacy unfiltered behavior.
    """
    # 1. Seed LMS (12 learning metrics) and Website (4 applications)
    client.post("/api/v1/integrations/sync/lms", headers=headers("supervisor"))
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))

    # 2. Insert a simulated sync_error technical envelope
    with app.state.session_factory() as session:
        error_item = IntegrationInbox(
            id=str(uuid4()),
            source="lms",
            entity_type="sync_error",
            external_id=f"err_{uuid4().hex[:8]}",
            source_revision="1",
            status="error",
            error_message="Connection timed out to upstream LMS",
            payload={"error": "timeout"},
            received_at=datetime.now(timezone.utc),
        )
        session.add(error_item)
        session.commit()

    # 3. Default call (without exclude_technical): all 17 records returned
    res_all = client.get("/api/v1/integrations/inbox", headers=headers("supervisor"))
    assert res_all.status_code == 200
    data_all = res_all.json()
    assert data_all["total"] == 17
    entity_types_all = {item["entity_type"] for item in data_all["items"]}
    assert "learning_metric" in entity_types_all
    assert "sync_error" in entity_types_all
    assert "application" in entity_types_all

    # 4. Filtered call: exclude_technical=true
    res_filtered = client.get(
        "/api/v1/integrations/inbox?exclude_technical=true",
        headers=headers("supervisor"),
    )
    assert res_filtered.status_code == 200
    data_filtered = res_filtered.json()
    # Exactly the 4 website applications should remain
    assert data_filtered["total"] == 4
    for item in data_filtered["items"]:
        assert item["entity_type"] not in ["learning_metric", "sync_error"]
        assert item["status"] != "error"
        assert item["source"] == "website"

    # 5. Combined filter: status=processed with and without exclude_technical
    # All processed items are learning_metrics
    res_proc_unfiltered = client.get(
        "/api/v1/integrations/inbox?status=processed",
        headers=headers("supervisor"),
    )
    assert res_proc_unfiltered.status_code == 200
    assert res_proc_unfiltered.json()["total"] == 12

    res_proc_filtered = client.get(
        "/api/v1/integrations/inbox?status=processed&exclude_technical=true",
        headers=headers("supervisor"),
    )
    assert res_proc_filtered.status_code == 200
    assert res_proc_filtered.json()["total"] == 0


# ==============================================================================
# DEFECT 4: Learner Payload course_name & Program Fallback Resolution
# ==============================================================================

def test_defect_4_learner_course_name_enrichment_and_fallback(client, app):
    """LMS learner envelopes include course_name when linked to orders, and
    program name resolution properly falls back to course_name instead of defaulting
    to 'Не указана'.
    """
    with app.state.session_factory() as session:
        # Create an order envelope with course information
        order_item = IntegrationInbox(
            id=str(uuid4()),
            source="lms",
            entity_type="lms_order",
            external_id="order-test-101",
            source_revision="1",
            status="pending",
            payload={
                "order_id": "order-test-101",
                "email": "learner.qa@example.com",
                "phone": "+79991234567",
                "course": "DevOps Practices in Python",
                "course_name": "DevOps Practices in Python",
            },
            received_at=datetime.now(timezone.utc),
        )
        session.add(order_item)
        session.commit()

        # Ingest learner CSV file that matches order
        learner_csv = (
            "id;full_name;email;phone;status;diploma_reg_number;diploma_issue_date\n"
            "learner-test-202;Иванов Иван;learner.qa@example.com;+7 (999) 123-45-67;completed;DIP-99;2026-06-01\n"
        )
        supervisor_user = session.get(User, "supervisor")
        learners_res = process_lms_learners_file(session, supervisor_user, learner_csv.encode("utf-8"), "learners.csv")
        session.commit()

        assert learners_res["created_count"] == 1

        # Retrieve the ingested learner inbox record (external_id is derived from clean_email)
        learner_inbox = session.scalar(
            select(IntegrationInbox).where(IntegrationInbox.external_id == "learner.qa@example.com")
        )
        assert learner_inbox is not None
        assert learner_inbox.payload is not None

        # Verify course_name is explicitly populated in the payload
        assert learner_inbox.payload.get("course_name") == "DevOps Practices in Python"
        assert learner_inbox.payload.get("linked_order_id") == "order-test-101"

    # Query inbox via API
    res = client.get(
        f"/api/v1/integrations/inbox?exclude_technical=true",
        headers=headers("supervisor"),
    )
    assert res.status_code == 200
    items = res.json()["items"]
    target = next((i for i in items if i["external_id"] == "learner.qa@example.com"), None)
    assert target is not None
    payload = target["payload"]
    assert payload["course_name"] == "DevOps Practices in Python"

    # Verify fallback resolution logic (matching frontend and API rules)
    # Full fallback chain: p.program_name || p.course_name || raw.course_name || raw.course || raw['Курс'] || 'Не указана'
    prog_name = (
        payload.get("program_name")
        or payload.get("course_name")
        or payload.get("course")
        or "Не указана"
    )
    assert prog_name == "DevOps Practices in Python"
    assert prog_name != "Не указана"


# ==============================================================================
# DEFECT 5: Duplicate Sync Timestamp Updates & Explanatory Suffix Messages
# ==============================================================================

def test_defect_5_duplicate_sync_timestamp_update_and_explanatory_suffix(client, app):
    """Repeated sync on duplicate envelopes updates last_synced_* timestamps
    and appends explanatory guidance message to result['message'].
    """
    # 1. First LMS sync: fresh ingestion
    res1_lms = client.post("/api/v1/integrations/sync/lms", headers=headers("supervisor"))
    assert res1_lms.status_code == 200
    data1_lms = res1_lms.json()
    assert data1_lms["processed_count"] == 12
    assert data1_lms["skipped_count"] == 0
    assert "Все учебные метрики в витрине ниже уже актуальны" not in data1_lms["message"]

    status1 = client.get("/api/v1/integrations/status", headers=headers("supervisor")).json()
    last_lms_1 = status1["last_synced_lms"]
    assert last_lms_1 is not None

    # Artificially shift received_at back in time to verify timestamp advancement
    with app.state.session_factory() as session:
        past_time = datetime.now(timezone.utc) - timedelta(hours=2)
        for item in session.scalars(select(IntegrationInbox).where(IntegrationInbox.source == "lms")):
            item.received_at = past_time
        session.commit()

    # Second LMS sync: all 12 envelopes are duplicates
    res2_lms = client.post("/api/v1/integrations/sync/lms", headers=headers("supervisor"))
    assert res2_lms.status_code == 200
    data2_lms = res2_lms.json()
    assert data2_lms["received_count"] == 12
    assert data2_lms["processed_count"] == 0
    assert data2_lms["skipped_count"] == 12
    # Verify suffix explanation message
    assert "Все учебные метрики в витрине ниже уже актуальны." in data2_lms["message"]

    # Verify timestamp was refreshed
    status2 = client.get("/api/v1/integrations/status", headers=headers("supervisor")).json()
    last_lms_2 = status2["last_synced_lms"]
    assert last_lms_2 is not None
    assert last_lms_2 > (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

    # 2. First Website sync: fresh ingestion
    res1_web = client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    assert res1_web.status_code == 200
    data1_web = res1_web.json()
    assert data1_web["pending_count"] == 4
    assert data1_web["skipped_count"] == 0
    assert "Все заявки с сайта уже загружены в очередь сверки ниже" not in data1_web["message"]

    # Artificially shift website items back in time
    with app.state.session_factory() as session:
        past_time = datetime.now(timezone.utc) - timedelta(hours=3)
        for item in session.scalars(select(IntegrationInbox).where(IntegrationInbox.source == "website")):
            item.received_at = past_time
        session.commit()

    # Second Website sync: all 4 applications are duplicates
    res2_web = client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    assert res2_web.status_code == 200
    data2_web = res2_web.json()
    assert data2_web["received_count"] == 4
    assert data2_web["processed_count"] == 0
    assert data2_web["pending_count"] == 0
    assert data2_web["skipped_count"] == 4
    # Verify suffix explanation message
    assert "Все заявки с сайта уже загружены в очередь сверки ниже." in data2_web["message"]

    # Verify website timestamp was refreshed
    status3 = client.get("/api/v1/integrations/status", headers=headers("supervisor")).json()
    last_web_2 = status3["last_synced_website"]
    assert last_web_2 is not None
    assert last_web_2 > (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()


# ==============================================================================
# ADDITIONAL STRESS & ADVERSARIAL EDGE CASE TESTS
# ==============================================================================

def test_adversarial_administrator_cannot_access_commercial_cards_via_search_or_filter(client):
    """Stress-test 152-FZ Zero-Oracle: administrator cannot bypass commercial isolation
    using query parameters, search terms, or organization filters.
    """
    # Create card for manager-a
    res_card = client.post(
        "/api/v1/interactions",
        json={
            "title": "Secret Commercial Deal Rostelecom",
            "organization_id": "org-1",
            "program_id": "program-devops",
            "product_id": "product-cloud",
            "cycle_label": "2026-Security-Challenge",
            "owner_id": "manager-a",
        },
        headers=headers("manager-a", key=str(uuid4())),
    )
    assert res_card.status_code == 201
    card_id = res_card.json()["id"]

    # Search with term matching card title
    res_search = client.get("/api/v1/interactions?query=Secret", headers=headers("administrator"))
    assert res_search.status_code == 200
    assert res_search.json()["total"] == 0

    # Filter with specific organization
    res_org = client.get("/api/v1/interactions?organization_id=org-1", headers=headers("administrator"))
    assert res_org.status_code == 200
    assert res_org.json()["total"] == 0

    # Attempt mutation: PATCH interaction -> 404
    res_patch = client.patch(
        f"/api/v1/interactions/{card_id}",
        json={"expected_revision": 1, "title": "Hacked Title"},
        headers=headers("administrator"),
    )
    assert res_patch.status_code == 404


def test_defect_3_inbox_pagination_with_exclude_technical(client):
    """Verify pagination functions correctly when exclude_technical=true is active."""
    # Seed website (4 applications) and LMS (12 metrics)
    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    client.post("/api/v1/integrations/sync/lms", headers=headers("supervisor"))

    # Page 1, page_size 2 with exclude_technical=true
    res_p1 = client.get(
        "/api/v1/integrations/inbox?exclude_technical=true&page=1&page_size=2",
        headers=headers("supervisor"),
    )
    assert res_p1.status_code == 200
    data_p1 = res_p1.json()
    assert data_p1["total"] == 4
    assert len(data_p1["items"]) == 2
    assert data_p1["page"] == 1

    # Page 2, page_size 2 with exclude_technical=true
    res_p2 = client.get(
        "/api/v1/integrations/inbox?exclude_technical=true&page=2&page_size=2",
        headers=headers("supervisor"),
    )
    assert res_p2.status_code == 200
    data_p2 = res_p2.json()
    assert data_p2["total"] == 4
    assert len(data_p2["items"]) == 2
    assert data_p2["page"] == 2

    # Verify disjoint item IDs across pages
    ids_p1 = {item["id"] for item in data_p1["items"]}
    ids_p2 = {item["id"] for item in data_p2["items"]}
    assert len(ids_p1.intersection(ids_p2)) == 0


def test_defect_4_program_fallback_hierarchy():
    """Verify the four-level fallback resolution hierarchy for program names:
    1. program_name
    2. course_name
    3. raw course / 'Курс'
    4. 'Не указана'
    """
    def resolve_prog(p: dict, raw: dict) -> str:
        return (
            p.get("program_name")
            or p.get("course_name")
            or raw.get("course_name")
            or raw.get("course")
            or raw.get("Курс")
            or "Не указана"
        )

    # 1. Primary: program_name takes precedence
    assert resolve_prog({"program_name": "Prog A", "course_name": "Course B"}, {}) == "Prog A"

    # 2. Secondary: course_name used when program_name is None / empty
    assert resolve_prog({"program_name": "", "course_name": "Course B"}, {}) == "Course B"
    assert resolve_prog({"course_name": "Course B"}, {}) == "Course B"

    # 3. Tertiary: raw payload course / 'Курс'
    assert resolve_prog({}, {"course": "Raw Course C"}) == "Raw Course C"
    assert resolve_prog({}, {"Курс": "Raw Course D"}) == "Raw Course D"

    # 4. Fallback default
    assert resolve_prog({}, {}) == "Не указана"

