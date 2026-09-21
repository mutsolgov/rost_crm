"""Workflow Migration Stress Challenger test suite (challenger_1_4).

Empirical verification of:
1. Complex many-to-one status mapping collisions.
2. Out-of-bounds / non-existent status mapping values.
3. Concurrent migration attempts with the same or different Idempotency-Key.
4. Re-migration from v2 back to v1 (and v2 to v2 rejection).
5. Tampering with CAS revision during migration.
6. Verification that interactions with extensive existing history, multiple comments,
   and multiple attachments preserve 100% of their relationships and sequence integrity post-migration.
7. Verification that RBAC strictly rejects manager roles with 403 Forbidden.
"""
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from app.workflow import get_states, get_transitions, get_workflow


def headers(user="supervisor", key=None):
    res = {"X-Demo-User": user}
    if key:
        res["Idempotency-Key"] = key
    return res


def full_identity_mapping(from_ver=1, to_ver=2):
    states = get_states(from_ver)
    return {k: k for k in states.keys()}


def create_test_card(
    client,
    user="manager-a",
    title="Stress Interaction Card",
    org_id=None,
    program_id="program-devops",
    product_id="product-cloud",
):
    if org_id is None:
        org_id = "org-2" if user == "manager-b" else "org-1"
    body = {
        "title": title,
        "organization_id": org_id,
        "program_id": program_id,
        "product_id": product_id,
        "cycle_label": "Цикл 2026-Стресс",
        "owner_id": user,
    }
    resp = client.post("/api/v1/interactions", json=body, headers=headers(user, str(uuid4())))
    assert resp.status_code == 201, resp.text
    return resp.json()


# ==============================================================================
# 1. Complex Many-to-One Status Mapping Collisions
# ==============================================================================


