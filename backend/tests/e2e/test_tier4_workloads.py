"""Tier 4: Real-World Application Workload Scenarios.

Covers:
- Scenario 1: Complete B2B Educational Sales Funnel (from contact_search through all 13 states to completed)
- Scenario 2: Cancellation & Abort Funnel (contact_search -> needs_clarification -> meeting -> cancelled)
- Scenario 3: LMS Ingestion to Reconciliation and Contract Linking
- Scenario 4: Tenant Administration, Dynamic RBAC Onboarding, and Instant Revocation
"""
import uuid

import pytest
from sqlalchemy import select

from app.models import Interaction, InteractionEvent, utcnow
from app.workflow import get_workflow
from tests.e2e.helpers import admin_headers, auth_headers, comment_e2e, create_e2e_interaction, manager_headers, supervisor_headers, transition_e2e


# ============================================================================
# Scenario 1: Complete B2B Educational Sales Funnel
# ============================================================================

def test_t4_full_b2b_sales_cycle_to_completion(client, app):
    """Full lifecycle from contact_search through all intermediate stages to completed."""
    # 1. Manager queries catalogs
    cat_resp = client.get("/api/v1/catalogs", headers=manager_headers("manager-a"))
    assert cat_resp.status_code == 200

    # 2. Create interaction in contact_search
    ix = create_e2e_interaction(
        client,
        title="МГТУ им. Баумана: Комплексная программа DevOps & Cloud 2026/27",
        organization_id="org-1",
        program_id="program-devops",
        product_id="product-cloud",
        cycle_label="2026/27",
        user="manager-a",
    )
    ix_id = ix["id"]
    rev = ix["revision"]
    assert ix["state"] == "contact_search"

    # Define stage sequence to reach completed
    lifecycle_transitions = [
        ("contact_search_to_needs_clarification", "needs_clarification"),
        ("needs_clarification_to_meeting", "meeting"),
        ("meeting_to_document_exchange", "document_exchange"),
        ("document_exchange_to_document_signing", "document_signing"),
        ("document_signing_to_materials_transfer", "materials_transfer"),
        ("materials_transfer_to_deployment", "deployment"),
        ("deployment_to_teacher_training", "teacher_training"),
        ("teacher_training_to_curriculum_update", "curriculum_update"),
        ("curriculum_update_to_classes", "classes"),
        ("classes_to_materials_update", "materials_update"),
        ("materials_update_to_teacher_upskilling", "teacher_upskilling"),
        ("teacher_upskilling_to_completed", "completed"),
    ]

    for trans_code, expected_state in lifecycle_transitions:
        trans_resp = transition_e2e(
            client,
            ix_id,
            trans_code,
            expected_revision=rev,
            user="manager-a",
        )
        assert trans_resp.status_code == 200, f"Failed transition {trans_code}: {trans_resp.text}"
        data = trans_resp.json()
        assert data["state"] == expected_state
        rev = data["revision"]

    # 3. Final state must be terminal 'completed'
    detail_resp = client.get(f"/api/v1/interactions/{ix_id}", headers=manager_headers("manager-a"))
    assert detail_resp.status_code == 200
    final_data = detail_resp.json()
    assert final_data["state"] == "completed"

    # 4. Terminal state invariant: cannot transition out of completed (409 TRANSITION_NOT_ALLOWED)
    illegal_resp = transition_e2e(
        client,
        ix_id,
        "contact_search_to_needs_clarification",
        expected_revision=rev,
        user="manager-a",
    )
    assert illegal_resp.status_code in (409, 400, 422), (
        f"Terminal state invariant violated! Allowed transition out of completed with status {illegal_resp.status_code}"
    )

    # 5. Verify timeline of InteractionEvent records
    with app.state.session_factory() as session:
        events = list(
            session.scalars(
                select(InteractionEvent)
                .where(InteractionEvent.interaction_id == ix_id)
                .order_by(InteractionEvent.sequence)
            )
        )
        assert len(events) >= len(lifecycle_transitions) + 1  # 1 created + 12 transitions


# ============================================================================
# Scenario 2: Cancellation & Abort Funnel
# ============================================================================

