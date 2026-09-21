from datetime import datetime, timezone
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


def create_test_interaction(client, user="manager-a", title="Миграционный тест"):
    body = {
        "title": title,
        "organization_id": "org-1",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "Цикл 2026",
        "owner_id": user,
    }
    resp = client.post("/api/v1/interactions", json=body, headers=headers(user, str(uuid4())))
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_workflow_endpoint_versioning(client):
    r_default = client.get("/api/v1/workflow", headers=headers())
    assert r_default.status_code == 200
    data_default = r_default.json()
    assert data_default["version"] == 1
    assert len(data_default["states"]) == 15
    assert len(data_default["transitions"]) == 29

    r_v1 = client.get("/api/v1/workflow?version=1", headers=headers())
    assert r_v1.status_code == 200
    assert r_v1.json()["version"] == 1

    r_v2 = client.get("/api/v1/workflow?version=2", headers=headers())
    assert r_v2.status_code == 200
    data_v2 = r_v2.json()
    assert data_v2["version"] == 2
    assert len(data_v2["states"]) == 15
    assert len(data_v2["transitions"]) == 36

    trans_codes_v2 = {t["code"] for t in data_v2["transitions"]}
    assert "meeting_to_document_signing" in trans_codes_v2
    assert "materials_transfer_to_classes" in trans_codes_v2
    assert "classes_to_completed" in trans_codes_v2
    assert "deployment_to_materials_transfer" in trans_codes_v2
    assert "classes_to_teacher_training" in trans_codes_v2
    assert "document_signing_to_meeting" in trans_codes_v2

    r_bad = client.get("/api/v1/workflow?version=99", headers=headers())
    assert r_bad.status_code == 404


def test_workflow_migrate_rbac_manager_forbidden(client):
    mapping = full_identity_mapping(1, 2)
    body = {"from_version": 1, "to_version": 2, "status_mapping": mapping}

    r_prev = client.post("/api/v1/workflow/migrate/preview", json=body, headers=headers("manager-a"))
    assert r_prev.status_code == 403
    assert r_prev.json()["error"]["code"] == "FORBIDDEN"

    r_comm = client.post(
        "/api/v1/workflow/migrate/commit",
        json=body,
        headers=headers("manager-a", str(uuid4())),
    )
    assert r_comm.status_code == 403
    assert r_comm.json()["error"]["code"] == "FORBIDDEN"


def test_workflow_migrate_rbac_supervisor_and_admin_allowed(client):
    mapping = full_identity_mapping(1, 2)
    body = {"from_version": 1, "to_version": 2, "status_mapping": mapping}

    r_sup = client.post("/api/v1/workflow/migrate/preview", json=body, headers=headers("supervisor"))
    assert r_sup.status_code == 200
    assert r_sup.json()["from_version"] == 1
    assert r_sup.json()["to_version"] == 2

    r_adm = client.post("/api/v1/workflow/migrate/preview", json=body, headers=headers("administrator"))
    assert r_adm.status_code == 200


def test_workflow_migrate_reject_terminal_to_active(client):
    bad_mapping = full_identity_mapping(1, 2)
    bad_mapping["completed"] = "contact_search"
    body = {"from_version": 1, "to_version": 2, "status_mapping": bad_mapping}

    r_prev = client.post("/api/v1/workflow/migrate/preview", json=body, headers=headers("supervisor"))
    assert r_prev.status_code == 422
    assert r_prev.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "терминальный статус" in r_prev.json()["error"]["message"]

    bad_mapping_2 = full_identity_mapping(1, 2)
    bad_mapping_2["cancelled"] = "meeting"
    body_2 = {"from_version": 1, "to_version": 2, "status_mapping": bad_mapping_2}

    r_comm = client.post(
        "/api/v1/workflow/migrate/commit",
        json=body_2,
        headers=headers("administrator", str(uuid4())),
    )
    assert r_comm.status_code == 422
    assert r_comm.json()["error"]["code"] == "VALIDATION_ERROR"