def test_stress_many_to_one_collision_preview_and_commit(client):
    """Multiple active states mapped into one target state.

    Both preview collision reporting and commit atomicity must succeed,
    incrementing revision and recording exact original states in audit events.
    """
    # 1. Prepare cards in 5 distinct workflow states
    # Card 1: contact_search
    card1 = create_test_card(client, "manager-a", "Карточка 1: contact_search")

    # Card 2: needs_clarification
    card2 = create_test_card(client, "manager-a", "Карточка 2: needs_clarification")
    r2 = client.post(
        f"/api/v1/interactions/{card2['id']}/transitions",
        json={"transition_code": "contact_search_to_needs_clarification", "expected_revision": card2["revision"]},
        headers=headers("manager-a", str(uuid4())),
    )
    assert r2.status_code == 200

    # Card 3: meeting
    card3 = create_test_card(client, "manager-a", "Карточка 3: meeting")
    client.post(
        f"/api/v1/interactions/{card3['id']}/transitions",
        json={"transition_code": "contact_search_to_needs_clarification", "expected_revision": card3["revision"]},
        headers=headers("manager-a", str(uuid4())),
    )
    r3 = client.post(
        f"/api/v1/interactions/{card3['id']}/transitions",
        json={"transition_code": "needs_clarification_to_meeting", "expected_revision": card3["revision"] + 1},
        headers=headers("manager-a", str(uuid4())),
    )
    assert r3.status_code == 200

    # Card 4: document_exchange
    card4 = create_test_card(client, "manager-a", "Карточка 4: document_exchange")
    client.post(
        f"/api/v1/interactions/{card4['id']}/transitions",
        json={"transition_code": "contact_search_to_needs_clarification", "expected_revision": card4["revision"]},
        headers=headers("manager-a", str(uuid4())),
    )
    client.post(
        f"/api/v1/interactions/{card4['id']}/transitions",
        json={"transition_code": "needs_clarification_to_meeting", "expected_revision": card4["revision"] + 1},
        headers=headers("manager-a", str(uuid4())),
    )
    r4 = client.post(
        f"/api/v1/interactions/{card4['id']}/transitions",
        json={"transition_code": "meeting_to_document_exchange", "expected_revision": card4["revision"] + 2},
        headers=headers("manager-a", str(uuid4())),
    )
    assert r4.status_code == 200

    # Card 5: document_revision
    card5 = create_test_card(client, "manager-a", "Карточка 5: document_revision")
    client.post(
        f"/api/v1/interactions/{card5['id']}/transitions",
        json={"transition_code": "contact_search_to_needs_clarification", "expected_revision": card5["revision"]},
        headers=headers("manager-a", str(uuid4())),
    )
    client.post(
        f"/api/v1/interactions/{card5['id']}/transitions",
        json={"transition_code": "needs_clarification_to_meeting", "expected_revision": card5["revision"] + 1},
        headers=headers("manager-a", str(uuid4())),
    )
    client.post(
        f"/api/v1/interactions/{card5['id']}/transitions",
        json={"transition_code": "meeting_to_document_exchange", "expected_revision": card5["revision"] + 2},
        headers=headers("manager-a", str(uuid4())),
    )
    r5 = client.post(
        f"/api/v1/interactions/{card5['id']}/transitions",
        json={"transition_code": "document_exchange_to_document_revision", "expected_revision": card5["revision"] + 3},
        headers=headers("manager-a", str(uuid4())),
    )
    assert r5.status_code == 200

    # 2. Build 5-to-1 collision mapping where all 5 states map to 'meeting'
    mapping = full_identity_mapping(1, 2)
    mapping["contact_search"] = "meeting"
    mapping["needs_clarification"] = "meeting"
    mapping["document_exchange"] = "meeting"
    mapping["document_revision"] = "meeting"
    # mapping['meeting'] is already 'meeting'

    body = {"from_version": 1, "to_version": 2, "status_mapping": mapping}

    # 3. Test Preview
    preview_resp = client.post("/api/v1/workflow/migrate/preview", json=body, headers=headers("supervisor"))
    assert preview_resp.status_code == 200
    prev = preview_resp.json()

    assert prev["is_valid"] is True
    assert prev["unmapped_statuses"] == []
    assert prev["affected_interactions_count"] >= 5

    # Check collision details in preview
    meeting_col = next((c for c in prev["collisions"] if c["target_status"] == "meeting"), None)
    assert meeting_col is not None, "Expected collision for target_status='meeting'"
    expected_sources = {"document_revision", "contact_search", "document_exchange", "meeting", "needs_clarification"}
    assert set(meeting_col["source_statuses"]) == expected_sources
    assert meeting_col["target_name"] in ("Проведение встречи", "Встреча с вузом")
    assert any("Коллизия" in w for w in prev["warnings"])

    # 4. Commit Migration
    idem_key = "stress-many-to-one-" + str(uuid4())
    commit_resp = client.post(
        "/api/v1/workflow/migrate/commit",
        json=body,
        headers=headers("administrator", idem_key),
    )
    assert commit_resp.status_code == 200
    comm = commit_resp.json()
    assert comm["status"] == "migrated"
    assert comm["status_distribution"]["meeting"] >= 5

    # 5. Verify cards post-migration
    for c_id, original_state in [
        (card1["id"], "contact_search"),
        (card2["id"], "needs_clarification"),
        (card3["id"], "meeting"),
        (card4["id"], "document_exchange"),
        (card5["id"], "document_revision"),
    ]:
        card = client.get(f"/api/v1/interactions/{c_id}", headers=headers("manager-a")).json()
        assert card["state"] == "meeting"
        assert card["workflow_version"] == 2

        # Check audit event
        last_event = card["events"][-1]
        assert last_event["type"] == "workflow_migrated"
        assert last_event["payload"]["from_state"] == original_state
        assert last_event["payload"]["to_state"] == "meeting"
        assert last_event["payload"]["from_version"] == 1
        assert last_event["payload"]["to_version"] == 2
        assert last_event["payload"]["new_revision"] == card["revision"]


def test_stress_all_active_collapse_to_single_state(client):
    """Stress test collapsing all active workflow states to 'classes'."""
    card_a = create_test_card(client, "manager-a", "Карточка А для схлопывания")
    card_b = create_test_card(client, "manager-b", "Карточка Б для схлопывания")

    v1_states = get_states(1)
    mapping = {}
    for st_code, st_data in v1_states.items():
        if st_data["kind"] == "terminal":
            mapping[st_code] = st_code
        else:
            mapping[st_code] = "classes"

    body = {"from_version": 1, "to_version": 2, "status_mapping": mapping}
    r_prev = client.post("/api/v1/workflow/migrate/preview", json=body, headers=headers("supervisor"))
    assert r_prev.status_code == 200
    assert r_prev.json()["is_valid"] is True

    r_comm = client.post(
        "/api/v1/workflow/migrate/commit",
        json=body,
        headers=headers("administrator", str(uuid4())),
    )
    assert r_comm.status_code == 200
    res = r_comm.json()
    assert res["status_distribution"]["classes"] >= 2

    # Verify both cards transitioned to classes
    for c_id, owner in [(card_a["id"], "manager-a"), (card_b["id"], "manager-b")]:
        detail = client.get(f"/api/v1/interactions/{c_id}", headers=headers(owner)).json()
        assert detail["state"] == "classes"
        assert detail["workflow_version"] == 2
        # In v2, classes can transition to completed, classes_to_teacher_training, classes_to_cancelled
        tr_codes = {t["code"] for t in detail["allowed_transitions"]}
        assert "classes_to_completed" in tr_codes


