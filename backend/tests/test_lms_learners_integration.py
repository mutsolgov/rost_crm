import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.models import IntegrationInbox, Interaction, Organization, User


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LEARNERS_FILE = REPO_ROOT / "данные предоставленные организаторами" / "Загрузка пользователей.xlsx"
PAYMENTS_FILE = REPO_ROOT / "данные предоставленные организаторами" / "Данные оплат.json"

EXPECTED_LEARNERS = [
    {
        "name": "Черепанова Светлана Васильевна",
        "email": "cherepanona.s@test.ru",
        "phone": "79990234365",
        "order_id": "ORD-20260313051569-OYJRVN",
        "course": "Анализ данных без программирования",
    },
    {
        "name": "Кричанов Максим Сергеевич",
        "email": "max_crich@mail.ru",
        "phone": "79977361351",
        "order_id": "ORD-202605130654453-GDJIKG",
        "course": "Инженер-тестировщик",
    },
    {
        "name": "Григорьев Станислав Семенович",
        "email": "grigorev355@gmail.com",
        "phone": "79947392263",
        "order_id": "ORD-20261721184559-AJIJEN",
        "course": "Управление ИТ-проектами на базе программного продукта ПАО «Ростелеком»",
    },
    {
        "name": "Осипенко Ирина Викторовна",
        "email": "osipenko833484@mail.ru",
        "phone": "79934253846",
        "order_id": "ORD-20260522061330-2LT0MG",
        "course": "Промпт-инжиниринг",
    },
    {
        "name": "Иванов Михаил Петрович",
        "email": "mp_ivanov@mail.ru",
        "phone": "79924583434",
        "order_id": "ORD-20260904075403-ZXFSZX",
        "course": "Python-разработчик с использованием инструментов ИИ",
    },
]


@pytest.fixture
def learner_bytes():
    assert LEARNERS_FILE.exists(), f"Learners file missing at {LEARNERS_FILE}"
    return LEARNERS_FILE.read_bytes()


@pytest.fixture
def payments_data():
    assert PAYMENTS_FILE.exists(), f"Payments file missing at {PAYMENTS_FILE}"
    return json.loads(PAYMENTS_FILE.read_text(encoding="utf-8"))


