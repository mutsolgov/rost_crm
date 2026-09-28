import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.models import IntegrationInbox, Interaction, Organization, User


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LEARNERS_FILE = REPO_ROOT / "данные предоставленные организаторами" / "Загрузка пользователей.xlsx"
PAYMENTS_FILE = REPO_ROOT / "данные предоставленные организаторами" / "Данные оплат.json"

EXPECTED_30_FIELDS = [
    "last_name",
    "first_name",
    "patronymic",
    "full_name",
    "email",
    "phone",
    "gender",
    "birth_date",
    "snils",
    "passport_series",
    "passport_number",
    "passport_issued_by",
    "passport_issued_date",
    "passport_subdivision_code",
    "registration_region",
    "registration_city",
    "registration_street",
    "registration_house",
    "registration_apartment",
    "registration_postal_code",
    "registration_address",
    "first_name_dative",
    "last_name_dative",
    "patronymic_dative",
    "education",
    "profession",
    "diploma_university",
    "diploma_last_name",
    "diploma_number",
    "diploma_series",
    "diploma_reg_number",
    "diploma_issue_date",
]


@pytest.fixture
def learner_bytes():
    assert LEARNERS_FILE.exists(), f"Learners file missing at {LEARNERS_FILE}"
    return LEARNERS_FILE.read_bytes()


@pytest.fixture
def payments_data():
    assert PAYMENTS_FILE.exists(), f"Payments file missing at {PAYMENTS_FILE}"
    return json.loads(PAYMENTS_FILE.read_text(encoding="utf-8"))


# ==============================================================================
# 1. UPLOAD ORDER SYMMETRY TESTS
# ==============================================================================