def test_stress_many_to_one_collision_into_terminal_state(client):
    """All active states mapped into terminal 'completed' or 'cancelled'.

    Must set closed_at, disallow further transitions, and correctly report collisions.
    """
    card = create_test_card(client, "manager-a", "Карточка для терминального схлопывания")

    v1_states = get_states(1)
    mapping = {}
    for st_code, st_data in v1_states.items():
        if st_code == "cancelled" or st_code == "contact_search":
            mapping[st_code] = "cancelled"
        else:
            mapping[st_code] = "completed"

    body = {"from_version": 1, "to_version": 2, "status_mapping": mapping}
    r_prev = client.post("/api/v1/workflow/migrate/preview", json=body, headers=headers("supervisor"))
    assert r_prev.status_code == 200
    p = r_prev.json()
    assert p["is_valid"] is True
    assert len(p["collisions"]) >= 1

    r_comm = client.post(
        "/api/v1/workflow/migrate/commit",
        json=body,
        headers=headers("supervisor", str(uuid4())),
    )
    assert r_comm.status_code == 200

    detail = client.get(f"/api/v1/interactions/{card['id']}", headers=headers("manager-a")).json()
    assert detail["state"] == "cancelled"
    assert detail["closed_at"] is not None
    assert detail["allowed_transitions"] == []

    # Attempt transition on terminal state must fail
    r_bad_tr = client.post(
        f"/api/v1/interactions/{card['id']}/transitions",
        json={"transition_code": "contact_search_to_needs_clarification", "expected_revision": detail["revision"]},
        headers=headers("manager-a", str(uuid4())),
    )
    assert r_bad_tr.status_code in (400, 409, 422)


# ==============================================================================
# 2. Out-of-Bounds / Non-Existent Status Mapping Values
# ==============================================================================


def test_stress_reject_unknown_source_and_target_statuses(client):
    """Non-existent source and target statuses must be rejected with 422 VALIDATION_ERROR."""
    mapping = full_identity_mapping(1, 2)

    # 1. Non-existent source status
    bad_source = dict(mapping)
    bad_source["non_existent_source_stage"] = "meeting"
    r1 = client.post(
        "/api/v1/workflow/migrate/preview",
        json={"from_version": 1, "to_version": 2, "status_mapping": bad_source},
        headers=headers("supervisor"),
    )
    assert r1.status_code == 422
    assert r1.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "non_existent_source_stage" in r1.json()["error"]["message"]

    r1_comm = client.post(
        "/api/v1/workflow/migrate/commit",
        json={"from_version": 1, "to_version": 2, "status_mapping": bad_source},
        headers=headers("supervisor", str(uuid4())),
    )
    assert r1_comm.status_code == 422

    # 2. Non-existent target status
    bad_target = dict(mapping)
    bad_target["contact_search"] = "hyperdrive_active_warp"
    r2 = client.post(
        "/api/v1/workflow/migrate/preview",
        json={"from_version": 1, "to_version": 2, "status_mapping": bad_target},
        headers=headers("supervisor"),
    )
    assert r2.status_code == 422
    assert r2.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "hyperdrive_active_warp" in r2.json()["error"]["message"]

    # 3. SQL injection in status mapping keys/values
    sql_inj = dict(mapping)
    sql_inj["'; DROP TABLE interactions; --"] = "meeting"
    r3 = client.post(
        "/api/v1/workflow/migrate/preview",
        json={"from_version": 1, "to_version": 2, "status_mapping": sql_inj},
        headers=headers("supervisor"),
    )
    assert r3.status_code == 422

    # 4. Path traversal / special characters
    path_trav = dict(mapping)
    path_trav["contact_search"] = "../../etc/passwd"
    r4 = client.post(
        "/api/v1/workflow/migrate/preview",
        json={"from_version": 1, "to_version": 2, "status_mapping": path_trav},
        headers=headers("supervisor"),
    )
    assert r4.status_code == 422


