"""Automated tests for requirement R4: PATCH /api/v1/interactions/{id}, CAS, catalogs, and deadlock D02."""
from uuid import uuid4

import pytest


def headers(user="manager-a", key=None):
    result = {"X-Demo-User": user}
    if key:
        result["Idempotency-Key"] = key
    return result


def create_interaction(client, user="manager-a", **changes):
    body = {
        "title": "Проверка взаимодействия",
        "organization_id": "org-1",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "Тестовый цикл 2026",
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


def test_patch_resolves_deadlock_d02(client):
    """Prove elimination of deadlock D02 (AC07):

    1. Card created without program and product transitions up to document_signing.
    2. Transition to materials_transfer fails with 422 VALIDATION_ERROR.
    3. PATCH assigns compatible program and product.
    4. Transition to materials_transfer now succeeds (200 OK, state=materials_transfer).
    """
    card = create_interaction(client, program_id=None, product_id=None)
    assert card["program_id"] is None and card["product_id"] is None
    assert card["state"] == "contact_search"

    transitions_to_signing = [
        "contact_search_to_needs_clarification",
        "needs_clarification_to_meeting",
        "meeting_to_document_exchange",
        "document_exchange_to_document_signing",
    ]
    for transition_code in transitions_to_signing:
        res = client.post(
            f"/api/v1/interactions/{card['id']}/transitions",
            json={"transition_code": transition_code, "expected_revision": card["revision"]},
            headers=headers(key=str(uuid4())),
        )
        assert res.status_code == 200, res.text
        card = res.json()

    assert card["state"] == "document_signing"

    blocked = client.post(
        f"/api/v1/interactions/{card['id']}/transitions",
        json={
            "transition_code": "document_signing_to_materials_transfer",
            "expected_revision": card["revision"],
        },
        headers=headers(key=str(uuid4())),
    )
    assert blocked.status_code == 422, blocked.text
    err = blocked.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert "Перед этим этапом укажите ИТ-программу и ИТ-продукт" in err["message"]

    current = detail(client, card["id"])
    assert current["state"] == "document_signing"
    assert current["revision"] == card["revision"]

    patch_res = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={
            "expected_revision": card["revision"],
            "program_id": "program-devops",
            "product_id": "product-cloud",
        },
        headers=headers(key=str(uuid4())),
    )
    assert patch_res.status_code == 200, patch_res.text
    patched = patch_res.json()
    assert patched["revision"] == card["revision"] + 1
    assert patched["program_id"] == "program-devops"
    assert patched["program_name"] == "DevOps и облачные технологии"
    assert patched["product_id"] == "product-cloud"
    assert patched["product_name"] == "Облачная платформа"
    assert patched["direction_name"] == "Цифровые технологии"

    unblocked = client.post(
        f"/api/v1/interactions/{card['id']}/transitions",
        json={
            "transition_code": "document_signing_to_materials_transfer",
            "expected_revision": patched["revision"],
        },
        headers=headers(key=str(uuid4())),
    )
    assert unblocked.status_code == 200, unblocked.text
    success = unblocked.json()
    assert success["state"] == "materials_transfer"
    assert success["revision"] == patched["revision"] + 1

    final_detail = detail(client, card["id"])
    assert final_detail["state"] == "materials_transfer"
    assert final_detail["program_id"] == "program-devops"
    assert final_detail["product_id"] == "product-cloud"


def test_patch_cas_conflict(client):
    """409 REVISION_CONFLICT on stale expected_revision (AC01)."""
    card = create_interaction(client)
    initial_rev = card["revision"]

    conflict_future = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={
            "expected_revision": initial_rev + 99,
            "title": "Изменение с забеганием ревизии вперед",
        },
        headers=headers(key=str(uuid4())),
    )
    assert conflict_future.status_code == 409, conflict_future.text
    assert conflict_future.json()["error"]["code"] == "REVISION_CONFLICT"

    current = detail(client, card["id"])
    assert current["revision"] == initial_rev
    assert current["title"] == card["title"]

    success_patch = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={
            "expected_revision": initial_rev,
            "title": "Успешно обновленный заголовок",
        },
        headers=headers(key=str(uuid4())),
    )
    assert success_patch.status_code == 200, success_patch.text
    updated = success_patch.json()
    assert updated["revision"] == initial_rev + 1
    assert updated["title"] == "Успешно обновленный заголовок"

    stale_patch = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={
            "expected_revision": initial_rev,
            "title": "Устаревшая попытка перезаписи",
        },
        headers=headers(key=str(uuid4())),
    )
    assert stale_patch.status_code == 409, stale_patch.text
    assert stale_patch.json()["error"]["code"] == "REVISION_CONFLICT"

    assert detail(client, card["id"])["title"] == "Успешно обновленный заголовок"


