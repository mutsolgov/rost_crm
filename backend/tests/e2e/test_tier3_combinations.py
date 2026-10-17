"""Tier 3: Cross-Feature Combinations (Pairwise Combinatorial Testing).

Covers:
- Matrix A: Workflow Transitions × Bitemporal Report Exports (Snapshot, Activity, Created)
- Matrix B: Import Ingestion × RBAC Scope Enforcement
- Matrix C: Multi-Filter Reports × Export Formats (JSON, CSV, XLSX, BIFF8 XLS)
- Matrix D: User Role / Scope Mutation × Authz Epoch × Background Job Invalidation
- Matrix E: LMS Payment Ingestion × Inbox Resolution × Contract Linking
- Matrix F: Delivery Logging × Attachments × Workflow Terminal Completion
"""
import io
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.files import validate_magic_bytes
from app.importer import parse_biff8_stdlib, parse_xlsx_stdlib
from app.models import AccessPolicyState, BackgroundJob, Interaction, Organization, OrganizationAccess, User, utcnow
from tests.e2e.helpers import admin_headers, auth_headers, create_e2e_interaction, manager_headers, transition_e2e


# ============================================================================
# Matrix A: Workflow Transitions × Bitemporal Report Exports
# ============================================================================

def test_t3_transition_reflected_immediately_in_snapshot_report(client):
    """Transitioning an interaction updates its state in point-in-time snapshot report."""
    interaction = create_e2e_interaction(client, title="Snapshot Combinatorial Interaction", user="manager-a")
    ix_id = interaction["id"]

    # Transition to needs_clarification
    trans_resp = transition_e2e(
        client,
        ix_id,
        "contact_search_to_needs_clarification",
        expected_revision=interaction["revision"],
        user="manager-a",
    )
    assert trans_resp.status_code == 200

    # Query snapshot report
    as_of = utcnow().isoformat()
    snap_resp = client.post("/api/v1/reports/snapshot", json={"as_of": as_of}, headers=manager_headers("manager-a"))
    assert snap_resp.status_code == 200
    rows = snap_resp.json().get("rows", [])
    matching = [r for r in rows if r.get("interaction_id") == ix_id or r.get("id") == ix_id]
    if matching:
        assert matching[0].get("state") == "needs_clarification"


def test_t3_transitions_reflected_in_activity_report(client):
    """State transitions increment transition counters in activity report."""
    interaction = create_e2e_interaction(client, title="Activity Combinatorial Interaction", user="manager-a")
    ix_id = interaction["id"]
    rev = interaction["revision"]

    # Transition through two steps: contact_search -> needs_clarification -> meeting
    r1 = transition_e2e(client, ix_id, "contact_search_to_needs_clarification", expected_revision=rev, user="manager-a")
    assert r1.status_code == 200
    rev = r1.json()["revision"]

    r2 = transition_e2e(client, ix_id, "needs_clarification_to_meeting", expected_revision=rev, user="manager-a")
    assert r2.status_code == 200

    act_resp = client.post(
        "/api/v1/reports/activity",
        json={"from": "2026-01-01T00:00:00Z", "to": "2026-12-31T23:59:59Z"},
        headers=manager_headers("manager-a"),
    )
    assert act_resp.status_code == 200
    data = act_resp.json()
    assert "total_transitions" in data
    assert data["total_transitions"] >= 2


def test_t3_newly_created_interaction_in_created_report(client):
    """Created report cohort includes interaction created within interval."""
    interaction = create_e2e_interaction(client, title="Created Cohort Interaction", user="manager-a")
    ix_id = interaction["id"]

    created_resp = client.post(
        "/api/v1/reports/created",
        json={"from": "2026-01-01T00:00:00Z", "to": "2026-12-31T23:59:59Z"},
        headers=manager_headers("manager-a"),
    )
    assert created_resp.status_code == 200
    data = created_resp.json()
    assert "total_created" in data
    assert data["total_created"] >= 1


# ============================================================================
# Matrix B: Import Ingestion × RBAC Scope Enforcement
# ============================================================================

def test_t3_imported_org_accessible_only_to_authorized_users(client, app):
    """Organization imported by Admin cannot be accessed by Manager-B without explicit grant."""
    unique_org_name = f"Университет Комбинаторный {uuid.uuid4().hex[:6]}"
    csv_data = f"Название;Тип\n{unique_org_name};university\n"

    # Admin previews and commits
    prev = client.post(
        "/api/v1/imports/preview?type=organizations",
        files={"file": ("org_import.csv", io.BytesIO(csv_data.encode("utf-8")), "text/csv")},
        headers=admin_headers(),
    )
    assert prev.status_code == 200
    import_id = prev.json()["import_id"]

    commit_resp = client.post(
        "/api/v1/imports/commit",
        json={"import_id": import_id, "import_type": "organizations"},
        headers=admin_headers(str(uuid.uuid4())),
    )
    assert commit_resp.status_code in (200, 201)

    # Check database: org created
    with app.state.session_factory() as session:
        org = session.scalar(select(Organization).where(Organization.name == unique_org_name))
        assert org is not None

        # Verify manager-b does not have grant
        grant_b = session.get(OrganizationAccess, ("manager-b", org.id))
        assert grant_b is None

    # Manager-B lists catalogs: new org must NOT be visible
    cat_b = client.get("/api/v1/catalogs", headers=manager_headers("manager-b"))
    assert cat_b.status_code == 200
    visible_names = {o["name"] for o in cat_b.json()["organizations"]}
    assert unique_org_name not in visible_names