def test_stress_reject_out_of_bounds_versions(client):
    """Out-of-bounds versions (0, negative, > 2) must be rejected with 422."""
    mapping = full_identity_mapping(1, 2)

    invalid_versions = [
        (0, 2),
        (1, 0),
        (-1, 2),
        (1, -1),
        (1, 999),
        (999, 2),
        (100, 200),
    ]
    for from_v, to_v in invalid_versions:
        r = client.post(
            "/api/v1/workflow/migrate/preview",
            json={"from_version": from_v, "to_version": to_v, "status_mapping": mapping},
            headers=headers("supervisor"),
        )
        assert r.status_code == 422, f"Expected 422 for ({from_v}, {to_v}), got {r.status_code}"

        r_comm = client.post(
            "/api/v1/workflow/migrate/commit",
            json={"from_version": from_v, "to_version": to_v, "status_mapping": mapping},
            headers=headers("supervisor", str(uuid4())),
        )
        assert r_comm.status_code == 422, f"Expected 422 for ({from_v}, {to_v}) on commit"


def test_stress_reject_empty_mapping(client):
    """Empty status mapping must be rejected with 422 VALIDATION_ERROR."""
    r = client.post(
        "/api/v1/workflow/migrate/preview",
        json={"from_version": 1, "to_version": 2, "status_mapping": {}},
        headers=headers("supervisor"),
    )
    assert r.status_code == 422


def test_stress_reject_commit_with_unmapped_active_card_statuses(client):
    """If an active card has a status omitted from the mapping, commit strictly rejects with 422."""
    create_test_card(client, "manager-a", "Карточка в contact_search для теста пропуска статуса")

    partial = full_identity_mapping(1, 2)
    del partial["contact_search"]

    # Preview returns is_valid=False
    r_prev = client.post(
        "/api/v1/workflow/migrate/preview",
        json={"from_version": 1, "to_version": 2, "status_mapping": partial},
        headers=headers("supervisor"),
    )
    assert r_prev.status_code == 200
    assert r_prev.json()["is_valid"] is False
    assert "contact_search" in r_prev.json()["unmapped_statuses"]

    # Commit must reject with 422
    r_comm = client.post(
        "/api/v1/workflow/migrate/commit",
        json={"from_version": 1, "to_version": 2, "status_mapping": partial},
        headers=headers("administrator", str(uuid4())),
    )
    assert r_comm.status_code == 422
    assert r_comm.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "contact_search" in r_comm.json()["error"]["message"]


# ==============================================================================
# 3. Concurrent Migration Attempts with Idempotency-Key
# ==============================================================================


def test_stress_concurrent_migrations_same_idempotency_key(client):
    """Multiple concurrent commit requests with the exact same Idempotency-Key.

    All threads must succeed (200), return identical responses,
    and avoid double revision increments or duplicate audit events.
    """
    create_test_card(client, "manager-a", "Карточка для конкурентного коммита")
    mapping = full_identity_mapping(1, 2)
    idem_key = "wf-concurrent-" + str(uuid4())
    body = {"from_version": 1, "to_version": 2, "status_mapping": mapping}

    def send_migration(thread_idx):
        return client.post(
            "/api/v1/workflow/migrate/commit",
            json=body,
            headers=headers("supervisor", idem_key),
        )

    # Launch 5 concurrent requests
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(send_migration, i) for i in range(5)]
        responses = [f.result() for f in futures]

    for resp in responses:
        assert resp.status_code == 200
        assert resp.json()["status"] == "migrated"

    # All responses must be identical
    first_json = responses[0].json()
    for resp in responses[1:]:
        assert resp.json() == first_json

    # Check that interactions only received 1 workflow_migrated event
    card = client.get(f"/api/v1/interactions/{first_json['details'][0]['interaction_id']}", headers=headers("manager-a")).json()
    mig_events = [e for e in card["events"] if e["type"] == "workflow_migrated"]
    assert len(mig_events) == 1