def test_patch_invalid_subject_combination(client):
    """422 VALIDATION_ERROR on incompatible program/product combination."""
    card = create_interaction(client)

    incompatible = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={
            "expected_revision": card["revision"],
            "program_id": "program-devops",
            "product_id": "product-test",
        },
        headers=headers(key=str(uuid4())),
    )
    assert incompatible.status_code == 422, incompatible.text
    assert incompatible.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "не связан с выбранной программой" in incompatible.json()["error"]["message"].lower()

    nonexistent_prog = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={
            "expected_revision": card["revision"],
            "program_id": "program-unknown-xyz",
            "product_id": "product-cloud",
        },
        headers=headers(key=str(uuid4())),
    )
    assert nonexistent_prog.status_code == 422, nonexistent_prog.text
    assert nonexistent_prog.json()["error"]["code"] == "VALIDATION_ERROR"

    nonexistent_prod = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={
            "expected_revision": card["revision"],
            "program_id": "program-devops",
            "product_id": "product-unknown-xyz",
        },
        headers=headers(key=str(uuid4())),
    )
    assert nonexistent_prod.status_code == 422, nonexistent_prod.text
    assert nonexistent_prod.json()["error"]["code"] == "VALIDATION_ERROR"

    unchanged = detail(client, card["id"])
    assert unchanged["revision"] == card["revision"]
    assert unchanged["program_id"] == card["program_id"]
    assert unchanged["product_id"] == card["product_id"]


def test_patch_disallows_clearing_subject_in_late_states(client):
    """422 VALIDATION_ERROR on resetting subject to None in materials_transfer or later."""
    card = create_interaction(client, program_id="program-devops", product_id="product-cloud")
    transitions_to_materials = [
        "contact_search_to_needs_clarification",
        "needs_clarification_to_meeting",
        "meeting_to_document_exchange",
        "document_exchange_to_document_signing",
        "document_signing_to_materials_transfer",
    ]
    for transition_code in transitions_to_materials:
        res = client.post(
            f"/api/v1/interactions/{card['id']}/transitions",
            json={"transition_code": transition_code, "expected_revision": card["revision"]},
            headers=headers(key=str(uuid4())),
        )
        assert res.status_code == 200, res.text
        card = res.json()

    assert card["state"] == "materials_transfer"

    clear_prog = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={"expected_revision": card["revision"], "program_id": None},
        headers=headers(key=str(uuid4())),
    )
    assert clear_prog.status_code == 422, clear_prog.text
    assert clear_prog.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "нельзя сбросить" in clear_prog.json()["error"]["message"]

    clear_prod = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={"expected_revision": card["revision"], "product_id": None},
        headers=headers(key=str(uuid4())),
    )
    assert clear_prod.status_code == 422, clear_prod.text
    assert clear_prod.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "нельзя сбросить" in clear_prod.json()["error"]["message"]

    clear_both = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={"expected_revision": card["revision"], "program_id": None, "product_id": None},
        headers=headers(key=str(uuid4())),
    )
    assert clear_both.status_code == 422, clear_both.text
    assert clear_both.json()["error"]["code"] == "VALIDATION_ERROR"

    persisted = detail(client, card["id"])
    assert persisted["program_id"] == "program-devops"
    assert persisted["product_id"] == "product-cloud"
    assert persisted["revision"] == card["revision"]


def test_patch_idempotency_and_event_sequence(client):
    """Replay returns identical response, single attributes_corrected event;

    different body with same key gives 409 IDEMPOTENCY_CONFLICT.
    """
    card = create_interaction(client)
    key = str(uuid4())
    body = {
        "expected_revision": card["revision"],
        "title": "Идемпотентный заголовок",
        "cycle_label": "2027/2028",
    }

    first = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json=body,
        headers=headers(key=key),
    )
    assert first.status_code == 200, first.text
    first_json = first.json()
    assert first_json["revision"] == card["revision"] + 1
    assert first_json["title"] == "Идемпотентный заголовок"
    assert first_json["cycle_label"] == "2027/2028"

    replay = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json=body,
        headers=headers(key=key),
    )
    assert replay.status_code == 200, replay.text
    assert replay.json() == first_json

    card_detail = detail(client, card["id"])
    corrected_events = [e for e in card_detail["events"] if e["type"] == "attributes_corrected"]
    assert len(corrected_events) == 1
    ev = corrected_events[0]
    assert ev["actor_name"] == "Анна Смирнова"
    assert "changes" in ev
    assert ev["changes"]["title"]["old"] == card["title"]
    assert ev["changes"]["title"]["new"] == "Идемпотентный заголовок"
    assert ev["changes"]["cycle_label"]["old"] == card["cycle_label"]
    assert ev["changes"]["cycle_label"]["new"] == "2027/2028"

    conflict_body = {
        "expected_revision": card["revision"],
        "title": "Совершенно другой заголовок",
        "cycle_label": "2030",
    }
    conflict = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json=conflict_body,
        headers=headers(key=key),
    )
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    # Missing idempotency key header rejects with 422
    missing_key = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={"expected_revision": first_json["revision"], "title": "Без ключа"},
        headers=headers(),
    )
    assert missing_key.status_code in (400, 422), missing_key.text


