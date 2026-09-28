"""Tests for temporal fact tables (TASK-O03).

Verifies:
1. StateVisit creation on interaction creation (create_interaction).
2. StateVisit closure, duration_seconds calculation, and next StateVisit creation on transition (transition).
3. StateVisit duration calculation accuracy with known time intervals.
4. Cascade deletion of StateVisit when parent Interaction is deleted.
5. Graceful handling of legacy interactions without open StateVisits during transition.
6. ReportRun and ReportRow creation via freeze_report_dataset.
7. Verification of parameters_hash and dataset_checksum computation.
8. Frozen dataset row retrieval in correct ordinal order via get_frozen_report_rows.
9. Handling of empty rows in freeze_report_dataset.
10. Cascade deletion of ReportRow when parent ReportRun is deleted.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import Interaction, ReportRow, ReportRun, StateVisit, User, utcnow
from app.schemas import InteractionCreate, TransitionCommand
from app.services import (
    create_interaction as service_create_interaction,
    freeze_report_dataset,
    get_frozen_report_rows,
    transition as service_transition,
)


def headers(user="manager-a", key=None):
    result = {"X-Demo-User": user}
    if key:
        result["Idempotency-Key"] = key
    return result


def test_state_visit_created_on_interaction_create(client, app):
    """Verify create_interaction creates initial StateVisit with state=contact_search."""
    body = {
        "title": "Тест StateVisit при создании",
        "organization_id": "org-1",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "2026/2027",
        "owner_id": "manager-a",
    }
    resp = client.post(
        "/api/v1/interactions",
        json=body,
        headers=headers(user="manager-a", key=str(uuid4())),
    )
    assert resp.status_code == 201, resp.text
    card = resp.json()

    with app.state.session_factory() as session:
        visits = session.scalars(
            select(StateVisit).where(StateVisit.interaction_id == card["id"])
        ).all()
        assert len(visits) == 1
        visit = visits[0]
        assert visit.state == "contact_search"
        assert visit.entered_at is not None
        assert visit.exited_at is None
        assert visit.duration_seconds is None


def test_state_visit_transition_and_duration_tracking(client, app):
    """Verify transitions close prior StateVisit with duration_seconds and open next StateVisit."""
    body = {
        "title": "Тест переходов StateVisit",
        "organization_id": "org-1",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "2026/2027",
        "owner_id": "manager-a",
    }
    resp = client.post(
        "/api/v1/interactions",
        json=body,
        headers=headers(user="manager-a", key=str(uuid4())),
    )
    assert resp.status_code == 201, resp.text
    card = resp.json()

    # Transition 1: contact_search -> needs_clarification
    resp_t1 = client.post(
        f"/api/v1/interactions/{card['id']}/transitions",
        json={
            "transition_code": "contact_search_to_needs_clarification",
            "expected_revision": card["revision"],
        },
        headers=headers(user="manager-a", key=str(uuid4())),
    )
    assert resp_t1.status_code == 200, resp_t1.text
    card = resp_t1.json()

    with app.state.session_factory() as session:
        visits = session.scalars(
            select(StateVisit)
            .where(StateVisit.interaction_id == card["id"])
            .order_by(StateVisit.entered_at.asc())
        ).all()
        assert len(visits) == 2

        v1, v2 = visits
        # First visit should be closed
        assert v1.state == "contact_search"
        assert v1.exited_at is not None
        assert v1.duration_seconds is not None
        assert v1.duration_seconds >= 0.0
        assert v1.exited_at >= v1.entered_at

        # Second visit should be open
        assert v2.state == "needs_clarification"
        assert v2.entered_at is not None
        assert v2.exited_at is None
        assert v2.duration_seconds is None

    # Transition 2: needs_clarification -> meeting
    resp_t2 = client.post(
        f"/api/v1/interactions/{card['id']}/transitions",
        json={
            "transition_code": "needs_clarification_to_meeting",
            "expected_revision": card["revision"],
        },
        headers=headers(user="manager-a", key=str(uuid4())),
    )
    assert resp_t2.status_code == 200, resp_t2.text
    card = resp_t2.json()

    with app.state.session_factory() as session:
        visits = session.scalars(
            select(StateVisit)
            .where(StateVisit.interaction_id == card["id"])
            .order_by(StateVisit.entered_at.asc())
        ).all()
        assert len(visits) == 3

        v1, v2, v3 = visits
        assert v1.state == "contact_search"
        assert v1.exited_at is not None

        assert v2.state == "needs_clarification"
        assert v2.exited_at is not None
        assert v2.duration_seconds is not None
        assert v2.duration_seconds >= 0.0

        assert v3.state == "meeting"
        assert v3.entered_at is not None
        assert v3.exited_at is None
        assert v3.duration_seconds is None


def test_state_visit_duration_calculation_accuracy(app):
    """Verify duration_seconds accurately reflects the time delta between entered_at and exited_at."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")
        create_body = InteractionCreate(
            title="Точность расчета duration_seconds",
            organization_id="org-1",
            program_id="program-devops",
            product_id="product-cloud",
            cycle_label="2026/2027",
            owner_id="manager-a",
        )
        card_data = service_create_interaction(session, user, create_body, key=str(uuid4()))
        ix_id = card_data["id"]

        # Artificially shift entered_at 45 seconds into the past
        visit = session.scalars(
            select(StateVisit).where(StateVisit.interaction_id == ix_id)
        ).one()
        forty_five_sec_ago = utcnow() - timedelta(seconds=45)
        visit.entered_at = forty_five_sec_ago
        session.commit()

        # Perform transition
        trans_body = TransitionCommand(
            transition_code="contact_search_to_needs_clarification",
            expected_revision=1,
        )
        service_transition(session, user, ix_id, trans_body, key=str(uuid4()))

        # Reload visits
        v1 = session.scalars(
            select(StateVisit)
            .where(StateVisit.interaction_id == ix_id, StateVisit.state == "contact_search")
        ).one()

        assert v1.exited_at is not None
        assert v1.duration_seconds == pytest.approx(45.0, abs=1.5)