def test_workflow_migrate_reject_invalid_versions_and_statuses(client):
    mapping = full_identity_mapping(1, 2)

    # Same version
    r_same = client.post(
        "/api/v1/workflow/migrate/preview",
        json={"from_version": 1, "to_version": 1, "status_mapping": mapping},
        headers=headers("supervisor"),
    )
    assert r_same.status_code == 422

    # Unknown version
    r_unk = client.post(
        "/api/v1/workflow/migrate/preview",
        json={"from_version": 1, "to_version": 99, "status_mapping": mapping},
        headers=headers("supervisor"),
    )
    assert r_unk.status_code == 422

    # Unknown target status
    bad_target = full_identity_mapping(1, 2)
    bad_target["contact_search"] = "nonexistent_status"
    r_bad_dst = client.post(
        "/api/v1/workflow/migrate/preview",
        json={"from_version": 1, "to_version": 2, "status_mapping": bad_target},
        headers=headers("supervisor"),
    )
    assert r_bad_dst.status_code == 422


def test_workflow_migrate_missing_idempotency_key(client):
    mapping = full_identity_mapping(1, 2)
    body = {"from_version": 1, "to_version": 2, "status_mapping": mapping}

    # Missing header
    r_miss = client.post("/api/v1/workflow/migrate/commit", json=body, headers=headers("supervisor"))
    assert r_miss.status_code == 422

    # Empty string / whitespace
    r_empty = client.post(
        "/api/v1/workflow/migrate/commit",
        json=body,
        headers={"X-Demo-User": "supervisor", "Idempotency-Key": "   "},
    )
    assert r_empty.status_code == 422

    # Too long (> 200 chars)
    r_long = client.post(
        "/api/v1/workflow/migrate/commit",
        json=body,
        headers={"X-Demo-User": "supervisor", "Idempotency-Key": "x" * 205},
    )
    assert r_long.status_code == 422


def test_workflow_migrate_preview_calculation_and_collisions(client):
    create_test_interaction(client, "manager-a", "Карточка для превью коллизий")
    mapping = full_identity_mapping(1, 2)
    # Merge needs_clarification into meeting -> N-to-1 collision
    mapping["needs_clarification"] = "meeting"

    body = {"from_version": 1, "to_version": 2, "status_mapping": mapping}
    r = client.post("/api/v1/workflow/migrate/preview", json=body, headers=headers("supervisor"))
    assert r.status_code == 200
    res = r.json()

    assert res["from_version"] == 1
    assert res["to_version"] == 2
    assert isinstance(res["affected_interactions_count"], int)
    assert res["affected_interactions_count"] >= 1
    assert "contact_search" in res["status_distribution_before"]
    assert res["unmapped_statuses"] == []
    assert res["is_valid"] is True

    # Check collision report
    collisions = res["collisions"]
    assert len(collisions) >= 1
    meeting_collision = next((c for c in collisions if c["target_status"] == "meeting"), None)
    assert meeting_collision is not None
    assert set(meeting_collision["source_statuses"]) == {"meeting", "needs_clarification"}
    assert any("Коллизия" in w for w in res["warnings"])


def test_workflow_migrate_preview_unmapped_status(client):
    create_test_interaction(client, "manager-a", "Карточка для проверки unmapped")
    # Mapping with missing contact_search
    partial_mapping = full_identity_mapping(1, 2)
    del partial_mapping["contact_search"]

    body = {"from_version": 1, "to_version": 2, "status_mapping": partial_mapping}
    r = client.post("/api/v1/workflow/migrate/preview", json=body, headers=headers("supervisor"))
    assert r.status_code == 200
    res = r.json()

    assert "contact_search" in res["unmapped_statuses"]
    assert res["is_valid"] is False
    assert any("Не все активные статусы сопоставлены" in w for w in res["warnings"])