def test_parse_lms_learners_xlsx_into_integration_inbox(client: TestClient, learner_bytes: bytes):
    """R2.1: Verifies parsing of 'Загрузка пользователей.xlsx' into IntegrationInbox
    with entity_type='learner', source='lms', external_id=normalized_email, and all 30 fields.
    """
    headers = {"X-Demo-User": "administrator"}
    files = {
        "file": (
            "Загрузка пользователей.xlsx",
            learner_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }

    resp = client.post("/api/v1/integrations/upload/learners", files=files, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "success"
    assert data["total_records"] == 5
    assert data["created_count"] == 5

    with client.app.state.session_factory() as session:
        inbox_items = session.query(IntegrationInbox).filter(
            IntegrationInbox.source == "lms",
            IntegrationInbox.entity_type == "learner",
        ).all()
        assert len(inbox_items) == 5

        # Check all 30 fields structure
        for item in inbox_items:
            payload = item.payload
            assert payload is not None
            assert item.status == "pending"
            assert item.source_revision == "1"

            # Identity
            assert "last_name" in payload
            assert "first_name" in payload
            assert "patronymic" in payload
            assert "full_name" in payload
            assert "email" in payload
            assert "phone" in payload
            assert "gender" in payload
            assert "birth_date" in payload

            # Passport
            assert "snils" in payload
            assert "passport_series" in payload
            assert "passport_number" in payload
            assert "passport_issued_by" in payload
            assert "passport_issued_date" in payload
            assert "passport_subdivision_code" in payload

            # Registration address
            assert "registration_region" in payload
            assert "registration_city" in payload
            assert "registration_street" in payload
            assert "registration_house" in payload
            assert "registration_apartment" in payload
            assert "registration_postal_code" in payload
            assert "registration_address" in payload

            # Cases & Education
            assert "first_name_dative" in payload
            assert "last_name_dative" in payload
            assert "patronymic_dative" in payload
            assert "education" in payload
            assert "profession" in payload
            assert "diploma_university" in payload
            assert "diploma_last_name" in payload
            assert "diploma_number" in payload
            assert "diploma_series" in payload
            assert "diploma_reg_number" in payload
            assert "diploma_issue_date" in payload


def test_bidirectional_enrichment_payments_and_learners(client: TestClient, learner_bytes: bytes, payments_data: list):
    """R2.2: Verifies mutual enrichment between LMS payments JSON and learner XLSX.
    Learners uploaded first -> payments JSON uploaded second -> both records enriched.
    """
    admin_headers = {"X-Demo-User": "administrator"}

    # 1. Upload learners
    files = {
        "file": (
            "Загрузка пользователей.xlsx",
            learner_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    resp_l = client.post("/api/v1/integrations/upload/learners", files=files, headers=admin_headers)
    assert resp_l.status_code == 200, resp_l.text

    # 2. Upload payments JSON
    resp_p = client.post("/api/v1/integrations/upload/json", json=payments_data, headers=admin_headers)
    assert resp_p.status_code == 200, resp_p.text

    with client.app.state.session_factory() as session:
        for exp in EXPECTED_LEARNERS:
            # Check learner is enriched with order
            learner = session.query(IntegrationInbox).filter(
                IntegrationInbox.source == "lms",
                IntegrationInbox.entity_type == "learner",
                IntegrationInbox.external_id == exp["email"],
            ).first()
            assert learner is not None
            assert learner.payload.get("linked_order_id") == exp["order_id"]
            assert learner.payload.get("course_name") == exp["course"]
            assert learner.payload.get("payment_status") == "paid"

            # Check order is enriched with learner
            order = session.query(IntegrationInbox).filter(
                IntegrationInbox.source == "lms",
                IntegrationInbox.entity_type == "lms_order",
                IntegrationInbox.external_id == exp["order_id"],
            ).first()
            assert order is not None
            assert order.payload.get("linked_learner_id") == exp["email"]
            assert order.payload.get("has_questionnaire") is True
            assert order.payload.get("questionnaire_status") == "completed"

    # 3. Test reverse order: re-upload learners, verifying enriched_with_payments count
    resp_l2 = client.post("/api/v1/integrations/upload/learners", files=files, headers=admin_headers)
    assert resp_l2.status_code == 200
    data_l2 = resp_l2.json()
    assert data_l2["enriched_with_payments"] == 5
    assert data_l2["updated_count"] == 5


def test_domain_purity_zero_learners_in_users_and_catalogs_owners(client: TestClient, learner_bytes: bytes):
    """R1: Verifies domain purity: 0 learner accounts in User table and catalogs.owners."""
    admin_headers = {"X-Demo-User": "administrator"}

    # Upload learners
    files = {
        "file": (
            "Загрузка пользователей.xlsx",
            learner_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    client.post("/api/v1/integrations/upload/learners", files=files, headers=admin_headers)

    # 1. Check catalogs endpoint
    resp_cat = client.post("/api/v1/catalogs", headers=admin_headers)
    if resp_cat.status_code == 405:
        resp_cat = client.get("/api/v1/catalogs", headers=admin_headers)
    assert resp_cat.status_code == 200, resp_cat.text
    catalogs = resp_cat.json()

    owners = catalogs["owners"]
    assert len(owners) > 0

    learner_emails = {exp["email"] for exp in EXPECTED_LEARNERS}
    learner_names = {exp["name"] for exp in EXPECTED_LEARNERS}
    learner_ids = {"cherepanona-s", "max_crich", "grigorev355", "osipenko833484", "mp_ivanov"}

    for owner in owners:
        assert owner["id"] not in learner_ids
        assert owner["name"] not in learner_names
        assert owner.get("role") in ("manager", "supervisor", "administrator")

    # 2. Check User table directly
    with client.app.state.session_factory() as session:
        for exp in EXPECTED_LEARNERS:
            db_u = session.query(User).filter(User.keycloak_subject == exp["email"]).first()
            assert db_u is None, f"Learner {exp['email']} must not exist in User table!"
        for lid in learner_ids:
            db_u2 = session.query(User).filter(User.id == lid).first()
            assert db_u2 is None, f"Learner ID {lid} must not exist in User table!"


def test_reconcile_learner_at_stage_11_classes(client: TestClient, learner_bytes: bytes):
    """R2.5: Verifies learner reconciliation with partner university and stage 11 ('classes') interaction."""
    admin_headers = {"X-Demo-User": "administrator"}

    # Upload learners
    files = {
        "file": (
            "Загрузка пользователей.xlsx",
            learner_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    client.post("/api/v1/integrations/upload/learners", files=files, headers=admin_headers)

    with client.app.state.session_factory() as session:
        learner_inbox = session.query(IntegrationInbox).filter(
            IntegrationInbox.source == "lms",
            IntegrationInbox.entity_type == "learner",
        ).first()
        assert learner_inbox is not None
        inbox_id = learner_inbox.id

        # Verify seeded interaction ix-6 is at stage 11 'classes'
        ix6 = session.get(Interaction, "ix-6")
        assert ix6 is not None
        assert ix6.state == "classes"

    # Reconcile learner with organization org-3 and interaction ix-6
    resolve_payload = {
        "action": "link_existing",
        "organization_id": "org-3",
        "interaction_id": "ix-6",
    }
    resolve_headers = dict(admin_headers, **{"Idempotency-Key": f"idemp-resolve-{inbox_id}"})
    resp = client.post(
        f"/api/v1/integrations/inbox/{inbox_id}/resolve",
        json=resolve_payload,
        headers=resolve_headers,
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()
    assert result["status"] == "processed"
    assert result["matched_organization_id"] == "org-3"
    assert result["matched_interaction_id"] == "ix-6"

    with client.app.state.session_factory() as session:
        updated_item = session.get(IntegrationInbox, inbox_id)
        assert updated_item.status == "processed"
        assert updated_item.matched_organization_id == "org-3"
        assert updated_item.matched_interaction_id == "ix-6"
        assert updated_item.payload.get("matched_interaction_id") == "ix-6"


def test_catalog_import_preview_redirects_lms_learners(client: TestClient, learner_bytes: bytes):
    """R2.4: When LMS learners file uploaded to catalog modal, redirects to Integrations and creates 0 CRM users."""
    admin_headers = {"X-Demo-User": "administrator"}
    files = {
        "file": (
            "Загрузка пользователей.xlsx",
            learner_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }

    resp = client.post("/api/v1/catalogs/organizations/import/preview", files=files, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    preview = resp.json()

    assert preview["detected_type"] == "lms_learners"
    assert preview["redirect"] == "/integrations"
    assert "Распознан реестр слушателей LMS" in preview["message"]
    assert preview["total_rows"] == 5
    assert preview["users_created"] == 0
    assert len(preview["preview_rows"]) == 0

    # Ensure IntegrationInbox received the data safely
    with client.app.state.session_factory() as session:
        inbox_count = session.query(IntegrationInbox).filter(
            IntegrationInbox.source == "lms",
            IntegrationInbox.entity_type == "learner",
        ).count()
        assert inbox_count == 5

        # And User table has 0 learners
        user_count = session.query(User).filter(
            User.keycloak_subject.in_([u["email"] for u in EXPECTED_LEARNERS])
        ).count()
        assert user_count == 0