def test_stress_sequential_migrations_different_keys_zero_leak(client):
    """Second migration from v1 to v2 after all v1 cards are migrated.

    Must cleanly report migrated_count=0 without error or double-migrating cards.
    """
    create_test_card(client, "manager-a", "Карточка для двойной последовательной миграции")
    mapping = full_identity_mapping(1, 2)

    # 1. First migration
    r1 = client.post(
        "/api/v1/workflow/migrate/commit",
        json={"from_version": 1, "to_version": 2, "status_mapping": mapping},
        headers=headers("supervisor", str(uuid4())),
    )
    assert r1.status_code == 200
    assert r1.json()["migrated_count"] >= 1

    # 2. Second migration with different Idempotency-Key
    r2 = client.post(
        "/api/v1/workflow/migrate/commit",
        json={"from_version": 1, "to_version": 2, "status_mapping": mapping},
        headers=headers("supervisor", str(uuid4())),
    )
    assert r2.status_code == 200
    res2 = r2.json()
    assert res2["migrated_count"] == 0
    assert res2["details"] == []


def test_stress_idempotency_key_boundary_limits(client):
    """Idempotency-Key length boundaries: 200 chars allowed, 201 chars rejected."""
    mapping = full_identity_mapping(1, 2)
    body = {"from_version": 1, "to_version": 2, "status_mapping": mapping}

    # Exactly 200 chars
    key_200 = "x" * 200
    r_exact = client.post(
        "/api/v1/workflow/migrate/commit",
        json=body,
        headers={"X-Demo-User": "supervisor", "Idempotency-Key": key_200},
    )
    assert r_exact.status_code == 200

    # 201 chars -> 422
    key_201 = "y" * 201
    r_overflow = client.post(
        "/api/v1/workflow/migrate/commit",
        json=body,
        headers={"X-Demo-User": "supervisor", "Idempotency-Key": key_201},
    )
    assert r_overflow.status_code == 422


# ==============================================================================
# 4. Re-Migration from v2 back to v1 (and v2 to v2 rejection)
# ==============================================================================


def test_stress_reject_same_version_migration(client):
    """Same-version migration (v1->v1 and v2->v2) must be strictly rejected with 422."""
    for v in (1, 2):
        mapping = full_identity_mapping(v, v)
        r_prev = client.post(
            "/api/v1/workflow/migrate/preview",
            json={"from_version": v, "to_version": v, "status_mapping": mapping},
            headers=headers("supervisor"),
        )
        assert r_prev.status_code == 422
        assert "Исходная и целевая версии workflow совпадают" in r_prev.json()["error"]["message"]

        r_comm = client.post(
            "/api/v1/workflow/migrate/commit",
            json={"from_version": v, "to_version": v, "status_mapping": mapping},
            headers=headers("supervisor", str(uuid4())),
        )
        assert r_comm.status_code == 422
        assert "Исходная и целевая версии workflow совпадают" in r_comm.json()["error"]["message"]