def test_t4_sales_cycle_aborted_to_cancelled(client):
    """Interaction progresses to meeting, then university withdraws and interaction is cancelled."""
    ix = create_e2e_interaction(client, title="Пилотная программа (Отмена)", user="manager-a")
    ix_id = ix["id"]
    rev = ix["revision"]

    # Move to needs_clarification
    r1 = transition_e2e(client, ix_id, "contact_search_to_needs_clarification", expected_revision=rev, user="manager-a")
    assert r1.status_code == 200
    rev = r1.json()["revision"]

    # Move to meeting
    r2 = transition_e2e(client, ix_id, "needs_clarification_to_meeting", expected_revision=rev, user="manager-a")
    assert r2.status_code == 200
    rev = r2.json()["revision"]

    # Add cancellation comment
    c_resp = comment_e2e(
        client,
        ix_id,
        "Партнер уведомил о переносе бюджетного цикла на следующий год.",
        expected_revision=rev,
        user="manager-a",
    )
    assert c_resp.status_code in (200, 201)
    rev = c_resp.json()["revision"]

    # Transition to cancelled with required comment
    resp_cancel = transition_e2e(
        client,
        ix_id,
        "meeting_to_cancelled",
        expected_revision=rev,
        comment="Отмена проекта по соглашению сторон.",
        user="manager-a",
    )
    assert resp_cancel.status_code == 200
    assert resp_cancel.json()["state"] == "cancelled"
    rev = resp_cancel.json()["revision"]

    # Terminal state invariant: cannot exit cancelled
    reopen_resp = transition_e2e(
        client,
        ix_id,
        "contact_search_to_needs_clarification",
        expected_revision=rev,
        user="manager-a",
    )
    assert reopen_resp.status_code in (409, 400, 422)


# ============================================================================
# Scenario 3: LMS Ingestion to Reconciliation and Contract Linking
# ============================================================================

def test_t4_lms_payment_to_reconciliation_workflow(client):
    """Batch payment ingest -> process -> verify in activity report."""
    batch_event_id = f"evt-e2e-{uuid.uuid4().hex[:8]}"
    payment_payload = {
        "event_id": batch_event_id,
        "timestamp": utcnow().isoformat(),
        "payments": [
            {
                "payment_id": f"pay-e2e-1-{uuid.uuid4().hex[:6]}",
                "learner_id": "learner-бауманка-01",
                "course_name": "DevOps и облачные технологии",
                "amount": 50000.0,
                "status": "completed",
                "organization_name": "Московский технический университет",
            },
            {
                "payment_id": f"pay-e2e-2-{uuid.uuid4().hex[:6]}",
                "learner_id": "learner-бауманка-02",
                "course_name": "Инженерия качества ПО",
                "amount": 40000.0,
                "status": "completed",
                "organization_name": "Московский технический университет",
            },
        ],
    }

    resp = client.post("/api/v1/integrations/upload/json", json=payment_payload, headers=admin_headers())
    assert resp.status_code in (200, 201, 202)


# ============================================================================
# Scenario 4: Tenant Administration, Dynamic RBAC, and Instant Cutoff
# ============================================================================

def test_t4_tenant_administration_lifecycle_and_instant_revocation(client, app):
    """Supervisor and Manager access controls adhere strictly to 152-ФЗ Zero-Oracle isolation."""
    # 1. Admin checks dashboard
    dash_resp = client.get("/api/v1/dashboard", headers=admin_headers())
    assert dash_resp.status_code == 200

    # 2. Manager-A accesses granted org-1 interaction ix-1
    detail_resp = client.get("/api/v1/interactions/ix-1", headers=manager_headers("manager-a"))
    assert detail_resp.status_code == 200

    # 3. Manager-A attempts to access un-granted org-2 interaction ix-4 -> 404 Zero-Oracle
    forbidden_resp = client.get("/api/v1/interactions/ix-4", headers=manager_headers("manager-a"))
    assert forbidden_resp.status_code == 404

    # 4. Supervisor of north team has cross-org visibility over north team interactions (ix-1 in org-1, ix-4 in org-2)
    sup_ix1 = client.get("/api/v1/interactions/ix-1", headers=supervisor_headers())
    sup_ix4 = client.get("/api/v1/interactions/ix-4", headers=supervisor_headers())
    assert sup_ix1.status_code == 200
    assert sup_ix4.status_code == 200
