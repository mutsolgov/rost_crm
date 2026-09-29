"""Empirical Adversarial Test Suite for SWE-26 (Deliveries API & Subsystems).

Author: teamwork_preview_challenger_swe26_1
Archetype: Empirical Challenger
Purpose: Stress-test assumptions, 152-FZ Zero-Oracle protection, multi-tenant isolation,
         CAS revision concurrency, and Idempotency-Key replay protection.
"""
from uuid import uuid4
import pytest
from sqlalchemy import select
from app.models import Delivery, DeliveryItem, Interaction, InteractionEvent, User, OrganizationAccess


def auth_headers(user="manager-a", key=None):
    res = {"X-Demo-User": user}
    if key is not None:
        res["Idempotency-Key"] = key
    return res


def create_test_interaction(client, user="manager-a", org_id="org-1"):
    resp = client.post(
        "/api/v1/interactions",
        json={
            "title": f"Испытательное взаимодействие {uuid4().hex[:8]}",
            "organization_id": org_id,
            "program_id": "program-devops",
            "product_id": "product-cloud",
            "cycle_label": "2026-T",
            "owner_id": user,
        },
        headers=auth_headers(user, str(uuid4())),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestSWE26AdversarialZeroOracle:
    """152-FZ Zero-Oracle Stress Tests."""

    def test_manager_b_cannot_probe_manager_a_deliveries(self, client):
        card = create_test_interaction(client, user="manager-a", org_id="org-1")
        card_id = card["id"]

        # Manager B attempts GET on Manager A's deliveries
        get_resp = client.get(
            f"/api/v1/interactions/{card_id}/deliveries",
            headers=auth_headers("manager-b"),
        )
        assert get_resp.status_code == 404, f"Expected 404, got {get_resp.status_code}"
        assert get_resp.json()["error"]["code"] == "NOT_FOUND"

        # Manager B attempts POST on Manager A's deliveries
        post_resp = client.post(
            f"/api/v1/interactions/{card_id}/deliveries",
            json={"title": "Злонамеренная поставка", "channel": "email"},
            headers=auth_headers("manager-b", str(uuid4())),
        )
        assert post_resp.status_code == 404, f"Expected 404, got {post_resp.status_code}"
        assert post_resp.json()["error"]["code"] == "NOT_FOUND"

        # Compare with non-existent interaction ID
        bogus_id = "non-existent-interaction-" + uuid4().hex
        bogus_get = client.get(
            f"/api/v1/interactions/{bogus_id}/deliveries",
            headers=auth_headers("manager-b"),
        )
        assert bogus_get.status_code == 404
        assert bogus_get.json()["error"]["code"] == "NOT_FOUND"

        bogus_post = client.post(
            f"/api/v1/interactions/{bogus_id}/deliveries",
            json={"title": "Поставка", "channel": "email"},
            headers=auth_headers("manager-b", str(uuid4())),
        )
        assert bogus_post.status_code == 404
        assert bogus_post.json()["error"]["code"] == "NOT_FOUND"

        # Both responses must return the same error code and message structure (Zero-Oracle)
        assert get_resp.json()["error"]["code"] == bogus_get.json()["error"]["code"] == "NOT_FOUND"
        assert get_resp.json()["error"]["message"] == bogus_get.json()["error"]["message"] == "Взаимодействие не найдено."
        assert post_resp.json()["error"]["code"] == bogus_post.json()["error"]["code"] == "NOT_FOUND"
        assert post_resp.json()["error"]["message"] == bogus_post.json()["error"]["message"] == "Взаимодействие не найдено."

    def test_isolated_supervisor_cross_team_zero_oracle(self, client, app):
        card = create_test_interaction(client, user="manager-a", org_id="org-1")
        card_id = card["id"]

        # Create supervisor from another team (south) with no access to org-1
        with app.state.session_factory() as session:
            foreign_sup = User(
                id="supervisor-south",
                keycloak_subject="south-sup-uuid",
                name="Южный Руководитель",
                role="supervisor",
                team_id="south",
            )
            session.add(foreign_sup)
            session.commit()

        sup_get = client.get(
            f"/api/v1/interactions/{card_id}/deliveries",
            headers=auth_headers("supervisor-south"),
        )
        assert sup_get.status_code == 404
        assert sup_get.json()["error"]["code"] == "NOT_FOUND"


class TestSWE26MultiTenantIsolation:
    """Multi-tenant Foreign License and Contact Rejection."""

    def test_reject_cross_tenant_license(self, client, app):
        card = create_test_interaction(client, user="manager-a", org_id="org-1")
        card_id = card["id"]

        # license-3 belongs to org-2
        resp = client.post(
            f"/api/v1/interactions/{card_id}/deliveries",
            json={
                "title": "Поставка чужой лицензии",
                "license_id": "license-3",
                "channel": "email",
            },
            headers=auth_headers("manager-a", str(uuid4())),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
        assert "Лицензия не принадлежит организации взаимодействия." in resp.json()["error"]["message"]

        # Verify nothing persisted in database
        with app.state.session_factory() as session:
            count = session.query(Delivery).filter(Delivery.interaction_id == card_id).count()
            assert count == 0

    def test_reject_non_existent_license(self, client, app):
        card = create_test_interaction(client, user="manager-a", org_id="org-1")
        card_id = card["id"]

        resp = client.post(
            f"/api/v1/interactions/{card_id}/deliveries",
            json={
                "title": "Поставка несуществующей лицензии",
                "license_id": "bogus-license-999",
                "channel": "email",
            },
            headers=auth_headers("manager-a", str(uuid4())),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
        assert "Лицензия не принадлежит организации взаимодействия." in resp.json()["error"]["message"]

    def test_reject_cross_tenant_contact(self, client, app):
        card = create_test_interaction(client, user="manager-a", org_id="org-1")
        card_id = card["id"]

        # contact-3 belongs to org-2
        resp = client.post(
            f"/api/v1/interactions/{card_id}/deliveries",
            json={
                "title": "Поставка чужому контакту",
                "recipient_contact_id": "contact-3",
                "channel": "email",
            },
            headers=auth_headers("manager-a", str(uuid4())),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
        assert "Контакт не принадлежит организации взаимодействия." in resp.json()["error"]["message"]

        # Verify nothing persisted
        with app.state.session_factory() as session:
            count = session.query(Delivery).filter(Delivery.interaction_id == card_id).count()
            assert count == 0

    def test_reject_non_existent_contact(self, client):
        card = create_test_interaction(client, user="manager-a", org_id="org-1")
        card_id = card["id"]

        resp = client.post(
            f"/api/v1/interactions/{card_id}/deliveries",
            json={
                "title": "Поставка несуществующему контакту",
                "recipient_contact_id": "bogus-contact-999",
                "channel": "email",
            },
            headers=auth_headers("manager-a", str(uuid4())),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
        assert "Контакт не принадлежит организации взаимодействия." in resp.json()["error"]["message"]


class TestSWE26CASRevisionConcurrency:
    """CAS Revision Concurrency and Conflict Handling."""

    def test_cas_exact_match_success(self, client):
        card = create_test_interaction(client, user="manager-a", org_id="org-1")
        card_id = card["id"]
        initial_revision = card["revision"]

        resp = client.post(
            f"/api/v1/interactions/{card_id}/deliveries",
            json={
                "title": "Поставка ПО по точной ревизии",
                "expected_revision": initial_revision,
            },
            headers=auth_headers("manager-a", str(uuid4())),
        )
        assert resp.status_code == 201

        # Check that interaction revision is incremented
        detail = client.get(f"/api/v1/interactions/{card_id}", headers=auth_headers("manager-a")).json()
        assert detail["revision"] == initial_revision + 1

    def test_cas_stale_revision_conflict_409(self, client, app):
        card = create_test_interaction(client, user="manager-a", org_id="org-1")
        card_id = card["id"]
        initial_revision = card["revision"]

        # Bump revision via first delivery
        resp1 = client.post(
            f"/api/v1/interactions/{card_id}/deliveries",
            json={"title": "Первая поставка", "expected_revision": initial_revision},
            headers=auth_headers("manager-a", str(uuid4())),
        )
        assert resp1.status_code == 201

        # Second delivery with stale initial_revision must fail 409
        resp2 = client.post(
            f"/api/v1/interactions/{card_id}/deliveries",
            json={"title": "Вторая поставка с устаревшей ревизией", "expected_revision": initial_revision},
            headers=auth_headers("manager-a", str(uuid4())),
        )
        assert resp2.status_code == 409
        assert resp2.json()["error"]["code"] in ("CONFLICT", "REVISION_CONFLICT")

        # Database must only have 1 delivery
        with app.state.session_factory() as session:
            count = session.query(Delivery).filter(Delivery.interaction_id == card_id).count()
            assert count == 1

    def test_cas_future_revision_conflict_409(self, client):
        card = create_test_interaction(client, user="manager-a", org_id="org-1")
        card_id = card["id"]

        # Future revision (e.g. +10) must fail 409
        resp = client.post(
            f"/api/v1/interactions/{card_id}/deliveries",
            json={"title": "Поставка из будущего", "expected_revision": card["revision"] + 10},
            headers=auth_headers("manager-a", str(uuid4())),
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] in ("CONFLICT", "REVISION_CONFLICT")

    def test_delivery_on_closed_card_rejected(self, client):
        card = create_test_interaction(client, user="manager-a", org_id="org-1")
        card_id = card["id"]

        # Close/cancel interaction
        cancel_resp = client.post(
            f"/api/v1/interactions/{card_id}/transitions",
            json={
                "transition_code": "contact_search_to_cancelled",
                "expected_revision": card["revision"],
                "comment": "Отмена карточки",
            },
            headers=auth_headers("manager-a", str(uuid4())),
        )
        assert cancel_resp.status_code == 200

        # Attempt delivery on closed card
        resp = client.post(
            f"/api/v1/interactions/{card_id}/deliveries",
            json={"title": "Поставка после закрытия"},
            headers=auth_headers("manager-a", str(uuid4())),
        )
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"
        assert "Нельзя регистрировать поставку для закрытого взаимодействия." in resp.json()["error"]["message"]


class TestSWE26IdempotencyStress:
    """Idempotency Replay and Mutation Protection."""

    def test_idempotent_replay_returns_cached_result_without_duplication(self, client, app):
        card = create_test_interaction(client, user="manager-a", org_id="org-1")
        card_id = card["id"]
        key = f"idem-key-{uuid4()}"

        payload = {
            "title": "Идемпотентная выдача ПО",
            "item_kind": "license",
            "material_version": "v1.0.0",
            "channel": "email",
            "comment": "Первичная выдача",
        }

        # 1. First execution
        resp1 = client.post(
            f"/api/v1/interactions/{card_id}/deliveries",
            json=payload,
            headers=auth_headers("manager-a", key),
        )
        assert resp1.status_code == 201
        data1 = resp1.json()

        # 2. Replay with identical key & payload
        resp2 = client.post(
            f"/api/v1/interactions/{card_id}/deliveries",
            json=payload,
            headers=auth_headers("manager-a", key),
        )
        assert resp2.status_code == 201
        data2 = resp2.json()

        assert data1 == data2

        # 3. Verify exactly 1 delivery in DB
        with app.state.session_factory() as session:
            deliveries = session.query(Delivery).filter(Delivery.interaction_id == card_id).all()
            assert len(deliveries) == 1
            items = session.query(DeliveryItem).filter(DeliveryItem.delivery_id == deliveries[0].id).all()
            assert len(items) == 1

            # Verify exactly 1 delivery_recorded event in InteractionEvent
            events = session.query(InteractionEvent).filter(
                InteractionEvent.interaction_id == card_id,
                InteractionEvent.type == "delivery_recorded",
            ).all()
            assert len(events) == 1

    def test_idempotency_payload_mismatch_conflict(self, client):
        card = create_test_interaction(client, user="manager-a", org_id="org-1")
        card_id = card["id"]
        key = f"idem-key-{uuid4()}"

        payload1 = {"title": "Оригинальная поставка", "channel": "email"}
        resp1 = client.post(
            f"/api/v1/interactions/{card_id}/deliveries",
            json=payload1,
            headers=auth_headers("manager-a", key),
        )
        assert resp1.status_code == 201

        # Replay with same key but altered payload
        payload2 = {"title": "Измененная поставка", "channel": "email"}
        resp2 = client.post(
            f"/api/v1/interactions/{card_id}/deliveries",
            json=payload2,
            headers=auth_headers("manager-a", key),
        )
        assert resp2.status_code == 409
        assert resp2.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    def test_idempotency_key_invalid_format(self, client):
        card = create_test_interaction(client, user="manager-a", org_id="org-1")
        card_id = card["id"]

        # Blank key
        resp_blank = client.post(
            f"/api/v1/interactions/{card_id}/deliveries",
            json={"title": "Поставка", "channel": "email"},
            headers=auth_headers("manager-a", "   "),
        )
        assert resp_blank.status_code == 422
        assert resp_blank.json()["error"]["code"] == "VALIDATION_ERROR"

        # Key longer than 200 chars
        resp_long = client.post(
            f"/api/v1/interactions/{card_id}/deliveries",
            json={"title": "Поставка", "channel": "email"},
            headers=auth_headers("manager-a", "K" * 201),
        )
        assert resp_long.status_code == 422
        assert resp_long.json()["error"]["code"] == "VALIDATION_ERROR"


class TestSWE26PayloadBoundaryAndAudit:
    """Boundary conditions and Audit trail verification."""

    def test_boundary_title_lengths(self, client):
        card = create_test_interaction(client, user="manager-a", org_id="org-1")
        card_id = card["id"]

        # Title = 250 characters (allowed boundary)
        max_title = "П" * 250
        resp = client.post(
            f"/api/v1/interactions/{card_id}/deliveries",
            json={"title": max_title, "channel": "email"},
            headers=auth_headers("manager-a", str(uuid4())),
        )
        assert resp.status_code == 201
        assert resp.json()["items"][0]["title"] == max_title

        # Title = 251 characters (exceeds limit)
        resp_too_long = client.post(
            f"/api/v1/interactions/{card_id}/deliveries",
            json={"title": "П" * 251, "channel": "email"},
            headers=auth_headers("manager-a", str(uuid4())),
        )
        assert resp_too_long.status_code == 422

        # Title = empty string
        resp_empty = client.post(
            f"/api/v1/interactions/{card_id}/deliveries",
            json={"title": "", "channel": "email"},
            headers=auth_headers("manager-a", str(uuid4())),
        )
        assert resp_empty.status_code == 422

    def test_invalid_item_kind_rejected(self, client):
        card = create_test_interaction(client, user="manager-a", org_id="org-1")
        card_id = card["id"]

        resp = client.post(
            f"/api/v1/interactions/{card_id}/deliveries",
            json={"title": "ПО", "item_kind": "trojan_payload"},
            headers=auth_headers("manager-a", str(uuid4())),
        )
        assert resp.status_code == 422

    def test_audit_event_immutability_and_metadata(self, client, app):
        card = create_test_interaction(client, user="manager-a", org_id="org-1")
        card_id = card["id"]

        resp = client.post(
            f"/api/v1/interactions/{card_id}/deliveries",
            json={
                "title": "Аудируемая поставка",
                "item_kind": "license",
                "material_version": "v3.1.4",
                "channel": "email",
                "comment": "Тестовый аудит",
            },
            headers=auth_headers("manager-a", str(uuid4())),
        )
        assert resp.status_code == 201
        deliv_id = resp.json()["id"]

        detail = client.get(f"/api/v1/interactions/{card_id}", headers=auth_headers("manager-a")).json()
        deliv_events = [e for e in detail["events"] if e["type"] == "delivery_recorded"]
        assert len(deliv_events) == 1
        ev = deliv_events[0]

        assert ev["actor_name"] == "Анна Смирнова"
        assert ev["delivery_id"] == deliv_id
        assert ev["title"] == "Аудируемая поставка"
        assert ev["channel"] == "email"
        assert ev["item_kind"] == "license"
        assert ev["material_version"] == "v3.1.4"
        assert ev["status"] == "confirmed"

        # Check DB level record for actor_id
        with app.state.session_factory() as session:
            db_ev = session.query(InteractionEvent).filter(
                InteractionEvent.interaction_id == card_id,
                InteractionEvent.type == "delivery_recorded",
            ).one()
            assert db_ev.actor_id == "manager-a"
            assert db_ev.actor_name == "Анна Смирнова"