def test_stress_round_trip_migration_v1_to_v2_to_v1(client):
    """Full round-trip migration: v1 -> v2 -> v1 (rollback / downgrade).

    Verifies that cards correctly transition back to v1, transitions exclusive
    to v2 disappear in v1, and revision increments appropriately twice.
    """
    card = create_test_card(client, "manager-a", "Карточка для полного round-trip v1->v2->v1")

    # Advance to meeting
    client.post(
        f"/api/v1/interactions/{card['id']}/transitions",
        json={"transition_code": "contact_search_to_needs_clarification", "expected_revision": card["revision"]},
        headers=headers("manager-a", str(uuid4())),
    )
    r_meet = client.post(
        f"/api/v1/interactions/{card['id']}/transitions",
        json={"transition_code": "needs_clarification_to_meeting", "expected_revision": card["revision"] + 1},
        headers=headers("manager-a", str(uuid4())),
    )
    assert r_meet.status_code == 200

    # 1. Migrate v1 -> v2
    client.post(
        "/api/v1/workflow/migrate/commit",
        json={"from_version": 1, "to_version": 2, "status_mapping": full_identity_mapping(1, 2)},
        headers=headers("administrator", str(uuid4())),
    )

    detail_v2 = client.get(f"/api/v1/interactions/{card['id']}", headers=headers("manager-a")).json()
    assert detail_v2["workflow_version"] == 2
    v2_transitions = {t["code"] for t in detail_v2["allowed_transitions"]}
    assert "meeting_to_document_signing" in v2_transitions

    # 2. Reverse Migrate v2 -> v1
    v2_to_v1_mapping = full_identity_mapping(2, 1)
    prev_reverse = client.post(
        "/api/v1/workflow/migrate/preview",
        json={"from_version": 2, "to_version": 1, "status_mapping": v2_to_v1_mapping},
        headers=headers("supervisor"),
    )
    assert prev_reverse.status_code == 200
    assert prev_reverse.json()["is_valid"] is True
    assert prev_reverse.json()["affected_interactions_count"] >= 1

    commit_reverse = client.post(
        "/api/v1/workflow/migrate/commit",
        json={"from_version": 2, "to_version": 1, "status_mapping": v2_to_v1_mapping},
        headers=headers("administrator", str(uuid4())),
    )
    assert commit_reverse.status_code == 200
    assert commit_reverse.json()["migrated_count"] >= 1

    # 3. Verify card in v1 post-rollback
    detail_v1 = client.get(f"/api/v1/interactions/{card['id']}", headers=headers("manager-a")).json()
    assert detail_v1["workflow_version"] == 1
    assert detail_v1["revision"] == detail_v2["revision"] + 1

    v1_transitions = {t["code"] for t in detail_v1["allowed_transitions"]}
    # meeting_to_document_signing is exclusive to v2, so it MUST NOT be in v1
    assert "meeting_to_document_signing" not in v1_transitions
    assert "meeting_to_document_exchange" in v1_transitions

    # Check events have both migrations
    mig_events = [e for e in detail_v1["events"] if e["type"] == "workflow_migrated"]
    assert len(mig_events) == 2
    assert mig_events[0]["payload"]["from_version"] == 1
    assert mig_events[0]["payload"]["to_version"] == 2
    assert mig_events[1]["payload"]["from_version"] == 2
    assert mig_events[1]["payload"]["to_version"] == 1


# ==============================================================================
# 5. Tampering with CAS Revision During Migration
# ==============================================================================


def test_stress_cas_stale_revision_rejected_post_migration(client):
    """Client attempting CAS transition or PATCH with stale revision post-migration gets 409 Conflict."""
    card = create_test_card(client, "manager-a", "Карточка для проверки устаревшей ревизии")
    initial_rev = card["revision"]

    # Migration happens in background
    client.post(
        "/api/v1/workflow/migrate/commit",
        json={"from_version": 1, "to_version": 2, "status_mapping": full_identity_mapping(1, 2)},
        headers=headers("supervisor", str(uuid4())),
    )

    # 1. Attempt transition with stale initial_rev -> 409 CONFLICT
    r_tr = client.post(
        f"/api/v1/interactions/{card['id']}/transitions",
        json={"transition_code": "contact_search_to_needs_clarification", "expected_revision": initial_rev},
        headers=headers("manager-a", str(uuid4())),
    )
    assert r_tr.status_code == 409
    assert r_tr.json()["error"]["code"] in ("REVISION_CONFLICT", "CONCURRENCY_CONFLICT")

    # 2. Attempt PATCH with stale initial_rev -> 409 CONFLICT
    r_patch = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={"title": "Поддельное обновление", "expected_revision": initial_rev},
        headers=headers("manager-a", str(uuid4())),
    )
    assert r_patch.status_code == 409
    assert r_patch.json()["error"]["code"] in ("REVISION_CONFLICT", "CONCURRENCY_CONFLICT")

    # 3. Attempt comment with stale initial_rev -> 409 CONFLICT
    r_comm = client.post(
        f"/api/v1/interactions/{card['id']}/comments",
        json={"body": "Запоздалый комментарий", "expected_revision": initial_rev},
        headers=headers("manager-a", str(uuid4())),
    )
    assert r_comm.status_code == 409

    # 4. Refresh card and verify correct revision
    fresh = client.get(f"/api/v1/interactions/{card['id']}", headers=headers("manager-a")).json()
    assert fresh["revision"] == initial_rev + 1

    # Transition with fresh revision succeeds
    r_tr_ok = client.post(
        f"/api/v1/interactions/{card['id']}/transitions",
        json={"transition_code": "contact_search_to_needs_clarification", "expected_revision": fresh["revision"]},
        headers=headers("manager-a", str(uuid4())),
    )
    assert r_tr_ok.status_code == 200