def test_state_visit_transition_to_terminal_state(client, app):
    """Verify transition to terminal state (e.g. cancelled) closes prior visit and opens terminal visit."""
    body = {
        "title": "Тест терминального StateVisit",
        "organization_id": "org-1",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "2026/2027",
        "owner_id": "manager-a",
    }
    resp = client.post(
        "/api/v1/interactions",
        json=body,
        headers=headers(user="manager-a", key=str(uuid4())),
    )
    assert resp.status_code == 201, resp.text
    card = resp.json()

    # Cancel interaction from contact_search
    resp_cancel = client.post(
        f"/api/v1/interactions/{card['id']}/transitions",
        json={
            "transition_code": "contact_search_to_cancelled",
            "expected_revision": card["revision"],
            "comment": "Отмена по запросу клиента",
        },
        headers=headers(user="manager-a", key=str(uuid4())),
    )
    assert resp_cancel.status_code == 200, resp_cancel.text

    with app.state.session_factory() as session:
        visits = session.scalars(
            select(StateVisit)
            .where(StateVisit.interaction_id == card["id"])
            .order_by(StateVisit.entered_at.asc())
        ).all()
        assert len(visits) == 2

        v_prior, v_term = visits
        assert v_prior.state == "contact_search"
        assert v_prior.exited_at is not None
        assert v_prior.duration_seconds is not None

        assert v_term.state == "cancelled"
        assert v_term.entered_at is not None
        assert v_term.exited_at is None
        assert v_term.duration_seconds is None