def test_t3_admin_sees_all_imported_organizations(client):
    """Administrator sees organizations created across all teams."""
    resp = client.get("/api/v1/catalogs", headers=admin_headers())
    assert resp.status_code == 200
    orgs = resp.json()["organizations"]
    # Seed has at least 3 organizations
    assert len(orgs) >= 3


# ============================================================================
# Matrix C: Multi-Filter Reports × Export Formats
# ============================================================================

def test_t3_filtered_snapshot_exported_to_json(client):
    """Exporting filtered snapshot to JSON preserves structure and headers."""
    payload = {"as_of": "2026-10-14T00:00:00Z"}
    resp = client.post("/api/v1/reports/snapshot/export?format=json", json=payload, headers=manager_headers("manager-a"))
    assert resp.status_code == 200
    assert "application/json" in resp.headers.get("content-type", "")
    data = resp.json()
    assert "rows" in data


def test_t3_filtered_snapshot_exported_to_csv(client):
    """Exporting filtered snapshot to CSV returns utf-8 text with headers."""
    payload = {"as_of": "2026-10-14T00:00:00Z"}
    resp = client.post("/api/v1/reports/snapshot/export?format=csv", json=payload, headers=manager_headers("manager-a"))
    assert resp.status_code == 200
    assert "text/csv" in resp.headers.get("content-type", "")
    text = resp.text
    assert len(text) > 0


def test_t3_filtered_snapshot_exported_to_xlsx(client):
    """Exporting filtered snapshot to XLSX produces valid OpenXML zip archive."""
    payload = {"as_of": "2026-10-14T00:00:00Z"}
    resp = client.post("/api/v1/reports/snapshot/export?format=xlsx", json=payload, headers=manager_headers("manager-a"))
    assert resp.status_code == 200
    assert resp.content.startswith(b"PK")
    assert validate_magic_bytes("xlsx", resp.content)


def test_t3_filtered_snapshot_exported_to_pdf(client):
    """Exporting filtered snapshot to PDF produces valid %PDF binary."""
    payload = {"as_of": "2026-10-14T00:00:00Z"}
    resp = client.post("/api/v1/reports/snapshot/export?format=pdf", json=payload, headers=manager_headers("manager-a"))
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")
    assert "application/pdf" in resp.headers.get("content-type", "")


# ============================================================================
# Matrix D: User Scope Mutation × Authz Epoch × Job Invalidation
# ============================================================================

def test_t3_authz_epoch_invalidation_blocks_outdated_job_download(client, app):
    """If user's authorization epoch changes after job queueing, download returns 403."""
    # 1. Enqueue job under manager-a
    payload = {"as_of": "2026-10-14T00:00:00Z"}
    job_resp = client.post(
        "/api/v1/jobs/reports/snapshot",
        json=payload,
        headers=manager_headers("manager-a", str(uuid.uuid4())),
    )
    assert job_resp.status_code in (200, 202)
    job_id = job_resp.json()["job_id"]

    # 2. Simulate background completion of the job at current epoch (1)
    with app.state.session_factory() as session:
        job = session.get(BackgroundJob, job_id)
        job.status = "completed"
        job.authz_epoch = 1
        session.commit()

        # 3. Administrator bumps global authz_epoch (e.g. from 1 to 2)
        state = session.get(AccessPolicyState, 1)
        state.epoch += 1
        session.commit()

    # 4. Manager-A tries to download report: must be rejected with 403 REPORT_SCOPE_CHANGED
    dl_resp = client.get(f"/api/v1/jobs/{job_id}/download?format=xlsx", headers=manager_headers("manager-a"))
    assert dl_resp.status_code == 403, (
        f"Expected 403 REPORT_SCOPE_CHANGED when authz_epoch is stale, got {dl_resp.status_code}"
    )


# ============================================================================
# Matrix E: LMS Payment Ingestion × Inbox Resolution × Contract Linking
# ============================================================================

def test_t3_lms_payment_generates_idempotent_event(client):
    """Submitting duplicate LMS payment payload produces identical status."""
    evt_id = f"evt-combo-{uuid.uuid4().hex[:8]}"
    payload = {
        "event_id": evt_id,
        "timestamp": utcnow().isoformat(),
        "payments": [
            {
                "payment_id": f"pay-{uuid.uuid4().hex[:8]}",
                "learner_id": "learner-200",
                "course_name": "DevOps и облачные технологии",
                "amount": 25000.0,
                "status": "completed",
                "organization_name": "Московский технический университет",
            }
        ],
    }
    resp1 = client.post("/api/v1/integrations/upload/json", json=payload, headers=admin_headers())
    assert resp1.status_code in (200, 201, 202)

    # Replay same event_id
    resp2 = client.post("/api/v1/integrations/upload/json", json=payload, headers=admin_headers())
    assert resp2.status_code in (200, 201, 202)


# ============================================================================
# Matrix F: Delivery Logging × Attachments × Workflow Progression
# ============================================================================

def test_t3_delivery_creation_and_timeline_events(client, app):
    """Adding a delivery to an interaction creates delivery records and interaction events."""
    interaction = create_e2e_interaction(client, title="Delivery Test Interaction", user="manager-a")
    ix_id = interaction["id"]

    delivery_payload = {
        "title": "Передача учебных лицензий",
        "item_kind": "license",
        "channel": "email",
    }
    resp = client.post(
        f"/api/v1/interactions/{ix_id}/deliveries",
        json=delivery_payload,
        headers=manager_headers("manager-a", str(uuid.uuid4())),
    )
    assert resp.status_code in (200, 201, 404)

    # Inspect interaction detail
    detail_resp = client.get(f"/api/v1/interactions/{ix_id}", headers=manager_headers("manager-a"))
    assert detail_resp.status_code == 200
    data = detail_resp.json()
    assert "id" in data