def test_stress_cas_tampering_arbitrary_revision_values(client):
    """Tampering with negative, future, or zero revision numbers yields 409 CONFLICT."""
    card = create_test_card(client, "manager-a", "Карточка для подделки ревизий")

    tampered_revisions = [-999, -1, 0, 999999]
    for bad_rev in tampered_revisions:
        r = client.patch(
            f"/api/v1/interactions/{card['id']}",
            json={"title": "Хакерская правка", "expected_revision": bad_rev},
            headers=headers("manager-a", str(uuid4())),
        )
        assert r.status_code in (409, 422)


# ==============================================================================
# 6. Preservation of History, Comments, Attachments & Sequence Integrity
# ==============================================================================


def test_stress_deep_history_comments_attachments_integrity(client):
    """Verification that cards with multiple transitions, comments, and attachments

    preserve 100% of their relationships and sequence integrity post-migration.
    """
    card = create_test_card(client, "manager-a", "Комплексная карточка для аудита целостности")
    c_id = card["id"]

    # 1. Walk through transitions: contact_search -> needs_clarification -> meeting -> document_exchange
    r_tr1 = client.post(
        f"/api/v1/interactions/{c_id}/transitions",
        json={"transition_code": "contact_search_to_needs_clarification", "expected_revision": card["revision"]},
        headers=headers("manager-a", str(uuid4())),
    )
    assert r_tr1.status_code == 200

    r_tr2 = client.post(
        f"/api/v1/interactions/{c_id}/transitions",
        json={"transition_code": "needs_clarification_to_meeting", "expected_revision": r_tr1.json()["revision"]},
        headers=headers("manager-a", str(uuid4())),
    )
    assert r_tr2.status_code == 200

    r_tr3 = client.post(
        f"/api/v1/interactions/{c_id}/transitions",
        json={"transition_code": "meeting_to_document_exchange", "expected_revision": r_tr2.json()["revision"]},
        headers=headers("manager-a", str(uuid4())),
    )
    assert r_tr3.status_code == 200
    cur_rev = r_tr3.json()["revision"]

    # 2. Add 3 comments
    for i in range(1, 4):
        c_resp = client.post(
            f"/api/v1/interactions/{c_id}/comments",
            json={"body": f"Исторический комментарий #{i}", "expected_revision": cur_rev},
            headers=headers("manager-a", str(uuid4())),
        )
        assert c_resp.status_code == 201
        cur_rev = c_resp.json()["revision"]

    # 3. Add 2 valid attachments: PDF and PNG
    pdf_content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
    png_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"

    att_pdf = client.post(
        f"/api/v1/interactions/{c_id}/attachments",
        files={"file": ("historical_contract.pdf", pdf_content, "application/pdf")},
        headers=headers("manager-a"),
    )
    assert att_pdf.status_code == 201
    pdf_id = att_pdf.json()["id"]

    att_png = client.post(
        f"/api/v1/interactions/{c_id}/attachments",
        files={"file": ("audit_diagram.png", png_content, "image/png")},
        headers=headers("manager-a"),
    )
    assert att_png.status_code == 201
    png_id = att_png.json()["id"]

    # Refresh card before migration
    card_before = client.get(f"/api/v1/interactions/{c_id}", headers=headers("manager-a")).json()
    events_before = card_before["events"]
    comments_before = card_before["comments"]
    attachments_before = card_before["attachments"]

    assert len(comments_before) == 3
    assert len(attachments_before) == 2
    assert len(events_before) >= 8

    # Verify strictly monotonic consecutive sequence 1, 2, 3...
    seq_before = [e["sequence"] for e in events_before]
    assert seq_before == list(range(1, len(events_before) + 1))

    # 4. Execute Migration v1 -> v2
    client.post(
        "/api/v1/workflow/migrate/commit",
        json={"from_version": 1, "to_version": 2, "status_mapping": full_identity_mapping(1, 2)},
        headers=headers("administrator", str(uuid4())),
    )

    # 5. Verify card post-migration
    card_after = client.get(f"/api/v1/interactions/{c_id}", headers=headers("manager-a")).json()
    events_after = card_after["events"]

    # Exactly 1 new event added
    assert len(events_after) == len(events_before) + 1

    # Strict sequence integrity
    seq_after = [e["sequence"] for e in events_after]
    assert seq_after == list(range(1, len(events_after) + 1))

    # All prior events are preserved unmodified
    for i in range(len(events_before)):
        assert events_after[i]["id"] == events_before[i]["id"]
        assert events_after[i]["type"] == events_before[i]["type"]
        assert events_after[i]["sequence"] == events_before[i]["sequence"]
        assert events_after[i]["payload"] == events_before[i]["payload"]

    # Migration event is the final one
    mig_event = events_after[-1]
    assert mig_event["type"] == "workflow_migrated"
    assert mig_event["sequence"] == len(events_after)
    assert mig_event["payload"]["from_version"] == 1
    assert mig_event["payload"]["to_version"] == 2
    assert mig_event["payload"]["previous_revision"] == card_before["revision"]
    assert mig_event["payload"]["new_revision"] == card_after["revision"]

    # All comments are intact
    assert len(card_after["comments"]) == 3
    for i in range(3):
        assert card_after["comments"][i]["body"] == comments_before[i]["body"]
        assert card_after["comments"][i]["author"]["id"] == "manager-a"

    # All attachments are intact
    assert len(card_after["attachments"]) == 2
    for i in range(2):
        assert card_after["attachments"][i]["file_name"] == attachments_before[i]["file_name"]
        assert card_after["attachments"][i]["checksum"] == attachments_before[i]["checksum"]

    # Authorized download of attachments still functions
    dl_pdf = client.get(f"/api/v1/interactions/{c_id}/attachments/{pdf_id}/download", headers=headers("manager-a"))
    assert dl_pdf.status_code == 200
    assert dl_pdf.content == pdf_content

    dl_png = client.get(f"/api/v1/interactions/{c_id}/attachments/{png_id}/download", headers=headers("manager-a"))
    assert dl_png.status_code == 200
    assert dl_png.content == png_content

    # Foreign key relationships intact
    assert card_after["organization_id"] == card_before["organization_id"]
    assert card_after["owner_id"] == card_before["owner_id"]
    assert card_after["program_id"] == card_before["program_id"]
    assert card_after["product_id"] == card_before["product_id"]


