"""Integration checks of the real API and persistence, independent of UI state."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.config import Settings
from app.main import create_app


def headers(user="manager-a", key=None):
    result = {"X-Demo-User": user}
    if key:
        result["Idempotency-Key"] = key
    return result


def create_interaction(client, user="manager-a", **changes):
    body = {
        "title": "Проверка полного рабочего сценария",
        "organization_id": "org-1",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "Тестовый цикл",
        "owner_id": user,
    }
    body.update(changes)
    response = client.post("/api/v1/interactions", json=body, headers=headers(user, str(uuid4())))
    assert response.status_code == 201, response.text
    return response.json()


def detail(client, interaction_id, user="manager-a"):
    response = client.get(f"/api/v1/interactions/{interaction_id}", headers=headers(user))
    assert response.status_code == 200, response.text
    return response.json()


def report(client, as_of, user="supervisor", **changes):
    body = {"as_of": as_of, "knowledge_cutoff": datetime.now(timezone.utc).isoformat()}
    body.update(changes)
    response = client.post("/api/v1/reports/snapshot", json=body, headers=headers(user))
    assert response.status_code == 200, response.text
    return response.json()


def test_auth_requires_explicit_identity(client):
    assert client.get("/api/v1/config").json()["auth_mode"] == "demo"
    assert client.get("/api/v1/me").status_code == 401
    assert client.get("/api/v1/me", headers=headers("nonexistent")).status_code == 401
    assert client.get("/api/v1/me", headers=headers()).json()["id"] == "manager-a"


def test_demo_and_sqlite_cannot_be_accidentally_enabled_in_production():
    with pytest.raises(RuntimeError):
        create_app(Settings(app_env="production", auth_mode="demo"))
    with pytest.raises(RuntimeError):
        create_app(Settings(app_env="production", auth_mode="oidc", database_url="sqlite:///:memory:"))


def test_health_and_openapi_are_real(client):
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200
    schema = client.get("/openapi.json").json()
    assert "/api/v1/interactions/{interaction_id}/transitions" in schema["paths"]
    assert client.get("/docs").status_code == 200


def test_manager_scope_applies_to_list_direct_detail_and_dashboard(client):
    a = client.get("/api/v1/interactions", headers=headers()).json()
    b = client.get("/api/v1/interactions", headers=headers("manager-b")).json()
    a_ids = {row["id"] for row in a["items"]}
    b_ids = {row["id"] for row in b["items"]}
    assert a_ids and b_ids and a_ids.isdisjoint(b_ids)
    for item_id in b_ids:
        assert client.get(f"/api/v1/interactions/{item_id}", headers=headers()).status_code == 404
    dashboard = client.get("/api/v1/dashboard", headers=headers()).json()
    assert dashboard["total_interactions"] == a["total"]
    assert sum(row["count"] for row in dashboard["counts_by_state"]) == a["total"]


def test_technical_admin_has_no_implicit_business_scope(client):
    listing = client.get("/api/v1/interactions", headers=headers("administrator"))
    assert listing.status_code == 200
    assert listing.json()["total"] == 0
    snapshot = report(client, datetime.now(timezone.utc).isoformat(), user="administrator")
    assert snapshot["rows"] == []


def test_create_and_idempotent_replay_do_not_duplicate(client):
    key = str(uuid4())
    body = {"title": "Новый цикл", "organization_id": "org-1", "program_id": None,
            "product_id": None, "cycle_label": "2030", "owner_id": "manager-a"}
    first = client.post("/api/v1/interactions", json=body, headers=headers(key=key))
    second = client.post("/api/v1/interactions", json=body, headers=headers(key=key))
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["state"] == "contact_search"
    events = detail(client, first.json()["id"])["events"]
    assert len([event for event in events if event["type"] == "created"]) == 1
    changed = client.post("/api/v1/interactions", json={**body, "title": "Другой запрос"}, headers=headers(key=key))
    assert changed.status_code == 409, changed.text


def test_creation_requires_key_and_does_not_allow_manager_to_assign_another_user(client):
    body = {"title": "Запрещённая передача", "organization_id": "org-1", "program_id": None,
            "product_id": None, "cycle_label": "2030", "owner_id": "manager-b"}
    without_key = client.post("/api/v1/interactions", json=body, headers=headers())
    assert without_key.status_code in (400, 422), without_key.text
    forbidden = client.post("/api/v1/interactions", json=body, headers=headers(key=str(uuid4())))
    assert forbidden.status_code == 403, forbidden.text


def test_transition_revision_and_idempotency_are_enforced(client):
    card = create_interaction(client)
    endpoint = f"/api/v1/interactions/{card['id']}/transitions"
    body = {"transition_code": "contact_search_to_needs_clarification", "expected_revision": card["revision"], "comment": "Потребность уточнена"}
    key = str(uuid4())
    first = client.post(endpoint, json=body, headers=headers(key=key))
    assert first.status_code == 200, first.text
    assert first.json()["state"] == "needs_clarification"
    assert first.json()["revision"] == card["revision"] + 1
    replay = client.post(endpoint, json=body, headers=headers(key=key))
    assert replay.status_code == 200 and replay.json() == first.json()
    stale = client.post(endpoint, json={**body, "transition_code": "needs_clarification_to_meeting"}, headers=headers(key=str(uuid4())))
    assert stale.status_code == 409, stale.text
    events = detail(client, card["id"])["events"]
    assert len([event for event in events if event["type"] == "state_changed"]) == 1


def test_forbidden_transition_cannot_skip_workflow(client):
    card = create_interaction(client)
    response = client.post(f"/api/v1/interactions/{card['id']}/transitions", json={
        "transition_code": "document_signing_to_materials_transfer", "expected_revision": card["revision"]
    }, headers=headers(key=str(uuid4())))
    assert response.status_code in (409, 422), response.text
    assert detail(client, card["id"])["state"] == "contact_search"


def test_missing_program_and_product_prevent_late_stage(client):
    card = create_interaction(client, program_id=None, product_id=None)
    for transition in ["contact_search_to_needs_clarification", "needs_clarification_to_meeting",
                       "meeting_to_document_exchange", "document_exchange_to_document_signing"]:
        response = client.post(f"/api/v1/interactions/{card['id']}/transitions", json={
            "transition_code": transition, "expected_revision": card["revision"]
        }, headers=headers(key=str(uuid4())))
        assert response.status_code == 200, response.text
        card = response.json()
    blocked = client.post(f"/api/v1/interactions/{card['id']}/transitions", json={
        "transition_code": "document_signing_to_materials_transfer", "expected_revision": card["revision"]
    }, headers=headers(key=str(uuid4())))
    assert blocked.status_code == 422, blocked.text
    assert detail(client, card["id"])["revision"] == card["revision"]


def test_cancel_requires_comment_and_terminal_has_no_transition(client):
    card = create_interaction(client)
    current = detail(client, card["id"])
    cancel = next(t for t in current["allowed_transitions"] if t["to"] == "cancelled")
    body = {"transition_code": cancel["code"], "expected_revision": card["revision"], "comment": "  "}
    endpoint = f"/api/v1/interactions/{card['id']}/transitions"
    blocked = client.post(endpoint, json=body, headers=headers(key=str(uuid4())))
    assert blocked.status_code == 422, blocked.text
    done = client.post(endpoint, json={**body, "comment": "Набор отменён"}, headers=headers(key=str(uuid4())))
    assert done.status_code == 200, done.text
    closed = detail(client, card["id"])
    assert closed["state"] == "cancelled" and closed["closed_at"]
    assert closed["allowed_transitions"] == []


def test_comment_is_persisted_and_stale_comment_does_not_overwrite(client):
    card = create_interaction(client)
    body = {"body": "Договорились о следующей встрече.", "expected_revision": card["revision"]}
    endpoint = f"/api/v1/interactions/{card['id']}/comments"
    key = str(uuid4())
    response = client.post(endpoint, json=body, headers=headers(key=key))
    assert response.status_code == 201, response.text
    assert client.post(endpoint, json=body, headers=headers(key=key)).status_code == 201
    stale = client.post(endpoint, json={**body, "body": "Не должен сохраниться"}, headers=headers(key=str(uuid4())))
    assert stale.status_code == 409, stale.text
    current = detail(client, card["id"])
    assert [c["body"] for c in current["comments"]] == [body["body"]]


def test_reassignment_restricts_old_owner_and_keeps_historical_owner(client):
    card = create_interaction(client)
    at_creation = card["created_at"]
    endpoint = f"/api/v1/interactions/{card['id']}/assignments"
    body = {"owner_id": "manager-b", "expected_revision": card["revision"], "reason": "Передача сопровождения"}
    denied = client.post(endpoint, json=body, headers=headers(key=str(uuid4())))
    assert denied.status_code == 403, denied.text
    reassigned = client.post(endpoint, json=body, headers=headers("supervisor", str(uuid4())))
    assert reassigned.status_code == 200, reassigned.text
    assert client.get(f"/api/v1/interactions/{card['id']}", headers=headers()).status_code == 404
    assert detail(client, card["id"], "manager-b")["owner_id"] == "manager-b"
    historical = report(client, at_creation, user="manager-b")
    row = next(row for row in historical["rows"] if row["interaction_id"] == card["id"])
    assert row["owner_id"] == "manager-a"
    former = report(client, at_creation, user="manager-a")
    assert card["id"] not in {r["interaction_id"] for r in former["rows"]}


def test_idempotent_transition_replay_checks_current_access(client):
    card = create_interaction(client)
    key = str(uuid4())
    body = {"transition_code": "contact_search_to_needs_clarification", "expected_revision": card["revision"]}
    endpoint = f"/api/v1/interactions/{card['id']}/transitions"
    response = client.post(endpoint, json=body, headers=headers(key=key))
    assert response.status_code == 200, response.text
    transfer = client.post(f"/api/v1/interactions/{card['id']}/assignments", json={
        "owner_id": "manager-b", "expected_revision": response.json()["revision"], "reason": "Передача"
    }, headers=headers("supervisor", str(uuid4())))
    assert transfer.status_code == 200, transfer.text
    replay = client.post(endpoint, json=body, headers=headers(key=key))
    assert replay.status_code == 404, replay.text


def test_snapshot_effective_and_received_boundaries(client):
    card = create_interaction(client)
    body = {"transition_code": "contact_search_to_needs_clarification", "expected_revision": card["revision"]}
    response = client.post(f"/api/v1/interactions/{card['id']}/transitions", json=body, headers=headers(key=str(uuid4())))
    assert response.status_code == 200, response.text
    event = next(e for e in detail(client, card["id"])["events"] if e["type"] == "state_changed")
    inclusive = report(client, event["effective_at"])
    row = next(r for r in inclusive["rows"] if r["interaction_id"] == card["id"])
    assert row["state"] == "needs_clarification"
    exclusive = report(client, event["effective_at"], as_of_inclusive=False)
    earlier = next(r for r in exclusive["rows"] if r["interaction_id"] == card["id"])
    assert earlier["state"] == "contact_search"
    before = (datetime.fromisoformat(card["created_at"].replace("Z", "+00:00")) - timedelta(seconds=1)).isoformat()
    unknown = report(client, event["effective_at"], knowledge_cutoff=before)
    assert card["id"] not in {r["interaction_id"] for r in unknown["rows"]}


def test_json_export_is_scoped_and_matches_report(client):
    params = {"as_of": datetime.now(timezone.utc).isoformat(), "knowledge_cutoff": datetime.now(timezone.utc).isoformat()}
    preview = client.post("/api/v1/reports/snapshot", json=params, headers=headers())
    export = client.post("/api/v1/reports/snapshot/export", json=params, headers=headers())
    assert preview.status_code == export.status_code == 200
    assert "attachment" in export.headers.get("content-disposition", "")
    assert export.json()["rows"] == preview.json()["rows"]
    assert export.json()["totals"] == preview.json()["totals"]
    listing = client.get("/api/v1/interactions", headers=headers()).json()
    assert {r["interaction_id"] for r in export.json()["rows"]} <= {r["id"] for r in listing["items"]}


def test_filter_intersection_pagination_and_input_validation(client):
    card = create_interaction(client, title="Уникальный поисковый маркер 4819")
    result = client.get("/api/v1/interactions", params={"q": "4819", "owner_id": "manager-a", "state": "contact_search"}, headers=headers())
    assert result.status_code == 200, result.text
    assert [r["id"] for r in result.json()["items"]] == [card["id"]]
    first = client.get("/api/v1/interactions?page=1&page_size=1", headers=headers()).json()
    second = client.get("/api/v1/interactions?page=2&page_size=1", headers=headers()).json()
    assert first["total"] == second["total"] and first["items"][0]["id"] != second["items"][0]["id"]
    assert client.get("/api/v1/interactions?page=0", headers=headers()).status_code == 422
    assert client.get("/api/v1/interactions?page_size=99999", headers=headers()).status_code == 422