def test_symmetry_payments_first_then_learners_organizers_data(client: TestClient, learner_bytes: bytes, payments_data: list):
    """Verifies mutual enrichment when Payments JSON is uploaded FIRST, then Learners XLSX is uploaded SECOND."""
    headers = {"X-Demo-User": "administrator"}

    # Step 1: Upload payments JSON
    resp_p = client.post("/api/v1/integrations/upload/json", json=payments_data, headers=headers)
    assert resp_p.status_code == 200, resp_p.text

    # Step 2: Upload learners XLSX
    files = {
        "file": (
            "Загрузка пользователей.xlsx",
            learner_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    resp_l = client.post("/api/v1/integrations/upload/learners", files=files, headers=headers)
    assert resp_l.status_code == 200, resp_l.text
    data_l = resp_l.json()
    assert data_l["status"] == "success"
    assert data_l["total_records"] == 5
    assert data_l["enriched_with_payments"] == 5

    # Step 3: Verify bidirectional enrichment in DB
    with client.app.state.session_factory() as session:
        learners = session.query(IntegrationInbox).filter(
            IntegrationInbox.source == "lms",
            IntegrationInbox.entity_type == "learner",
        ).all()
        orders = session.query(IntegrationInbox).filter(
            IntegrationInbox.source == "lms",
            IntegrationInbox.entity_type == "lms_order",
        ).all()

        assert len(learners) == 5
        assert len(orders) >= 5

        for learner in learners:
            lp = learner.payload
            assert lp.get("linked_order_id") is not None
            assert lp.get("course_name") is not None
            assert lp.get("cohort") is not None
            assert lp.get("payment_status") == "paid"

            # Find matching order
            matched_order = next((o for o in orders if o.external_id == lp["linked_order_id"]), None)
            assert matched_order is not None
            op = matched_order.payload
            assert op.get("linked_learner_id") == learner.external_id
            assert op.get("has_questionnaire") is True
            assert op.get("questionnaire_status") == "completed"


def test_symmetry_learners_first_then_payments_organizers_data(client: TestClient, learner_bytes: bytes, payments_data: list):
    """Verifies mutual enrichment when Learners XLSX is uploaded FIRST, then Payments JSON is uploaded SECOND."""
    headers = {"X-Demo-User": "administrator"}

    # Step 1: Upload learners XLSX
    files = {
        "file": (
            "Загрузка пользователей.xlsx",
            learner_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    resp_l = client.post("/api/v1/integrations/upload/learners", files=files, headers=headers)
    assert resp_l.status_code == 200, resp_l.text
    assert resp_l.json()["created_count"] == 5

    # Step 2: Upload payments JSON
    resp_p = client.post("/api/v1/integrations/upload/json", json=payments_data, headers=headers)
    assert resp_p.status_code == 200, resp_p.text

    # Step 3: Verify bidirectional enrichment in DB
    with client.app.state.session_factory() as session:
        learners = session.query(IntegrationInbox).filter(
            IntegrationInbox.source == "lms",
            IntegrationInbox.entity_type == "learner",
        ).all()
        orders = session.query(IntegrationInbox).filter(
            IntegrationInbox.source == "lms",
            IntegrationInbox.entity_type == "lms_order",
        ).all()

        assert len(learners) == 5

        for learner in learners:
            lp = learner.payload
            assert lp.get("linked_order_id") is not None
            assert lp.get("course_name") is not None
            assert lp.get("payment_status") == "paid"

            matched_order = next((o for o in orders if o.external_id == lp["linked_order_id"]), None)
            assert matched_order is not None
            op = matched_order.payload
            assert op.get("linked_learner_id") == learner.external_id
            assert op.get("has_questionnaire") is True
            assert op.get("questionnaire_status") == "completed"


def test_symmetry_matching_by_phone_digits_when_email_differs(client: TestClient):
    """Tests that mutual enrichment works when email is different but normalized phone (10 digits) matches."""
    headers = {"X-Demo-User": "administrator"}

    order_data = [{
        "Номер заявки": "ORD-PHONE-MATCH-001",
        "Курс": "Python-разработчик",
        "Номер потока": "2",
        "Email": "student_order@domain.com",
        "Телефон": "+7 (999) 888-77-66",
        "Статус оплаты": "Оплачено",
    }]

    learner_csv = """Фамилия,Имя,Email,Номер телефона,СНИЛС,Серия паспорта,Номер паспорта
Кузнецов,Алексей,student_personal@gmail.com,89998887766,123-456-789 00,4510,123456
"""

    # Direction 1: Order first, then Learner
    resp_p = client.post("/api/v1/integrations/upload/json", json=order_data, headers=headers)
    assert resp_p.status_code == 200

    resp_l = client.post(
        "/api/v1/integrations/upload/learners",
        files={"file": ("learners.csv", learner_csv.encode("utf-8"), "text/csv")},
        headers=headers,
    )
    assert resp_l.status_code == 200
    assert resp_l.json()["enriched_with_payments"] == 1

    with client.app.state.session_factory() as session:
        learner = session.query(IntegrationInbox).filter(
            IntegrationInbox.source == "lms",
            IntegrationInbox.entity_type == "learner",
            IntegrationInbox.external_id == "student_personal@gmail.com",
        ).first()
        assert learner is not None
        assert learner.payload.get("linked_order_id") == "ORD-PHONE-MATCH-001"
        assert learner.payload.get("payment_status") == "paid"

        order = session.query(IntegrationInbox).filter(
            IntegrationInbox.source == "lms",
            IntegrationInbox.entity_type == "lms_order",
            IntegrationInbox.external_id == "ORD-PHONE-MATCH-001",
        ).first()
        assert order is not None
        assert order.payload.get("linked_learner_id") == "student_personal@gmail.com"
        assert order.payload.get("snils") == "123-456-789 00"
        assert order.payload.get("passport_number") == "123456"


def test_adversarial_unpaid_order_symmetry_flaw(client: TestClient):
    """ADVERSARIAL STRESS: Demonstrates asymmetry bug where unpaid orders are treated as 'paid'
    when payments are uploaded first, but as 'pending' when learners are uploaded first.
    """
    headers = {"X-Demo-User": "administrator"}

    # Scenario A: Unpaid payment uploaded first, then learner uploaded
    unpaid_order_a = [{
        "Номер заявки": "ORD-UNPAID-A",
        "Курс": "ИТ-Аналитик",
        "Номер потока": "1",
        "Email": "student_a@test.ru",
        "Телефон": "79991112233",
        "Статус оплаты": "Не оплачено",
    }]
    client.post("/api/v1/integrations/upload/json", json=unpaid_order_a, headers=headers)

    learner_csv_a = "Фамилия,Имя,Email,Номер телефона\nСмирнов,Игорь,student_a@test.ru,79991112233\n"
    client.post(
        "/api/v1/integrations/upload/learners",
        files={"file": ("learners_a.csv", learner_csv_a.encode("utf-8"), "text/csv")},
        headers=headers,
    )

    # Scenario B: Learner uploaded first, then unpaid payment uploaded
    learner_csv_b = "Фамилия,Имя,Email,Номер телефона\nПопов,Олег,student_b@test.ru,79994445566\n"
    client.post(
        "/api/v1/integrations/upload/learners",
        files={"file": ("learners_b.csv", learner_csv_b.encode("utf-8"), "text/csv")},
        headers=headers,
    )

    unpaid_order_b = [{
        "Номер заявки": "ORD-UNPAID-B",
        "Курс": "ИТ-Аналитик",
        "Номер потока": "1",
        "Email": "student_b@test.ru",
        "Телефон": "79994445566",
        "Статус оплаты": "Не оплачено",
    }]
    client.post("/api/v1/integrations/upload/json", json=unpaid_order_b, headers=headers)

    with client.app.state.session_factory() as session:
        learner_a = session.query(IntegrationInbox).filter(IntegrationInbox.external_id == "student_a@test.ru").first()
        learner_b = session.query(IntegrationInbox).filter(IntegrationInbox.external_id == "student_b@test.ru").first()

        status_a = learner_a.payload.get("payment_status")
        status_b = learner_b.payload.get("payment_status")

        # In a fully symmetric system, status_a must equal status_b.
        # But in service.py line 1281: payload["payment_status"] = "paid" is hardcoded!
        # Thus status_a == 'paid' while status_b == 'pending'.
        assert status_a == "paid", f"Expected 'paid' due to hardcoded line 1281, got {status_a}"
        assert status_b == "pending", f"Expected 'pending' from payment JSON check, got {status_b}"
        # We record this asymmetry finding!


# ==============================================================================
# 2. DEDUPLICATION & IDEMPOTENCY TESTS
# ==============================================================================

def test_consecutive_file_upload_deduplication(client: TestClient, learner_bytes: bytes):
    """Uploading the same learners file multiple times updates existing entries and never creates duplicates."""
    headers = {"X-Demo-User": "administrator"}
    files = {
        "file": (
            "Загрузка пользователей.xlsx",
            learner_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }

    # First upload: 5 created
    resp1 = client.post("/api/v1/integrations/upload/learners", files=files, headers=headers)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["created_count"] == 5
    assert data1["updated_count"] == 0

    # Second upload with Idempotency-Key header: 5 updated, 0 created
    idemp_headers = dict(headers, **{"Idempotency-Key": "idemp-upload-learners-key-1"})
    resp2 = client.post("/api/v1/integrations/upload/learners", files=files, headers=idemp_headers)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["created_count"] == 0
    assert data2["updated_count"] == 5

    # Third upload with different Idempotency-Key: still 5 updated, 0 created
    idemp_headers2 = dict(headers, **{"Idempotency-Key": "idemp-upload-learners-key-2"})
    resp3 = client.post("/api/v1/integrations/upload/learners", files=files, headers=idemp_headers2)
    assert resp3.status_code == 200
    assert resp3.json()["created_count"] == 0
    assert resp3.json()["updated_count"] == 5

    with client.app.state.session_factory() as session:
        total_learners = session.query(IntegrationInbox).filter(
            IntegrationInbox.source == "lms",
            IntegrationInbox.entity_type == "learner",
        ).count()
        assert total_learners == 5, f"Expected exactly 5 learners in IntegrationInbox, got {total_learners}"


def test_adversarial_intra_file_duplicate_rows_integrity_error(client: TestClient):
    """ADVERSARIAL STRESS: Demonstrates empirical flaw where duplicate rows within the SAME file
    cause an unhandled SQLAlchemy IntegrityError (HTTP 500) because autoflush=False prevents
    db.scalar() from detecting newly added objects before commit.
    """
    headers = {"X-Demo-User": "administrator"}

    # CSV with 2 duplicate rows for the same student
    duplicate_rows_csv = """Фамилия,Имя,Email,Номер телефона
Иванов,Иван,duplicate_student@test.ru,79991112233
Иванов,Иван,duplicate_student@test.ru,79991112233
"""
    # This triggers IntegrityError: UNIQUE constraint failed: integration_inbox.source, integration_inbox.entity_type...
    with pytest.raises(Exception) as excinfo:
        client.post(
            "/api/v1/integrations/upload/learners",
            files={"file": ("learners_dup.csv", duplicate_rows_csv.encode("utf-8"), "text/csv")},
            headers=headers,
        )
    assert "IntegrityError" in str(type(excinfo.value)) or "UNIQUE constraint failed" in str(excinfo.value)


def test_adversarial_json_duplicate_orders_integrity_error(client: TestClient):
    """ADVERSARIAL STRESS: Demonstrates empirical flaw where duplicate order records within the SAME JSON
    cause an unhandled SQLAlchemy IntegrityError (HTTP 500) because autoflush=False prevents
    db.scalar() from detecting newly added orders before commit.
    """
    headers = {"X-Demo-User": "administrator"}

    duplicate_orders_json = [
        {
            "Номер заявки": "ORD-INTRA-DUP-001",
            "Курс": "Python-разработчик",
            "Номер потока": "1",
            "Email": "dup_order@test.ru",
            "Телефон": "79991112233",
            "Статус оплаты": "Оплачено",
        },
        {
            "Номер заявки": "ORD-INTRA-DUP-001",
            "Курс": "Python-разработчик",
            "Номер потока": "1",
            "Email": "dup_order@test.ru",
            "Телефон": "79991112233",
            "Статус оплаты": "Оплачено",
        },
    ]

    with pytest.raises(Exception) as excinfo:
        client.post(
            "/api/v1/integrations/upload/json",
            json=duplicate_orders_json,
            headers=headers,
        )
    assert "IntegrityError" in str(type(excinfo.value)) or "UNIQUE constraint failed" in str(excinfo.value)


# ==============================================================================
# 3. PAYLOAD COMPLETENESS TESTS (ALL 30 FIELDS)
# ==============================================================================

def test_payload_completeness_organizers_file_all_30_keys(client: TestClient, learner_bytes: bytes):
    """Verifies that all 30 fields defined in the questionnaire schema are present in IntegrationInbox.payload
    for the organizers' file 'Загрузка пользователей.xlsx'.
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
    assert resp.status_code == 200

    with client.app.state.session_factory() as session:
        learners = session.query(IntegrationInbox).filter(
            IntegrationInbox.source == "lms",
            IntegrationInbox.entity_type == "learner",
        ).all()
        assert len(learners) == 5

        for idx, learner in enumerate(learners):
            payload = learner.payload
            assert isinstance(payload, dict)

            missing_fields = [f for f in EXPECTED_30_FIELDS if f not in payload]
            assert not missing_fields, f"Learner {learner.external_id} missing fields: {missing_fields}"

            # Check identity fields present in the sample file
            assert payload["last_name"] != ""
            assert payload["first_name"] != ""
            assert payload["email"] != ""
            assert payload["phone"] != ""


def test_payload_completeness_full_data_row_extraction(client: TestClient):
    """Verifies that when all 30 fields are populated in the input file, every field is correctly
    extracted and preserved without data loss or truncation.
    """
    headers = {"X-Demo-User": "administrator"}

    full_learner_csv = (
        "Фамилия,Имя,Отчествопри наличии),Номер телефона,Email,СНИЛС,Серия паспорта,Номер паспорта,"
        "Кем выдан паспорт,Дата выдачи паспорта,Код подразделения,Пол,Дата рождения,Регион регистрации,"
        "Населенный пункт регистрации,Улица регистрации,Дом регистрации,Квартира регистрации,Индекс регистрации,"
        "Имядательный падеж),Фамилиядательный падеж),Отчестводательный падеж),Образование,Профессия по диплому,"
        "Учебное заведение по диплому,\"Фамилия, указанная в дипломе\",Номер диплома,Серия диплома,"
        "Регистрационный номер диплома,Дата выдачи диплома\n"
        "Сидоров,Петр,Алексеевич,79998881122,sidorov@test.ru,123-456-789 99,4512,987654,"
        "ГУ МВД по г. Москве,15.05.2018,770-001,М,20.08.1995,Москва,г. Москва,"
        "ул. Ленина,10,25,101000,Петру,Сидорову,Алексеевичу,Высшее,Программист,"
        "МГТУ им. Баумана,Сидоров,112233,ВС,REG-9999,30.06.2017\n"
    )

    resp = client.post(
        "/api/v1/integrations/upload/learners",
        files={"file": ("learners_full.csv", full_learner_csv.encode("utf-8"), "text/csv")},
        headers=headers,
    )
    assert resp.status_code == 200

    with client.app.state.session_factory() as session:
        learner = session.query(IntegrationInbox).filter(
            IntegrationInbox.source == "lms",
            IntegrationInbox.entity_type == "learner",
            IntegrationInbox.external_id == "sidorov@test.ru",
        ).first()
        assert learner is not None
        p = learner.payload

        assert p["last_name"] == "Сидоров"
        assert p["first_name"] == "Петр"
        assert p["patronymic"] == "Алексеевич"
        assert p["phone"] == "79998881122"
        assert p["email"] == "sidorov@test.ru"
        assert p["snils"] == "123-456-789 99"
        assert p["passport_series"] == "4512"
        assert p["passport_number"] == "987654"
        assert p["passport_issued_by"] == "ГУ МВД по г. Москве"
        assert p["passport_issued_date"] == "15.05.2018"
        assert p["passport_subdivision_code"] == "770-001"
        assert p["gender"] == "М"
        assert p["birth_date"] == "20.08.1995"
        assert p["registration_region"] == "Москва"
        assert p["registration_city"] == "г. Москва"
        assert p["registration_street"] == "ул. Ленина"
        assert p["registration_house"] == "10"
        assert p["registration_apartment"] == "25"
        assert p["registration_postal_code"] == "101000"
        assert p["first_name_dative"] == "Петру"
        assert p["last_name_dative"] == "Сидорову"
        assert p["patronymic_dative"] == "Алексеевичу"
        assert p["education"] == "Высшее"
        assert p["profession"] == "Программист"
        assert p["diploma_university"] == "МГТУ им. Баумана"
        assert p["diploma_last_name"] == "Сидоров"
        assert p["diploma_number"] == "112233"
        assert p["diploma_series"] == "ВС"
        assert p["diploma_reg_number"] == "REG-9999"
        assert p["diploma_issue_date"] == "30.06.2017"


# ==============================================================================
# 4. STAGE 11 RECONCILIATION TESTS
# ==============================================================================

def test_stage_11_reconciliation_happy_path(client: TestClient, learner_bytes: bytes):
    """Verifies reconciling learner with organization org-3 and stage 11 ('classes') interaction ix-6."""
    headers = {"X-Demo-User": "administrator"}

    # 1. Ingest learners
    files = {
        "file": (
            "Загрузка пользователей.xlsx",
            learner_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    client.post("/api/v1/integrations/upload/learners", files=files, headers=headers)

    with client.app.state.session_factory() as session:
        learner = session.query(IntegrationInbox).filter(
            IntegrationInbox.source == "lms",
            IntegrationInbox.entity_type == "learner",
        ).first()
        assert learner is not None
        inbox_id = learner.id

        # Verify interaction ix-6 is seeded at stage 11 'classes'
        ix6 = session.get(Interaction, "ix-6")
        assert ix6 is not None
        assert ix6.state == "classes"

    # 2. Reconcile learner to org-3 and ix-6
    resolve_headers = dict(headers, **{"Idempotency-Key": f"idemp-resolve-stage11-{inbox_id}"})
    resolve_body = {
        "action": "link_existing",
        "organization_id": "org-3",
        "interaction_id": "ix-6",
    }
    resp = client.post(
        f"/api/v1/integrations/inbox/{inbox_id}/resolve",
        json=resolve_body,
        headers=resolve_headers,
    )
    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert res["status"] == "processed"
    assert res["matched_organization_id"] == "org-3"
    assert res["matched_interaction_id"] == "ix-6"
    assert res["processed_at"] is not None

    # 3. Verify in DB
    with client.app.state.session_factory() as session:
        updated = session.get(IntegrationInbox, inbox_id)
        assert updated.status == "processed"
        assert updated.matched_organization_id == "org-3"
        assert updated.matched_interaction_id == "ix-6"
        assert updated.processed_at is not None
        assert updated.payload["matched_organization_id"] == "org-3"
        assert updated.payload["matched_interaction_id"] == "ix-6"


def test_stage_11_reconciliation_idempotency_replay(client: TestClient, learner_bytes: bytes):
    """Replaying the exact same reconciliation request with same Idempotency-Key returns replayed response."""
    headers = {"X-Demo-User": "administrator"}
    files = {
        "file": (
            "Загрузка пользователей.xlsx",
            learner_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    client.post("/api/v1/integrations/upload/learners", files=files, headers=headers)

    with client.app.state.session_factory() as session:
        learner = session.query(IntegrationInbox).filter(
            IntegrationInbox.source == "lms",
            IntegrationInbox.entity_type == "learner",
        ).first()
        inbox_id = learner.id

    idemp_key = f"replay-key-{inbox_id}"
    resolve_headers = dict(headers, **{"Idempotency-Key": idemp_key})
    resolve_body = {
        "action": "link_existing",
        "organization_id": "org-3",
        "interaction_id": "ix-6",
    }

    # First attempt
    resp1 = client.post(f"/api/v1/integrations/inbox/{inbox_id}/resolve", json=resolve_body, headers=resolve_headers)
    assert resp1.status_code == 200

    # Second attempt with SAME idempotency key (replay)
    resp2 = client.post(f"/api/v1/integrations/inbox/{inbox_id}/resolve", json=resolve_body, headers=resolve_headers)
    assert resp2.status_code == 200
    assert resp2.json()["matched_interaction_id"] == "ix-6"
    assert resp2.json()["status"] == "processed"


def test_stage_11_reconciliation_conflict_on_different_key(client: TestClient, learner_bytes: bytes):
    """Attempting to resolve an already processed learner with a different Idempotency-Key raises 409 Conflict."""
    headers = {"X-Demo-User": "administrator"}
    files = {
        "file": (
            "Загрузка пользователей.xlsx",
            learner_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    client.post("/api/v1/integrations/upload/learners", files=files, headers=headers)

    with client.app.state.session_factory() as session:
        learner = session.query(IntegrationInbox).filter(
            IntegrationInbox.source == "lms",
            IntegrationInbox.entity_type == "learner",
        ).first()
        inbox_id = learner.id

    resolve_body = {
        "action": "link_existing",
        "organization_id": "org-3",
        "interaction_id": "ix-6",
    }

    # First resolve
    r1 = client.post(
        f"/api/v1/integrations/inbox/{inbox_id}/resolve",
        json=resolve_body,
        headers=dict(headers, **{"Idempotency-Key": f"key-1-{inbox_id}"}),
    )
    assert r1.status_code == 200

    # Second resolve with DIFFERENT key -> 409 Conflict
    r2 = client.post(
        f"/api/v1/integrations/inbox/{inbox_id}/resolve",
        json=resolve_body,
        headers=dict(headers, **{"Idempotency-Key": f"key-2-{inbox_id}"}),
    )
    assert r2.status_code == 409, r2.text
    assert "уже обработана" in r2.json()["error"]["message"]


def test_stage_11_reconciliation_error_paths(client: TestClient, learner_bytes: bytes):
    """Verifies error handling for missing Idempotency-Key, invalid org/interaction, and invalid action."""
    headers = {"X-Demo-User": "administrator"}
    files = {
        "file": (
            "Загрузка пользователей.xlsx",
            learner_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    client.post("/api/v1/integrations/upload/learners", files=files, headers=headers)

    with client.app.state.session_factory() as session:
        learner = session.query(IntegrationInbox).filter(
            IntegrationInbox.source == "lms",
            IntegrationInbox.entity_type == "learner",
        ).first()
        inbox_id = learner.id

    # 1. Missing Idempotency-Key header -> 422 / 400
    r_no_key = client.post(
        f"/api/v1/integrations/inbox/{inbox_id}/resolve",
        json={"action": "link_existing", "organization_id": "org-3"},
        headers=headers,
    )
    assert r_no_key.status_code in (400, 422)

    # 2. Non-existent organization_id -> 404
    r_bad_org = client.post(
        f"/api/v1/integrations/inbox/{inbox_id}/resolve",
        json={"action": "link_existing", "organization_id": "non-existent-org"},
        headers=dict(headers, **{"Idempotency-Key": f"k-bad-org-{inbox_id}"}),
    )
    assert r_bad_org.status_code == 404

    # 3. Non-existent interaction_id -> 404
    r_bad_ix = client.post(
        f"/api/v1/integrations/inbox/{inbox_id}/resolve",
        json={"action": "link_existing", "organization_id": "org-3", "interaction_id": "non-existent-ix"},
        headers=dict(headers, **{"Idempotency-Key": f"k-bad-ix-{inbox_id}"}),
    )
    assert r_bad_ix.status_code == 404

    # 4. Non-existent inbox_id -> 404
    r_bad_inbox = client.post(
        "/api/v1/integrations/inbox/non-existent-inbox-id/resolve",
        json={"action": "link_existing", "organization_id": "org-3"},
        headers=dict(headers, **{"Idempotency-Key": "k-bad-inbox"}),
    )
    assert r_bad_inbox.status_code == 404

    # 5. Invalid action -> 400 / 422
    r_bad_act = client.post(
        f"/api/v1/integrations/inbox/{inbox_id}/resolve",
        json={"action": "unknown_action"},
        headers=dict(headers, **{"Idempotency-Key": f"k-bad-act-{inbox_id}"}),
    )
    assert r_bad_act.status_code in (400, 422)


def test_reconciliation_action_reject(client: TestClient, learner_bytes: bytes):
    """Verifies that action='reject' marks the learner as rejected with the specified reason."""
    headers = {"X-Demo-User": "administrator"}
    files = {
        "file": (
            "Загрузка пользователей.xlsx",
            learner_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    client.post("/api/v1/integrations/upload/learners", files=files, headers=headers)

    with client.app.state.session_factory() as session:
        learner = session.query(IntegrationInbox).filter(
            IntegrationInbox.source == "lms",
            IntegrationInbox.entity_type == "learner",
        ).first()
        inbox_id = learner.id

    resp = client.post(
        f"/api/v1/integrations/inbox/{inbox_id}/resolve",
        json={"action": "reject", "reason": "Заявка отозвана студентом"},
        headers=dict(headers, **{"Idempotency-Key": f"k-reject-{inbox_id}"}),
    )
    assert resp.status_code == 200
    res = resp.json()
    assert res["status"] == "rejected"
    assert res["error_message"] == "Заявка отозвана студентом"

    with client.app.state.session_factory() as session:
        updated = session.get(IntegrationInbox, inbox_id)
        assert updated.status == "rejected"
        assert updated.error_message == "Заявка отозвана студентом"


# ==============================================================================
# 5. RBAC & SECURITY TESTS
# ==============================================================================

def test_rbac_manager_forbidden_to_upload_learners(client: TestClient, learner_bytes: bytes):
    """Manager (standard operator) must be rejected with 403 Forbidden on learner upload."""
    manager_headers = {"X-Demo-User": "manager-a"}
    files = {
        "file": (
            "Загрузка пользователей.xlsx",
            learner_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    resp = client.post("/api/v1/integrations/upload/learners", files=files, headers=manager_headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


def test_rbac_supervisor_allowed_to_upload_learners(client: TestClient, learner_bytes: bytes):
    """Supervisor must be permitted to upload learner questionnaires."""
    supervisor_headers = {"X-Demo-User": "supervisor"}
    files = {
        "file": (
            "Загрузка пользователей.xlsx",
            learner_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    resp = client.post("/api/v1/integrations/upload/learners", files=files, headers=supervisor_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


def test_adversarial_corrupt_xlsx_handling(client: TestClient):
    """ADVERSARIAL STRESS: Demonstrates that uploading non-zip bytes with .xlsx extension
    causes an unhandled BadZipFile exception rather than a clean 422 APIError response.
    """
    headers = {"X-Demo-User": "administrator"}
    corrupt_bytes = b"This is definitely not an xlsx zip file!"
    files = {
        "file": (
            "corrupt.xlsx",
            corrupt_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    with pytest.raises(Exception) as excinfo:
        client.post("/api/v1/integrations/upload/learners", files=files, headers=headers)
    assert "BadZipFile" in str(type(excinfo.value)) or "BadZipFile" in str(excinfo.value)