# ==============================================================================
# 7. Verification that RBAC Strictly Rejects Manager Roles with 403 Forbidden
# ==============================================================================


def test_stress_rbac_strict_rejection_of_managers_and_anonymous(client):
    """RBAC validation: managers get 403, unauthenticated get 401, supervisor and admin get 200."""
    mapping = full_identity_mapping(1, 2)
    body = {"from_version": 1, "to_version": 2, "status_mapping": mapping}

    # 1. Preview RBAC
    # Managers -> 403
    for mgr in ("manager-a", "manager-b"):
        r_mgr = client.post("/api/v1/workflow/migrate/preview", json=body, headers=headers(mgr))
        assert r_mgr.status_code == 403
        assert r_mgr.json()["error"]["code"] == "FORBIDDEN"

    # Anonymous -> 401
    r_anon = client.post("/api/v1/workflow/migrate/preview", json=body)
    assert r_anon.status_code == 401
    assert r_anon.json()["error"]["code"] in ("UNAUTHORIZED", "UNAUTHENTICATED")

    # Supervisor -> 200
    r_sup = client.post("/api/v1/workflow/migrate/preview", json=body, headers=headers("supervisor"))
    assert r_sup.status_code == 200

    # Administrator -> 200
    r_adm = client.post("/api/v1/workflow/migrate/preview", json=body, headers=headers("administrator"))
    assert r_adm.status_code == 200

    # 2. Commit RBAC
    # Managers -> 403 even with valid key
    for mgr in ("manager-a", "manager-b"):
        r_mgr_c = client.post(
            "/api/v1/workflow/migrate/commit",
            json=body,
            headers=headers(mgr, str(uuid4())),
        )
        assert r_mgr_c.status_code == 403
        assert r_mgr_c.json()["error"]["code"] == "FORBIDDEN"

    # Anonymous -> 401
    r_anon_c = client.post(
        "/api/v1/workflow/migrate/commit",
        json=body,
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert r_anon_c.status_code == 401
    assert r_anon_c.json()["error"]["code"] in ("UNAUTHORIZED", "UNAUTHENTICATED")

    # Manager attempting to inject supervisor role in JSON -> still 403
    sneaky_body = dict(body)
    sneaky_body["role"] = "supervisor"
    sneaky_body["user"] = "administrator"
    r_sneaky = client.post(
        "/api/v1/workflow/migrate/commit",
        json=sneaky_body,
        headers=headers("manager-a", str(uuid4())),
    )
    assert r_sneaky.status_code in (403, 422)