def test_patch_scope_isolation_manager(client):
    """Manager B gets strict 404 NOT_FOUND on Manager A's card (152-ФЗ / AC06)."""
    card_a = create_interaction(client, user="manager-a")

    attempt_b = client.patch(
        f"/api/v1/interactions/{card_a['id']}",
        json={
            "expected_revision": card_a["revision"],
            "title": "Несанкционированная модификация менеджером Б",
        },
        headers=headers("manager-b", str(uuid4())),
    )
    assert attempt_b.status_code == 404, attempt_b.text
    assert attempt_b.json()["error"]["code"] == "NOT_FOUND"

    check_a = detail(client, card_a["id"], user="manager-a")
    assert check_a["title"] == card_a["title"]
    assert check_a["revision"] == card_a["revision"]

    attempt_admin = client.patch(
        f"/api/v1/interactions/{card_a['id']}",
        json={
            "expected_revision": card_a["revision"],
            "title": "Попытка изменения администратором без бизнес-доступа",
        },
        headers=headers("administrator", str(uuid4())),
    )
    assert attempt_admin.status_code in (403, 404), attempt_admin.text


def test_patch_scope_isolation_after_reassignment(client):
    """Manager A gets strict 404 NOT_FOUND on card reassigned by supervisor to Manager B."""
    card = create_interaction(client, user="manager-a")
    transfer_key = str(uuid4())

    transfer = client.post(
        f"/api/v1/interactions/{card['id']}/assignments",
        json={
            "owner_id": "manager-b",
            "expected_revision": card["revision"],
            "reason": "Передача ведения проекта новому менеджеру",
        },
        headers=headers("supervisor", transfer_key),
    )
    assert transfer.status_code == 200, transfer.text
    reassigned = transfer.json()
    new_rev = reassigned["revision"]
    assert reassigned["owner_id"] == "manager-b"

    assert client.get(f"/api/v1/interactions/{card['id']}", headers=headers("manager-a")).status_code == 404

    patch_former = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={
            "expected_revision": new_rev,
            "title": "Попытка бывшего владельца изменить карточку",
        },
        headers=headers("manager-a", str(uuid4())),
    )
    assert patch_former.status_code == 404, patch_former.text
    assert patch_former.json()["error"]["code"] == "NOT_FOUND"

    patch_new_owner = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={
            "expected_revision": new_rev,
            "title": "Обновление от нового ответственного",
        },
        headers=headers("manager-b", str(uuid4())),
    )
    assert patch_new_owner.status_code == 200, patch_new_owner.text
    updated_b = patch_new_owner.json()
    assert updated_b["title"] == "Обновление от нового ответственного"
    assert updated_b["owner_id"] == "manager-b"
    assert updated_b["revision"] == new_rev + 1


def test_patch_links_contact_contract_license(client):
    """Successfully attaches contact, contract, license; verifies fields in detail();

    rejects linking foreign organization entities or mismatched license product with 422.
    """
    card = create_interaction(
        client,
        user="manager-a",
        organization_id="org-1",
        program_id="program-devops",
        product_id="product-cloud",
    )
    assert card["contact_id"] is None
    assert card["contract_id"] is None
    assert card["license_id"] is None

    patch_res = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={
            "expected_revision": card["revision"],
            "contact_id": "contact-1",
            "contract_id": "contract-1",
            "license_id": "license-1",
        },
        headers=headers(key=str(uuid4())),
    )
    assert patch_res.status_code == 200, patch_res.text
    patched = patch_res.json()
    assert patched["contact_id"] == "contact-1"
    assert patched["contact_name"] == "Иван Петров"
    assert patched["contract_id"] == "contract-1"
    assert patched["contract_number"] == "ДОГ-2026/01"
    assert patched["license_id"] == "license-1"
    assert patched["license_status"] == "transferred"

    card_detail = detail(client, card["id"])
    assert card_detail["contact_id"] == "contact-1"
    assert card_detail["contact_name"] == "Иван Петров"
    assert card_detail["contract_id"] == "contract-1"
    assert card_detail["contract_number"] == "ДОГ-2026/01"
    assert card_detail["license_id"] == "license-1"
    assert card_detail["license_status"] == "transferred"

    foreign_contact = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={"expected_revision": patched["revision"], "contact_id": "contact-3"},
        headers=headers(key=str(uuid4())),
    )
    assert foreign_contact.status_code == 422, foreign_contact.text
    assert foreign_contact.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "Контакт не принадлежит организации" in foreign_contact.json()["error"]["message"]

    foreign_contract = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={"expected_revision": patched["revision"], "contract_id": "contract-2"},
        headers=headers(key=str(uuid4())),
    )
    assert foreign_contract.status_code == 422, foreign_contract.text
    assert foreign_contract.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "Договор не принадлежит организации" in foreign_contract.json()["error"]["message"]

    foreign_license = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={"expected_revision": patched["revision"], "license_id": "license-3"},
        headers=headers(key=str(uuid4())),
    )
    assert foreign_license.status_code == 422, foreign_license.text
    assert foreign_license.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "Лицензия не принадлежит организации" in foreign_license.json()["error"]["message"]

    # license-2 belongs to org-1, but its product is product-test while card is product-cloud
    mismatched_license = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={"expected_revision": patched["revision"], "license_id": "license-2"},
        headers=headers(key=str(uuid4())),
    )
    assert mismatched_license.status_code == 422, mismatched_license.text
    assert mismatched_license.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "Лицензия не соответствует выбранному ИТ-продукту" in mismatched_license.json()["error"]["message"]