def test_workflow_migrate_commit_atomic_execution(client):
    item = create_test_interaction(client, "manager-a", "Карточка для атомарного коммита")
    mapping = full_identity_mapping(1, 2)
    idem_key = str(uuid4())

    body = {"from_version": 1, "to_version": 2, "status_mapping": mapping}
    r = client.post(
        "/api/v1/workflow/migrate/commit",
        json=body,
        headers=headers("supervisor", idem_key),
    )
    assert r.status_code == 200
    res = r.json()
    assert res["status"] == "migrated"
    assert res["from_version"] == 1
    assert res["to_version"] == 2
    assert res["migrated_count"] >= 1

    # Check migrated card in database
    detail_resp = client.get(f"/api/v1/interactions/{item['id']}", headers=headers("manager-a"))
    assert detail_resp.status_code == 200
    card = detail_resp.json()
    assert card["workflow_version"] == 2
    assert card["revision"] == item["revision"] + 1


def test_workflow_migrate_preserves_history_comments_attachments(client):
    item = create_test_interaction(client, "manager-a", "Карточка с историей и файлами")

    # Add comment
    comm_resp = client.post(
        f"/api/v1/interactions/{item['id']}/comments",
        json={"body": "Важный комментарий перед миграцией", "expected_revision": item["revision"]},
        headers=headers("manager-a", str(uuid4())),
    )
    assert comm_resp.status_code == 201

    # Add attachment
    files = {"file": ("report.pdf", b"%PDF-1.4 test migration content", "application/pdf")}
    att_resp = client.post(
        f"/api/v1/interactions/{item['id']}/attachments",
        files=files,
        headers=headers("manager-a"),
    )
    assert att_resp.status_code == 201

    # Refresh card
    card_before = client.get(f"/api/v1/interactions/{item['id']}", headers=headers("manager-a")).json()
    assert len(card_before["comments"]) == 1
    assert len(card_before["attachments"]) == 1
    event_count_before = len(card_before["events"])

    # Migrate v1 -> v2 (target is v2 now for any remaining v1 cards)
    # If all were migrated in previous test, let's create a fresh card and migrate it!
    fresh_item = create_test_interaction(client, "manager-a", "Свежая карточка v1")
    # Add comment to fresh item
    client.post(
        f"/api/v1/interactions/{fresh_item['id']}/comments",
        json={"body": "Комментарий к свежей карточке", "expected_revision": fresh_item["revision"]},
        headers=headers("manager-a", str(uuid4())),
    )
    # Add attachment to fresh item
    client.post(
        f"/api/v1/interactions/{fresh_item['id']}/attachments",
        files={"file": ("doc.pdf", b"%PDF-1.4 test document", "application/pdf")},
        headers=headers("manager-a"),
    )

    mapping = full_identity_mapping(1, 2)
    r_commit = client.post(
        "/api/v1/workflow/migrate/commit",
        json={"from_version": 1, "to_version": 2, "status_mapping": mapping},
        headers=headers("administrator", str(uuid4())),
    )
    assert r_commit.status_code == 200

    card_after = client.get(f"/api/v1/interactions/{fresh_item['id']}", headers=headers("manager-a")).json()
    assert card_after["workflow_version"] == 2
    assert len(card_after["comments"]) == 1
    assert card_after["comments"][0]["body"] == "Комментарий к свежей карточке"
    assert len(card_after["attachments"]) == 1
    assert card_after["attachments"][0]["file_name"] == "doc.pdf"

    # Events: previous events + workflow_migrated
    migration_events = [e for e in card_after["events"] if e["type"] == "workflow_migrated"]
    assert len(migration_events) == 1
    mig_event = migration_events[0]
    assert mig_event["sequence"] == len(card_after["events"])