def test_state_visit_cascade_deletion(app):
    """Verify ON DELETE CASCADE cleans up state_visits when interaction is deleted."""
    with app.state.session_factory() as session:
        raw_ix = Interaction(
            id=str(uuid4()),
            title="Каскадное удаление StateVisit",
            organization_id="org-1",
            program_id="program-devops",
            product_id="product-cloud",
            cycle_label="2026/2027",
            owner_id="manager-a",
            state="contact_search",
            workflow_version=1,
            revision=1,
            visit_id=str(uuid4()),
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(raw_ix)
        session.flush()

        visit = StateVisit(
            id=str(uuid4()),
            interaction_id=raw_ix.id,
            state="contact_search",
            entered_at=utcnow(),
        )
        session.add(visit)
        session.commit()

        visits = session.scalars(
            select(StateVisit).where(StateVisit.interaction_id == raw_ix.id)
        ).all()
        assert len(visits) == 1

        # Delete the interaction
        session.delete(raw_ix)
        session.commit()

        remaining_visits = session.scalars(
            select(StateVisit).where(StateVisit.interaction_id == raw_ix.id)
        ).all()
        assert len(remaining_visits) == 0


def test_transition_without_prior_open_state_visit(app):
    """Verify transition succeeds even if interaction has no prior open StateVisit (legacy data)."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")
        # Create interaction without creating a StateVisit
        legacy_ix = Interaction(
            id=str(uuid4()),
            title="Устаревшее взаимодействие без визитов",
            organization_id="org-1",
            program_id="program-devops",
            product_id="product-cloud",
            cycle_label="2026/2027",
            owner_id="manager-a",
            team_id="team-alpha",
            state="contact_search",
            workflow_version=1,
            revision=1,
            visit_id=str(uuid4()),
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(legacy_ix)
        session.commit()

        # Perform transition
        trans_body = TransitionCommand(
            transition_code="contact_search_to_needs_clarification",
            expected_revision=1,
        )
        res = service_transition(session, user, legacy_ix.id, trans_body, key=str(uuid4()))
        assert res["state"] == "needs_clarification"

        # Verify new StateVisit was created
        visits = session.scalars(
            select(StateVisit).where(StateVisit.interaction_id == legacy_ix.id)
        ).all()
        assert len(visits) == 1
        assert visits[0].state == "needs_clarification"
        assert visits[0].exited_at is None


def test_freeze_report_dataset_and_get_frozen_rows(app):
    """Verify freeze_report_dataset persists ReportRun and ReportRow entities, and get_frozen_report_rows reads them."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")
        report_type = "pipeline_activity"
        params = {"team_id": "team-alpha", "as_of": "2026-09-23"}
        rows = [
            {"interaction_id": "ix-1", "state": "lead", "count": 5},
            {"interaction_id": "ix-2", "state": "meeting", "count": 3},
            {"interaction_id": "ix-3", "state": "completed", "count": 12},
        ]
        cutoff = datetime(2026, 9, 23, 18, 0, 0, tzinfo=timezone.utc)

        expected_p_hash = hashlib.sha256(
            json.dumps(params, default=str, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        expected_d_hash = hashlib.sha256(
            json.dumps(rows, default=str, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

        report_run = freeze_report_dataset(
            session,
            user=user,
            report_type=report_type,
            parameters=params,
            rows=rows,
            knowledge_cutoff=cutoff,
        )
        session.commit()

        assert report_run.id is not None
        assert report_run.requested_by == user.id
        assert report_run.report_type == report_type
        assert report_run.parameters == params
        assert report_run.parameters_hash == expected_p_hash
        assert report_run.dataset_checksum == expected_d_hash
        assert report_run.knowledge_cutoff == cutoff
        assert report_run.row_count == 3
        assert report_run.created_at is not None

        # Verify retrieval via get_frozen_report_rows
        fetched_rows = get_frozen_report_rows(session, report_run.id)
        assert fetched_rows == rows

        # Verify ordinals in database
        db_rows = session.scalars(
            select(ReportRow)
            .where(ReportRow.report_run_id == report_run.id)
            .order_by(ReportRow.ordinal.asc())
        ).all()
        assert len(db_rows) == 3
        assert [r.ordinal for r in db_rows] == [1, 2, 3]
        assert [r.row_data for r in db_rows] == rows


def test_freeze_report_dataset_empty_rows(app):
    """Verify freeze_report_dataset safely handles empty rows."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")
        report_run = freeze_report_dataset(
            session,
            user=user,
            report_type="empty_report",
            parameters={},
            rows=[],
        )
        session.commit()

        assert report_run.row_count == 0
        fetched_rows = get_frozen_report_rows(session, report_run.id)
        assert fetched_rows == []


def test_freeze_report_dataset_cascade_deletion(app):
    """Verify ON DELETE CASCADE deletes report_rows when ReportRun is deleted."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")
        report_run = freeze_report_dataset(
            session,
            user=user,
            report_type="cascade_test",
            parameters={"k": "v"},
            rows=[{"a": 1}, {"b": 2}],
        )
        session.commit()

        rr_id = report_run.id
        assert len(get_frozen_report_rows(session, rr_id)) == 2

        # Delete report_run
        run_obj = session.get(ReportRun, rr_id)
        session.delete(run_obj)
        session.commit()

        remaining_rows = session.scalars(
            select(ReportRow).where(ReportRow.report_run_id == rr_id)
        ).all()
        assert len(remaining_rows) == 0


def test_idempotent_transition_replay_does_not_duplicate_state_visits(client, app):
    """Verify replaying a transition with the same Idempotency-Key returns cached response without duplicating visits."""
    body = {
        "title": "Тест идемпотентного повтора переходов",
        "organization_id": "org-1",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "2026/2027",
        "owner_id": "manager-a",
    }
    resp = client.post(
        "/api/v1/interactions",
        json=body,
        headers=headers(user="manager-a", key=str(uuid4())),
    )
    assert resp.status_code == 201, resp.text
    card = resp.json()

    idem_key = str(uuid4())
    req_body = {
        "transition_code": "contact_search_to_needs_clarification",
        "expected_revision": card["revision"],
    }

    # First call
    r1 = client.post(
        f"/api/v1/interactions/{card['id']}/transitions",
        json=req_body,
        headers=headers(user="manager-a", key=idem_key),
    )
    assert r1.status_code == 200

    # Second call (replay)
    r2 = client.post(
        f"/api/v1/interactions/{card['id']}/transitions",
        json=req_body,
        headers=headers(user="manager-a", key=idem_key),
    )
    assert r2.status_code == 200
    assert r2.json()["revision"] == r1.json()["revision"]

    # Verify visit count is still exactly 2 (1 closed + 1 open), NOT 3
    with app.state.session_factory() as session:
        visits = session.scalars(
            select(StateVisit)
            .where(StateVisit.interaction_id == card["id"])
            .order_by(StateVisit.entered_at.asc())
        ).all()
        assert len(visits) == 2


def test_freeze_report_dataset_with_datetime_and_complex_types(app):
    """Verify freeze_report_dataset handles nested JSON structures and ISO datetime strings in parameters/rows."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")
        iso_str = "2026-09-23T12:00:00Z"
        params = {
            "since": iso_str,
            "nested": {"tags": ["crm", "temporal"], "active": True},
        }
        rows = [
            {"created": iso_str, "metrics": {"duration": 120.5}},
        ]
        run = freeze_report_dataset(
            session,
            user=user,
            report_type="complex_report",
            parameters=params,
            rows=rows,
        )
        session.commit()

        assert run.id is not None
        assert run.parameters_hash is not None
        assert len(run.parameters_hash) == 64
        assert run.dataset_checksum is not None
        assert len(run.dataset_checksum) == 64


def test_concurrent_state_transitions_cas_conflict_atomicity(client, app):
    """Adversarial stress: concurrent threads attempting to transition the same card with the same expected_revision.
    
    Verifies that:
    1. Exactly one thread succeeds (200), and all other threads receive 409 REVISION_CONFLICT.
    2. Only ONE new StateVisit is committed.
    3. The previous StateVisit is closed exactly once.
    4. Failed threads leave zero orphan StateVisits or uncommitted state mutations.
    """
    import concurrent.futures

    body = {
        "title": "Тест конкурентных переходов StateVisit",
        "organization_id": "org-1",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "2026/2027",
        "owner_id": "manager-a",
    }
    resp = client.post("/api/v1/interactions", json=body, headers=headers(user="manager-a", key=str(uuid4())))
    assert resp.status_code == 201
    card = resp.json()

    ix_id = card["id"]
    exp_rev = card["revision"]

    def attempt_transition(thread_idx):
        from fastapi.testclient import TestClient
        # Create thread-local TestClient sharing the same app instance
        thread_client = TestClient(app)
        res = thread_client.post(
            f"/api/v1/interactions/{ix_id}/transitions",
            json={
                "transition_code": "contact_search_to_needs_clarification",
                "expected_revision": exp_rev,
            },
            headers={"X-Demo-User": "manager-a", "Idempotency-Key": str(uuid4())},
        )
        return res.status_code, res.text

    thread_count = 8
    with concurrent.futures.ThreadPoolExecutor(max_workers=thread_count) as executor:
        futures = [executor.submit(attempt_transition, i) for i in range(thread_count)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    successes = [r for r in results if r[0] == 200]
    conflicts = [r for r in results if r[0] == 409]

    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}: {results}"
    assert len(conflicts) == thread_count - 1, f"Expected {thread_count - 1} conflicts, got {len(conflicts)}"

    with app.state.session_factory() as session:
        ix = session.get(Interaction, ix_id)
        assert ix.revision == exp_rev + 1
        assert ix.state == "needs_clarification"

        visits = session.scalars(
            select(StateVisit)
            .where(StateVisit.interaction_id == ix_id)
            .order_by(StateVisit.entered_at.asc())
        ).all()
        # Exactly 2 visits: 1 closed for contact_search, 1 open for needs_clarification
        assert len(visits) == 2
        assert visits[0].state == "contact_search"
        assert visits[0].exited_at is not None
        assert visits[0].duration_seconds is not None

        assert visits[1].state == "needs_clarification"
        assert visits[1].exited_at is None
        assert visits[1].duration_seconds is None


def test_sequential_multi_state_chain_and_sla_durations(client, app):
    """Adversarial test: chain of sequential transitions verifying continuous timestamp links and cumulative SLA duration."""
    body = {
        "title": "Тест цепочки переходов SLA",
        "organization_id": "org-1",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "2026/2027",
        "owner_id": "manager-a",
    }
    resp = client.post("/api/v1/interactions", json=body, headers=headers(user="manager-a", key=str(uuid4())))
    assert resp.status_code == 201
    card = resp.json()
    ix_id = card["id"]

    transitions = [
        ("contact_search_to_needs_clarification", "needs_clarification"),
        ("needs_clarification_to_meeting", "meeting"),
        ("meeting_to_document_exchange", "document_exchange"),
        ("document_exchange_to_document_signing", "document_signing"),
    ]

    for trans_code, expected_state in transitions:
        t_res = client.post(
            f"/api/v1/interactions/{ix_id}/transitions",
            json={
                "transition_code": trans_code,
                "expected_revision": card["revision"],
            },
            headers=headers(user="manager-a", key=str(uuid4())),
        )
        assert t_res.status_code == 200, t_res.text
        card = t_res.json()
        assert card["state"] == expected_state

    with app.state.session_factory() as session:
        visits = session.scalars(
            select(StateVisit)
            .where(StateVisit.interaction_id == ix_id)
            .order_by(StateVisit.entered_at.asc())
        ).all()
        assert len(visits) == 5

        # Verify visits 0, 1, 2, 3 are closed and continuous
        for i in range(4):
            v_curr = visits[i]
            v_next = visits[i + 1]
            assert v_curr.exited_at is not None
            assert v_curr.duration_seconds is not None
            assert v_curr.duration_seconds >= 0.0
            # Timestamp continuity: exited_at matches entered_at of next visit
            assert v_curr.exited_at == v_next.entered_at

        # Final visit is open
        v_final = visits[4]
        assert v_final.state == "document_signing"
        assert v_final.exited_at is None
        assert v_final.duration_seconds is None


def test_multiple_open_visits_auto_healing_on_transition(app):
    """Verify that if data corruption resulted in multiple open StateVisits, transition heals all of them."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")
        raw_ix = Interaction(
            id=str(uuid4()),
            title="Тест исправления нескольких открытых визитов",
            organization_id="org-1",
            program_id="program-devops",
            product_id="product-cloud",
            cycle_label="2026/2027",
            owner_id="manager-a",
            team_id="team-alpha",
            state="contact_search",
            workflow_version=1,
            revision=1,
            visit_id=str(uuid4()),
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(raw_ix)
        session.flush()

        # Artificially inject TWO open visits
        v1 = StateVisit(
            id=str(uuid4()),
            interaction_id=raw_ix.id,
            state="contact_search",
            entered_at=utcnow() - timedelta(minutes=10),
            exited_at=None,
        )
        v2 = StateVisit(
            id=str(uuid4()),
            interaction_id=raw_ix.id,
            state="contact_search",
            entered_at=utcnow() - timedelta(minutes=5),
            exited_at=None,
        )
        session.add_all([v1, v2])
        session.commit()

        # Perform transition
        trans_body = TransitionCommand(
            transition_code="contact_search_to_needs_clarification",
            expected_revision=1,
        )
        service_transition(session, user, raw_ix.id, trans_body, key=str(uuid4()))

        # Reload visits
        visits = session.scalars(
            select(StateVisit)
            .where(StateVisit.interaction_id == raw_ix.id)
            .order_by(StateVisit.entered_at.asc())
        ).all()

        assert len(visits) == 3
        # Both prior visits should now be cleanly closed
        assert visits[0].exited_at is not None
        assert visits[0].duration_seconds is not None
        assert visits[0].duration_seconds > 0.0

        assert visits[1].exited_at is not None
        assert visits[1].duration_seconds is not None
        assert visits[1].duration_seconds > 0.0

        # Exactly one new open visit exists
        assert visits[2].state == "needs_clarification"
        assert visits[2].exited_at is None


def test_freeze_report_dataset_with_generator_and_naive_cutoff(app):
    """Verify freeze_report_dataset handles generators/iterators and timezone-naive cutoff."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")

        # Generator of rows
        def row_generator():
            for i in range(10):
                yield {"row_idx": i, "metric": i * 1.5}

        naive_cutoff = datetime(2026, 9, 23, 14, 30, 0)

        run = freeze_report_dataset(
            session,
            user=user,
            report_type="generator_report",
            parameters=None,  # None parameters should safely default to {}
            rows=row_generator(),
            knowledge_cutoff=naive_cutoff,
        )
        session.commit()

        assert run.row_count == 10
        assert run.parameters == {}
        assert run.parameters_hash is not None
        assert run.dataset_checksum is not None
        assert run.knowledge_cutoff is not None
        assert run.knowledge_cutoff.tzinfo == timezone.utc

        fetched = get_frozen_report_rows(session, run.id)
        assert len(fetched) == 10
        assert fetched[0] == {"row_idx": 0, "metric": 0.0}
        assert fetched[9] == {"row_idx": 9, "metric": 13.5}


def test_get_frozen_report_rows_non_existent_raises_404(app):
    """Verify get_frozen_report_rows raises APIError NOT_FOUND (404) for non-existent report run id."""
    from app.errors import APIError

    with app.state.session_factory() as session:
        with pytest.raises(APIError) as exc_info:
            get_frozen_report_rows(session, "non_existent_run_id_99999")
        assert exc_info.value.code == "NOT_FOUND"
        assert exc_info.value.status_code == 404


def test_workflow_migration_state_visit_synchronization(app):
    """Verify workflow migration closes prior StateVisit and opens new StateVisit when state changes."""
    from app.services import commit_workflow_migration

    with app.state.session_factory() as session:
        supervisor = session.get(User, "supervisor")
        user = session.get(User, "manager-a")

        create_body = InteractionCreate(
            title="Миграция и StateVisit",
            organization_id="org-1",
            program_id="program-devops",
            product_id="product-cloud",
            cycle_label="2026/2027",
            owner_id="manager-a",
        )
        card_data = service_create_interaction(session, user, create_body, key=str(uuid4()))
        ix_id = card_data["id"]

        # Card is in contact_search (version 1). Map contact_search -> needs_clarification in v2
        from app.workflow import get_states
        mapping = {k: k for k in get_states(1).keys()}
        mapping["contact_search"] = "needs_clarification"

        commit_res = commit_workflow_migration(
            db=session,
            user=supervisor,
            from_version=1,
            to_version=2,
            status_mapping=mapping,
            idempotency_key=str(uuid4()),
        )
        assert commit_res["status"] == "migrated"

        # Check StateVisits
        visits = session.scalars(
            select(StateVisit)
            .where(StateVisit.interaction_id == ix_id)
            .order_by(StateVisit.entered_at.asc())
        ).all()

        assert len(visits) == 2
        v_prior, v_migrated = visits

        assert v_prior.state == "contact_search"
        assert v_prior.exited_at is not None
        assert v_prior.duration_seconds is not None

        assert v_migrated.state == "needs_clarification"
        assert v_migrated.exited_at is None
        assert v_migrated.duration_seconds is None


def test_clock_skew_backwards_time_clamped_to_zero(app):
    """Verify that if system clock moves backwards, duration_seconds is safely clamped to 0.0 without crash."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")
        card_data = service_create_interaction(
            session,
            user,
            InteractionCreate(
                title="Тест отрицательного времени",
                organization_id="org-1",
                program_id="program-devops",
                product_id="product-cloud",
                cycle_label="2026/2027",
                owner_id="manager-a",
            ),
            key=str(uuid4()),
        )
        ix_id = card_data["id"]

        # Shift entered_at 1 hour into the FUTURE
        visit = session.scalars(select(StateVisit).where(StateVisit.interaction_id == ix_id)).one()
        visit.entered_at = utcnow() + timedelta(hours=1)
        session.commit()

        # Transition
        service_transition(
            session,
            user,
            ix_id,
            TransitionCommand(
                transition_code="contact_search_to_needs_clarification",
                expected_revision=1,
            ),
            key=str(uuid4()),
        )

        v_reloaded = session.scalars(
            select(StateVisit).where(StateVisit.interaction_id == ix_id, StateVisit.state == "contact_search")
        ).one()
        assert v_reloaded.exited_at is not None
        assert v_reloaded.duration_seconds == 0.0


def test_freeze_report_dataset_large_volume_and_cascade(app):
    """Verify freeze_report_dataset with 500 rows, checksum verification, and cascade delete."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")
        rows = [{"row_id": f"row-{i}", "val": i * 10, "label": f"label-{i}"} for i in range(500)]

        run = freeze_report_dataset(
            session,
            user=user,
            report_type="large_volume_test",
            parameters={"size": 500},
            rows=rows,
        )
        session.commit()

        assert run.row_count == 500
        run_id = run.id

        # Verify all rows retrieved in order
        retrieved = get_frozen_report_rows(session, run_id)
        assert len(retrieved) == 500
        assert retrieved[0]["row_id"] == "row-0"
        assert retrieved[499]["row_id"] == "row-499"

        # Cascade delete
        session.delete(session.get(ReportRun, run_id))
        session.commit()

        remaining = session.scalars(select(ReportRow).where(ReportRow.report_run_id == run_id)).all()
        assert len(remaining) == 0


def test_freeze_report_dataset_with_python_datetime_uuid_decimal(app):
    """Adversarial test: verify freeze_report_dataset handles native datetime, date, UUID, and Decimal objects without flush failure."""
    from datetime import date
    from decimal import Decimal
    from app.errors import APIError

    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")
        raw_uuid = uuid4()
        now_dt = utcnow()
        today = date(2026, 9, 23)
        amount = Decimal("12345.67")

        params = {
            "query_uuid": raw_uuid,
            "effective_date": today,
            "as_of": now_dt,
            "threshold": amount,
        }
        rows = [
            {"row_id": uuid4(), "created_at": now_dt, "revenue": Decimal("999.99"), "date": today},
            {"row_id": uuid4(), "created_at": now_dt, "revenue": Decimal("500.00"), "date": today},
        ]

        run = freeze_report_dataset(
            session,
            user=user,
            report_type="complex_types_report",
            parameters=params,
            rows=rows,
        )
        session.commit()

        assert run.id is not None
        assert run.row_count == 2

        # Verify get_frozen_report_rows returns rows and matches dataset_checksum
        retrieved = get_frozen_report_rows(session, run.id)
        assert len(retrieved) == 2
        assert retrieved[0]["revenue"] == "999.99"
        assert retrieved[1]["revenue"] == "500.00"

        recomputed_hash = hashlib.sha256(
            json.dumps(retrieved, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        assert recomputed_hash == run.dataset_checksum


def test_freeze_report_dataset_validation_errors(app):
    """Adversarial test: verify freeze_report_dataset rejects empty or oversized report_type."""
    from app.errors import APIError

    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")

        with pytest.raises(APIError) as exc1:
            freeze_report_dataset(session, user, report_type="", parameters={}, rows=[])
        assert exc1.value.code == "VALIDATION_ERROR"
        assert exc1.value.status_code == 422

        with pytest.raises(APIError) as exc2:
            freeze_report_dataset(session, user, report_type="   ", parameters={}, rows=[])
        assert exc2.value.code == "VALIDATION_ERROR"
        assert exc2.value.status_code == 422

        with pytest.raises(APIError) as exc3:
            freeze_report_dataset(session, user, report_type="x" * 51, parameters={}, rows=[])
        assert exc3.value.code == "VALIDATION_ERROR"
        assert exc3.value.status_code == 422


def test_get_frozen_report_rows_empty_or_whitespace_raises_404(app):
    """Adversarial test: verify get_frozen_report_rows raises 404 for empty, whitespace, or None report_run_id."""
    from app.errors import APIError

    with app.state.session_factory() as session:
        for bad_id in ["", "   ", None]:
            with pytest.raises(APIError) as exc:
                get_frozen_report_rows(session, bad_id)
            assert exc.value.code == "NOT_FOUND"
            assert exc.value.status_code == 404


def test_state_visit_timezones_cross_offset_arithmetic(app):
    """Adversarial test: verify duration_seconds calculation handles different timezone offsets (+03:00, +05:00)."""
    from datetime import timezone as tz

    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")
        card = service_create_interaction(
            session,
            user,
            InteractionCreate(
                title="Тест временных зон",
                organization_id="org-1",
                program_id="program-devops",
                product_id="product-cloud",
                cycle_label="2026/2027",
                owner_id="manager-a",
            ),
            key=str(uuid4()),
        )
        ix_id = card["id"]

        # Set entered_at to a specific timezone with +05:00 offset (e.g. Yekaterinburg) 60 seconds ago
        tz_plus5 = tz(timedelta(hours=5))
        past_time_plus5 = datetime.now(tz_plus5) - timedelta(seconds=60)
        visit = session.scalars(select(StateVisit).where(StateVisit.interaction_id == ix_id)).one()
        visit.entered_at = past_time_plus5
        session.commit()

        # Transition card
        service_transition(
            session,
            user,
            ix_id,
            TransitionCommand(
                transition_code="contact_search_to_needs_clarification",
                expected_revision=1,
            ),
            key=str(uuid4()),
        )

        v_closed = session.scalars(
            select(StateVisit).where(StateVisit.interaction_id == ix_id, StateVisit.state == "contact_search")
        ).one()
        assert v_closed.exited_at is not None
        assert v_closed.duration_seconds == pytest.approx(60.0, abs=1.5)


def test_freeze_report_dataset_with_non_dict_row_elements(app):
    """Adversarial test: verify freeze_report_dataset safely normalizes scalar/list rows."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")
        rows = [123, "text_row", ["nested", 1]]

        run = freeze_report_dataset(
            session,
            user=user,
            report_type="non_dict_rows",
            parameters={"test": 1},
            rows=rows,
        )
        session.commit()

        assert run.row_count == 3
        retrieved = get_frozen_report_rows(session, run.id)
        assert len(retrieved) == 3
        assert retrieved[0] == {"value": 123}
        assert retrieved[1] == {"value": "text_row"}
        assert retrieved[2] == {"value": ["nested", 1]}


def test_freeze_report_dataset_with_string_and_date_knowledge_cutoff(app):
    """Adversarial test (Round 3): verify freeze_report_dataset supports ISO string and date knowledge_cutoff without crashing."""
    from datetime import date
    from app.errors import APIError

    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")

        # 1. ISO string with Z
        run1 = freeze_report_dataset(
            session,
            user=user,
            report_type="iso_str_cutoff",
            parameters={},
            rows=[{"k": 1}],
            knowledge_cutoff="2026-09-23T14:30:00Z",
        )
        assert run1.knowledge_cutoff is not None
        assert run1.knowledge_cutoff.tzinfo == timezone.utc
        assert run1.knowledge_cutoff.hour == 14
        assert run1.knowledge_cutoff.minute == 30

        # 2. Date object
        today = date(2026, 9, 23)
        run2 = freeze_report_dataset(
            session,
            user=user,
            report_type="date_obj_cutoff",
            parameters={},
            rows=[{"k": 2}],
            knowledge_cutoff=today,
        )
        assert run2.knowledge_cutoff is not None
        assert run2.knowledge_cutoff.tzinfo == timezone.utc
        assert run2.knowledge_cutoff.year == 2026
        assert run2.knowledge_cutoff.month == 9
        assert run2.knowledge_cutoff.day == 23

        # 3. Invalid string format raises 422
        with pytest.raises(APIError) as exc_inv:
            freeze_report_dataset(
                session,
                user=user,
                report_type="bad_str_cutoff",
                parameters={},
                rows=[],
                knowledge_cutoff="invalid-date-format-xyz",
            )
        assert exc_inv.value.code == "VALIDATION_ERROR"
        assert exc_inv.value.status_code == 422

        # 4. Invalid cutoff type (e.g. integer or list) raises 422
        with pytest.raises(APIError) as exc_type:
            freeze_report_dataset(
                session,
                user=user,
                report_type="bad_type_cutoff",
                parameters={},
                rows=[],
                knowledge_cutoff=12345678,
            )
        assert exc_type.value.code == "VALIDATION_ERROR"
        assert exc_type.value.status_code == 422

        # 5. user is None raises 401
        with pytest.raises(APIError) as exc_user:
            freeze_report_dataset(
                session,
                user=None,
                report_type="no_user",
                parameters={},
                rows=[],
            )
        assert exc_user.value.code == "UNAUTHORIZED"
        assert exc_user.value.status_code == 401


def test_get_frozen_report_rows_with_whitespace_and_uuid_types(app):
    """Adversarial test (Round 3): verify get_frozen_report_rows supports whitespace-padded IDs and UUID instances."""
    from uuid import UUID

    with app.state.session_factory() as session:
        user = session.get(User, "manager-a")
        run = freeze_report_dataset(
            session,
            user=user,
            report_type="whitespace_uuid_test",
            parameters={"q": "test"},
            rows=[{"idx": 1}, {"idx": 2}],
        )
        session.commit()

        # Whitespace-padded string ID
        padded_id = f"   {run.id}   "
        rows_from_padded = get_frozen_report_rows(session, padded_id)
        assert len(rows_from_padded) == 2
        assert rows_from_padded[0]["idx"] == 1

        # UUID object instance (if ID is UUID format or can be cast)
        # Verify str casting works for arbitrary object with __str__
        class CustomIdHolder:
            def __str__(self):
                return run.id

        rows_from_obj = get_frozen_report_rows(session, CustomIdHolder())
        assert len(rows_from_obj) == 2