def test_catalogs_returns_contracts_licenses_contacts(client):
    """Verifies /api/v1/catalogs returns non-empty contacts, contracts, licenses for visible orgs."""
    res_a = client.get("/api/v1/catalogs", headers=headers("manager-a"))
    assert res_a.status_code == 200, res_a.text
    data_a = res_a.json()

    assert "contacts" in data_a and len(data_a["contacts"]) > 0
    assert "contracts" in data_a and len(data_a["contracts"]) > 0
    assert "licenses" in data_a and len(data_a["licenses"]) > 0

    assert all(c["organization_id"] == "org-1" for c in data_a["contacts"])
    assert all(c["organization_id"] == "org-1" for c in data_a["contracts"])
    assert all(l["organization_id"] == "org-1" for l in data_a["licenses"])

    contact_ids_a = {c["id"] for c in data_a["contacts"]}
    assert "contact-1" in contact_ids_a and "contact-2" in contact_ids_a
    assert "contact-3" not in contact_ids_a

    c_sample = data_a["contacts"][0]
    for field in ("id", "organization_id", "full_name", "position", "email", "phone", "active"):
        assert field in c_sample

    ct_sample = data_a["contracts"][0]
    for field in ("id", "organization_id", "number", "signed_on", "status", "created_at"):
        assert field in ct_sample

    lic_sample = data_a["licenses"][0]
    for field in (
        "id",
        "organization_id",
        "product_id",
        "contract_id",
        "signed_on",
        "term_years",
        "transfer_status",
        "created_at",
    ):
        assert field in lic_sample

    res_sup = client.get("/api/v1/catalogs", headers=headers("supervisor"))
    assert res_sup.status_code == 200, res_sup.text
    data_sup = res_sup.json()

    sup_contacts = {c["id"] for c in data_sup["contacts"]}
    sup_contracts = {c["id"] for c in data_sup["contracts"]}
    sup_licenses = {l["id"] for l in data_sup["licenses"]}

    assert {"contact-1", "contact-2", "contact-3", "contact-4"} <= sup_contacts
    assert {"contract-1", "contract-2", "contract-3"} <= sup_contracts
    assert {"license-1", "license-2", "license-3", "license-4"} <= sup_licenses


def test_patch_disallows_modifying_closed_interaction(client):
    """422 VALIDATION_ERROR when attempting to PATCH a closed (terminal) interaction."""
    card = create_interaction(client)
    current = detail(client, card["id"])
    cancel_transition = next(t for t in current["allowed_transitions"] if t["to"] == "cancelled")

    cancel_res = client.post(
        f"/api/v1/interactions/{card['id']}/transitions",
        json={
            "transition_code": cancel_transition["code"],
            "expected_revision": card["revision"],
            "comment": "Отмена карточки для теста закрытого состояния",
        },
        headers=headers(key=str(uuid4())),
    )
    assert cancel_res.status_code == 200, cancel_res.text
    closed_card = cancel_res.json()
    assert closed_card["state"] == "cancelled"
    assert closed_card["closed_at"] is not None

    patch_closed = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={
            "expected_revision": closed_card["revision"],
            "title": "Попытка модификации закрытой карточки",
        },
        headers=headers(key=str(uuid4())),
    )
    assert patch_closed.status_code == 422, patch_closed.text
    assert patch_closed.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "Завершённое взаимодействие не подлежит изменению" in patch_closed.json()["error"]["message"]