def test_workflow_migrate_idempotency_replay_and_conflict(client):
    create_test_interaction(client, "manager-a", "Идемпотентная карточка")
    mapping = full_identity_mapping(1, 2)
    idem_key = "wf-migrate-" + str(uuid4())

    body = {"from_version": 1, "to_version": 2, "status_mapping": mapping}
    r1 = client.post(
        "/api/v1/workflow/migrate/commit",
        json=body,
        headers=headers("supervisor", idem_key),
    )
    assert r1.status_code == 200
    res1 = r1.json()

    # Replay identical
    r2 = client.post(
        "/api/v1/workflow/migrate/commit",
        json=body,
        headers=headers("supervisor", idem_key),
    )
    assert r2.status_code == 200
    assert r2.json() == res1

    # Conflict with modified body
    body_conflict = {"from_version": 1, "to_version": 2, "status_mapping": {"meeting": "meeting"}}
    r3 = client.post(
        "/api/v1/workflow/migrate/commit",
        json=body_conflict,
        headers=headers("supervisor", idem_key),
    )
    assert r3.status_code == 409
    assert r3.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_v2_allowed_transitions_and_execution_after_migration(client):
    item = create_test_interaction(client, "manager-a", "Карточка для проверки переходов v2")
    # Advance to needs_clarification
    r_tr1 = client.post(
        f"/api/v1/interactions/{item['id']}/transitions",
        json={"transition_code": "contact_search_to_needs_clarification", "expected_revision": item["revision"]},
        headers=headers("manager-a", str(uuid4())),
    )
    assert r_tr1.status_code == 200

    # Advance to meeting
    r_tr2 = client.post(
        f"/api/v1/interactions/{item['id']}/transitions",
        json={"transition_code": "needs_clarification_to_meeting", "expected_revision": r_tr1.json()["revision"]},
        headers=headers("manager-a", str(uuid4())),
    )
    assert r_tr2.status_code == 200
    cur_rev = r_tr2.json()["revision"]

    # In v1, meeting allowed transitions: meeting_to_document_exchange, meeting_to_cancelled
    detail_v1 = client.get(f"/api/v1/interactions/{item['id']}", headers=headers("manager-a")).json()
    trans_v1_codes = {t["code"] for t in detail_v1["allowed_transitions"]}
    assert "meeting_to_document_signing" not in trans_v1_codes

    # Migrate all v1 to v2
    client.post(
        "/api/v1/workflow/migrate/commit",
        json={"from_version": 1, "to_version": 2, "status_mapping": full_identity_mapping(1, 2)},
        headers=headers("supervisor", str(uuid4())),
    )

    # Now in v2, card is in meeting state
    detail_v2 = client.get(f"/api/v1/interactions/{item['id']}", headers=headers("manager-a")).json()
    assert detail_v2["workflow_version"] == 2
    trans_v2_codes = {t["code"] for t in detail_v2["allowed_transitions"]}
    assert "meeting_to_document_signing" in trans_v2_codes

    # Execute fast-track transition meeting -> document_signing
    r_fast = client.post(
        f"/api/v1/interactions/{item['id']}/transitions",
        json={"transition_code": "meeting_to_document_signing", "expected_revision": detail_v2["revision"]},
        headers=headers("manager-a", str(uuid4())),
    )
    assert r_fast.status_code == 200
    res_fast = r_fast.json()
    assert res_fast["state"] == "document_signing"


def test_workflow_migrate_to_terminal_updates_closed_at(client):
    item = create_test_interaction(client, "manager-a", "Карточка для терминальной миграции")
    mapping = full_identity_mapping(1, 2)
    # Map contact_search to completed
    mapping["contact_search"] = "completed"

    r_commit = client.post(
        "/api/v1/workflow/migrate/commit",
        json={"from_version": 1, "to_version": 2, "status_mapping": mapping},
        headers=headers("administrator", str(uuid4())),
    )
    assert r_commit.status_code == 200

    card = client.get(f"/api/v1/interactions/{item['id']}", headers=headers("manager-a")).json()
    assert card["state"] == "completed"
    assert card["closed_at"] is not None
