"""SWE-26: Test suite for Deliveries API and Software Transfer Subsystem.

Covers:
- GET /api/v1/interactions/{interaction_id}/deliveries
- POST /api/v1/interactions/{interaction_id}/deliveries
- 152-FZ / FSTEC #117 row-level scope isolation (strict 404 Not Found)
- Idempotency-Key and replay protection
- InteractionEvent recording (delivery_recorded) and timeline inclusion
"""
from uuid import uuid4
import pytest


def auth_headers(user="manager-a", key=None):
    res = {"X-Demo-User": user}
    if key:
        res["Idempotency-Key"] = key
    return res


def test_get_deliveries_empty_and_created(client):
    # 1. Create test interaction by manager-a
    create_payload = {
        "title": "Тестовое внедрение ПО для кафедры",
        "organization_id": "org-1",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "Цикл 2026-1",
        "owner_id": "manager-a",
    }
    resp = client.post(
        "/api/v1/interactions",
        json=create_payload,
        headers=auth_headers("manager-a", str(uuid4())),
    )
    assert resp.status_code == 201, resp.text
    card = resp.json()
    card_id = card["id"]

    # 2. Initial deliveries list is empty
    resp = client.get(
        f"/api/v1/interactions/{card_id}/deliveries",
        headers=auth_headers("manager-a"),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == []

    # 3. Register delivery of software license
    delivery_payload = {
        "title": "Дистрибутив РТК-Платформа и лицензионные ключи",
        "item_kind": "license",
        "material_version": "v2.5.0",
        "channel": "email",
        "comment": "Лицензионный пакет направлен координатору вуза",
    }
    idem_key = str(uuid4())
    resp = client.post(
        f"/api/v1/interactions/{card_id}/deliveries",
        json=delivery_payload,
        headers=auth_headers("manager-a", idem_key),
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["id"]
    assert created["interaction_id"] == card_id
    assert created["status"] == "confirmed"
    assert created["channel"] == "email"
    assert created["comment"] == "Лицензионный пакет направлен координатору вуза"
    assert len(created["items"]) == 1
    assert created["items"][0]["title"] == "Дистрибутив РТК-Платформа и лицензионные ключи"
    assert created["items"][0]["material_version"] == "v2.5.0"
    assert created["items"][0]["item_kind"] == "license"

    # 4. Idempotency test: repeating with same key returns identical response
    replay_resp = client.post(
        f"/api/v1/interactions/{card_id}/deliveries",
        json=delivery_payload,
        headers=auth_headers("manager-a", idem_key),
    )
    assert replay_resp.status_code == 201
    assert replay_resp.json() == created

    # 5. GET deliveries now returns the created delivery
    list_resp = client.get(
        f"/api/v1/interactions/{card_id}/deliveries",
        headers=auth_headers("manager-a"),
    )
    assert list_resp.status_code == 200
    deliveries = list_resp.json()
    assert len(deliveries) == 1
    assert deliveries[0]["id"] == created["id"]

    # 6. Interaction detail contains deliveries and timeline event
    detail_resp = client.get(
        f"/api/v1/interactions/{card_id}",
        headers=auth_headers("manager-a"),
    )
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert "deliveries" in detail_data
    assert len(detail_data["deliveries"]) == 1
    assert detail_data["revision"] == 2

    # Check timeline events for delivery_recorded
    event_types = [e["type"] for e in detail_data["events"]]
    assert "delivery_recorded" in event_types
    deliv_event = next(e for e in detail_data["events"] if e["type"] == "delivery_recorded")
    assert deliv_event["actor_name"]
    assert deliv_event["delivery_id"] == created["id"]
    assert deliv_event["title"] == "Дистрибутив РТК-Платформа и лицензионные ключи"


def test_deliveries_security_isolation_152_fz(client):
    # Create card for manager-a
    resp = client.post(
        "/api/v1/interactions",
        json={
            "title": "Конфиденциальное взаимодействие 152-ФЗ",
            "organization_id": "org-1",
            "program_id": "program-devops",
            "product_id": "product-cloud",
            "cycle_label": "2026",
            "owner_id": "manager-a",
        },
        headers=auth_headers("manager-a", str(uuid4())),
    )
    assert resp.status_code == 201
    card_id = resp.json()["id"]

    # Manager B (different owner, not granted) must get strict 404 Not Found
    get_resp = client.get(
        f"/api/v1/interactions/{card_id}/deliveries",
        headers=auth_headers("manager-b"),
    )
    assert get_resp.status_code == 404
    assert get_resp.json()["error"]["code"] == "NOT_FOUND"

    # Manager B cannot register delivery on foreign card (strict 404)
    post_resp = client.post(
        f"/api/v1/interactions/{card_id}/deliveries",
        json={"title": "Несанкционированная поставка", "channel": "email"},
        headers=auth_headers("manager-b", str(uuid4())),
    )
    assert post_resp.status_code == 404
    assert post_resp.json()["error"]["code"] == "NOT_FOUND"

    # Non-existent card returns 404
    fake_resp = client.get(
        "/api/v1/interactions/non-existent-interaction-id/deliveries",
        headers=auth_headers("manager-a"),
    )
    assert fake_resp.status_code == 404


def test_delivery_validation_rules(client):
    # Create card
    resp = client.post(
        "/api/v1/interactions",
        json={
            "title": "Карточка для проверки валидации",
            "organization_id": "org-1",
            "program_id": "program-devops",
            "product_id": "product-cloud",
            "cycle_label": "2026",
            "owner_id": "manager-a",
        },
        headers=auth_headers("manager-a", str(uuid4())),
    )
    card = resp.json()
    card_id = card["id"]

    # Missing title must fail validation (422)
    fail_resp = client.post(
        f"/api/v1/interactions/{card_id}/deliveries",
        json={"channel": "email"},
        headers=auth_headers("manager-a", str(uuid4())),
    )
    assert fail_resp.status_code == 422

    # Foreign license_id raises 422 VALIDATION_ERROR
    lic_resp = client.post(
        f"/api/v1/interactions/{card_id}/deliveries",
        json={"title": "ПО", "channel": "email", "license_id": "license-3"},
        headers=auth_headers("manager-a", str(uuid4())),
    )
    assert lic_resp.status_code == 422
    assert lic_resp.json()["error"]["code"] == "VALIDATION_ERROR"

    # Foreign recipient_contact_id raises 422 VALIDATION_ERROR
    cnt_resp = client.post(
        f"/api/v1/interactions/{card_id}/deliveries",
        json={"title": "ПО", "channel": "email", "recipient_contact_id": "contact-3"},
        headers=auth_headers("manager-a", str(uuid4())),
    )
    assert cnt_resp.status_code == 422
    assert cnt_resp.json()["error"]["code"] == "VALIDATION_ERROR"

    # Valid expected_revision succeeds and increments revision
    valid_cas_resp = client.post(
        f"/api/v1/interactions/{card_id}/deliveries",
        json={"title": "ПО с CAS", "channel": "email", "expected_revision": card["revision"]},
        headers=auth_headers("manager-a", str(uuid4())),
    )
    assert valid_cas_resp.status_code == 201

    # Stale expected_revision raises 409 CONFLICT
    stale_resp = client.post(
        f"/api/v1/interactions/{card_id}/deliveries",
        json={"title": "ПО", "channel": "email", "expected_revision": card["revision"]},
        headers=auth_headers("manager-a", str(uuid4())),
    )
    assert stale_resp.status_code == 409
    assert stale_resp.json()["error"]["code"] in ("CONFLICT", "REVISION_CONFLICT")

    # Cancel interaction to close it (revision was bumped by valid_cas_resp)
    cancel_resp = client.post(
        f"/api/v1/interactions/{card_id}/transitions",
        json={
            "transition_code": "contact_search_to_cancelled",
            "expected_revision": card["revision"] + 1,
            "comment": "Отменено для проверки закрытого цикла",
        },
        headers=auth_headers("manager-a", str(uuid4())),
    )
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["closed_at"] is not None

    # Attempting delivery on closed interaction raises 422 VALIDATION_ERROR
    closed_resp = client.post(
        f"/api/v1/interactions/{card_id}/deliveries",
        json={"title": "ПО", "channel": "email"},
        headers=auth_headers("manager-a", str(uuid4())),
    )
    assert closed_resp.status_code == 422
    assert closed_resp.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "Нельзя регистрировать поставку для закрытого взаимодействия." in closed_resp.json()["error"]["message"]
