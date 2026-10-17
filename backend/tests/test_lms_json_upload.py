import pytest
from fastapi.testclient import TestClient

from app.models import IntegrationInbox, LearningMetric, User
from app.seed import seed_database

def test_lms_json_upload_permissions(client: TestClient):
    payload = [{"id": "ord-1", "user_id": 10, "status": "paid", "amount": 5000}]
    
    # Manager must be rejected with 403
    resp = client.post("/api/v1/integrations/upload/json", json=payload, headers={"X-Demo-User": "manager-a"})
    assert resp.status_code == 403

    # Supervisor is allowed
    resp = client.post("/api/v1/integrations/upload/json", json=payload, headers={"X-Demo-User": "supervisor"})
    assert resp.status_code == 200

    # Admin is allowed
    resp = client.post("/api/v1/integrations/upload/json", json=payload, headers={"X-Demo-User": "administrator"})
    assert resp.status_code == 200

def test_lms_json_upload_null_resilience_and_metrics(client: TestClient):
    # Array with valid objects, nulls, and different payment statuses
    payload = [
        {"order_id": "LMS-101", "payment_status": "success", "amount": 12000, "program_id": "prog-python"},
        None,
        {"order_id": "LMS-102", "status": "paid", "sum": 8000, "program_name": "Веб-разработка"},
        None,
        {"id": "LMS-103", "payment_status": "pending", "amount": 10000},
        {"id": "LMS-104", "status": "failed", "amount": 10000}
    ]

    resp = client.post("/api/v1/integrations/upload/json", json=payload, headers={"X-Demo-User": "administrator"})
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["total_records"] == 6
    assert data["skipped_nulls"] == 2
    assert data["processed_count"] == 4
    assert data["paid_count"] == 2
    assert data["total_paid_amount"] == 20000.0

    # Verify IntegrationInbox items created
    with client.app.state.session_factory() as session:
        inbox_items = session.query(IntegrationInbox).filter(IntegrationInbox.entity_type == "lms_order").all()
        assert len(inbox_items) >= 4
        for item in inbox_items:
            assert item.status == "pending"
            assert item.source in ("lms", "lms_payments_json")

        # Verify LearningMetric aggregation across all programs (including pool)
        all_metrics = session.query(LearningMetric).filter(LearningMetric.source == "lms").all()
        total_apps = sum(m.value for m in all_metrics if m.metric_code == "applications_count")
        total_payments = sum(m.value for m in all_metrics if m.metric_code == "payments_count")
        assert total_apps == 4
        assert total_payments == 2

        # Ensure no synthetic batch total metrics exist (no double counting)
        batch_metrics = [m for m in all_metrics if m.external_id in ("lms-app-batch-total", "lms-pay-batch-total")]
        assert len(batch_metrics) == 0

        # Verify fallback to pool organization and program for unmapped records
        unmapped_items = (
            session.query(IntegrationInbox)
            .filter(IntegrationInbox.external_id.in_(["LMS-103", "LMS-104"]))
            .all()
        )
        assert len(unmapped_items) == 2
        for item in unmapped_items:
            assert item.payload.get("matched_organization_name") == "ИТ Школа Ростелекома (Пул заявок)"
            assert item.payload.get("matched_program_name") == "Общий пул программ LMS"


def test_seed_database_preserves_added_staff_users(client: TestClient):
    """R1: Verify users with manager/supervisor/administrator roles added outside initial USERS
    are retained upon re-seeding, while non-staff / invalid roles are purged.
    """
    staff_ids = ["custom-staff-mgr", "custom-staff-sup", "custom-staff-adm"]
    non_staff_ids = ["rogue-user-learner", "rogue-user-guest", "rogue-user-norole"]

    with client.app.state.session_factory() as session:
        for uid in staff_ids + non_staff_ids:
            existing = session.get(User, uid)
            if existing:
                session.delete(existing)
        session.commit()

        session.add_all([
            User(id="custom-staff-mgr", keycloak_subject="c_mgr@rt.ru", name="Менеджер 1", role="manager", active=True),
            User(id="custom-staff-sup", keycloak_subject="c_sup@rt.ru", name="Супервизор 1", role="supervisor", active=True),
            User(id="custom-staff-adm", keycloak_subject="c_adm@rt.ru", name="Администратор 1", role="administrator", active=True),
            User(id="rogue-user-learner", keycloak_subject="r_lrn@test.ru", name="Студент 1", role="learner", active=True),
            User(id="rogue-user-guest", keycloak_subject="r_gst@test.ru", name="Гость 1", role="guest", active=True),
            User(id="rogue-user-norole", keycloak_subject="r_nor@test.ru", name="Без роли", role="", active=True),
        ])
        session.commit()

    with client.app.state.session_factory() as session:
        seed_database(session)
        session.commit()

    with client.app.state.session_factory() as session:
        for sid in staff_ids:
            u = session.get(User, sid)
            assert u is not None, f"Staff user {sid} should be preserved after re-seeding!"
            assert u.role in ("manager", "supervisor", "administrator")

        for nid in non_staff_ids:
            u = session.get(User, nid)
            assert u is None, f"Non-staff user {nid} should be purged after re-seeding!"


def test_seed_database_preserves_employee_added_via_api(client: TestClient):
    """R1/R3: Verify an employee created via CRM import API is preserved upon repeated seed_database(db)."""
    target_email = "api_added_employee@rt.ru"
    commit_payload = {
        "source_name": "Загрузка пользователей.xlsx",
        "rows": [
            {
                "data": {
                    "name": "Инженер АПИ Ростелеком",
                    "email": target_email,
                    "role": "manager",
                    "team": "north",
                    "phone": "+79997776655",
                }
            }
        ],
    }
    commit_headers = {"X-Demo-User": "administrator", "Idempotency-Key": "idemp-add-staff-api-1"}
    resp = client.post("/api/v1/catalogs/organizations/import/commit?import_type=users", json=commit_payload, headers=commit_headers)
    assert resp.status_code == 200, resp.text

    # Confirm user exists before re-seed
    with client.app.state.session_factory() as session:
        created_user = session.query(User).filter(User.keycloak_subject == target_email).first()
        assert created_user is not None
        assert created_user.role == "manager"
        created_user_id = created_user.id

    # Re-run seed_database
    with client.app.state.session_factory() as session:
        seed_database(session)
        session.commit()

    # Verify employee created via API remains intact
    with client.app.state.session_factory() as session:
        preserved_user = session.get(User, created_user_id)
        assert preserved_user is not None, f"Employee {created_user_id} added via API was deleted by seed_database!"
        assert preserved_user.role == "manager"
        assert preserved_user.active is True


def test_lms_json_upload_multipart_file(client: TestClient):
    json_bytes = b'[{"order_id": "LMS-FILE-1", "status": "paid", "amount": 15000}, null]'
    files = {"file": ("payments_export.json", json_bytes, "application/json")}

    resp = client.post("/api/v1/integrations/upload/json", files=files, headers={"X-Demo-User": "supervisor"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_records"] == 2
    assert data["skipped_nulls"] == 1
    assert data["processed_count"] == 1
    assert data["paid_count"] == 1


def test_lms_json_upload_russian_fields_and_standardized_payload(client: TestClient):
    payload = [
        {
            "Номер заявки": "ORD-RUS-999",
            "Курс": "DevOps практики",
            "Фамилия": "Смирнов",
            "Имя": "Алексей",
            "Отчество": "Петрович",
            "Телефон": "+79991234567",
            "Email": "alex.smirnov@example.com",
            "Номер потока": "Поток 2",
            "Организация": "МТУ",
            "Статус оплаты": "Оплачено",
            "Сумма": 25000,
        }
    ]

    resp = client.post("/api/v1/integrations/upload/json", json=payload, headers={"X-Demo-User": "administrator"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["processed"] == 1
    assert data["paid_count"] == 1

    with client.app.state.session_factory() as session:
        inbox_item = session.query(IntegrationInbox).filter(IntegrationInbox.external_id == "ORD-RUS-999").first()
        assert inbox_item is not None
        p = inbox_item.payload
        assert p["representative_name"] == "Смирнов Алексей Петрович"
        assert p["representative_email"] == "alex.smirnov@example.com"
        assert p["representative_phone"] == "+79991234567"
        assert p["course"] == "DevOps практики"
        assert p["cohort"] == "Поток 2"
        assert p["organization_name"] in ("МТУ", "Московский технический университет связи и информатики")


def test_lms_json_upload_zero_values(client: TestClient):
    # Tests that numeric 0 is not dropped to random UUID
    payload = [
        {
            "Номер заявки": 0,
            "Номер потока": 0,
            "Курс": "Тест курс",
            "status": "paid",
            "amount": 1000,
        }
    ]
    resp = client.post("/api/v1/integrations/upload/json", json=payload, headers={"X-Demo-User": "administrator"})
    assert resp.status_code == 200, resp.text

    with client.app.state.session_factory() as session:
        inbox_item = session.query(IntegrationInbox).filter(IntegrationInbox.external_id == "0").first()
        assert inbox_item is not None
        assert inbox_item.source_revision == "0"


def test_admin_dashboard_system_stats_telemetry(client: TestClient):
    # 1. Admin gets system_stats
    resp = client.get("/api/v1/dashboard", headers={"X-Demo-User": "administrator"})
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert "system_stats" in d
    stats = d["system_stats"]
    assert stats["total_users"] > 0
    assert stats["total_organizations_catalog"] > 0
    assert stats["total_programs_catalog"] > 0
    assert stats["total_products_catalog"] > 0
    assert "total_inbox_pending" in stats
    assert stats["lms_health_status"] in ("healthy", "ok")

    # 2. Manager gets NO system_stats
    resp_m = client.get("/api/v1/dashboard", headers={"X-Demo-User": "manager-a"})
    assert resp_m.status_code == 200, resp_m.text
    assert "system_stats" not in resp_m.json()


def test_lms_json_upload_cp1251_and_currency_text(client: TestClient):
    import json
    data = [
        {
            "Номер заявки": "CP1251-01",
            "Курс": "Анализ данных",
            "Фамилия": "Кузнецов",
            "Имя": "Дмитрий",
            "Статус оплаты": "Оплачено",
            "Сумма": "25 000,50 руб.",
        }
    ]
    raw_json_str = json.dumps(data, ensure_ascii=False)
    cp1251_bytes = raw_json_str.encode("cp1251")
    files = {"file": ("payments_cp1251.json", cp1251_bytes, "application/json")}

    resp = client.post("/api/v1/integrations/upload/json", files=files, headers={"X-Demo-User": "supervisor"})
    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert res["processed"] == 1
    assert res["paid_count"] == 1
    assert abs(res["total_paid_amount"] - 25000.5) < 0.01


def test_lms_json_upload_utf16(client: TestClient):
    import json
    data = [
        {
            "Номер заявки": "UTF16-01",
            "Курс": "Информационная безопасность",
            "Фамилия": "Морозов",
            "Имя": "Игорь",
            "Статус оплаты": "Оплачено",
            "Сумма": 45000,
        }
    ]
    raw_json_str = json.dumps(data, ensure_ascii=False)
    utf16_bytes = raw_json_str.encode("utf-16")
    files = {"file": ("payments_utf16.json", utf16_bytes, "application/json")}

    resp = client.post("/api/v1/integrations/upload/json", files=files, headers={"X-Demo-User": "supervisor"})
    assert resp.status_code == 200, resp.text
    res = resp.json()
    assert res["processed"] == 1
    assert res["paid_count"] == 1
    assert res["total_paid_amount"] == 45000.0


def test_lms_json_upload_adversarial_edge_cases(client: TestClient):
    """Adversarial edge cases: empty batch, whitespace/mixed-case course names,
    unmapped fallback without blind [0] errors, and metric single-counting.
    """
    admin_headers = {"X-Demo-User": "administrator"}

    # 1. Empty payload
    resp = client.post("/api/v1/integrations/upload/json", json=[], headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["total_records"] == 0
    assert resp.json()["processed"] == 0

    # 2. Mixed casing, leading/trailing whitespace in course and no matching interaction
    payload = [
        {
            "order_id": "EDGE-001",
            "course": "   Инженерия качества ПО   ",
            "status": "paid",
            "amount": "14 000 руб.",
        },
        {
            "order_id": "EDGE-002",
            "course": "",
            "organization": "",
            "status": "pending",
            "amount": 5000,
        },
    ]
    resp = client.post("/api/v1/integrations/upload/json", json=payload, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["processed"] == 2
    assert data["paid_count"] == 1

    with client.app.state.session_factory() as session:
        # Check that EDGE-001 matched Program "program-qa" despite whitespace
        edge1 = session.query(IntegrationInbox).filter(IntegrationInbox.external_id == "EDGE-001").first()
        assert edge1 is not None
        assert edge1.payload.get("matched_program_id") == "program-qa"

        # Check that EDGE-002 cleanly bound to technical pool
        edge2 = session.query(IntegrationInbox).filter(IntegrationInbox.external_id == "EDGE-002").first()
        assert edge2 is not None
        assert edge2.payload.get("matched_organization_name") == "ИТ Школа Ростелекома (Пул заявок)"
        assert edge2.payload.get("matched_program_name") == "Общий пул программ LMS"

        # Verify no batch total metrics exist
        legacy = session.query(LearningMetric).filter(
            LearningMetric.external_id.in_(["lms-app-batch-total", "lms-pay-batch-total"])
        ).all()
        assert len(legacy) == 0


def test_seed_database_role_casing_and_whitespace_resilience(client: TestClient):
    """Adversarial R1: Verify seed_database preserves staff users whose roles have
    mixed casing, whitespace padding, or 'admin' alias, while purging non-staff roles.
    """
    staff_variations = [
        ("case-staff-1", "case1@rt.ru", "Менеджер Регистр", "Manager"),
        ("case-staff-2", "case2@rt.ru", "Админ Капс", " ADMINISTRATOR "),
        ("case-staff-3", "case3@rt.ru", "Супервизор Пробелы", "  supervisor  "),
        ("case-staff-4", "case4@rt.ru", "Админ Алиас", "admin"),
    ]
    purge_variations = [
        ("purge-user-1", "p1@test.ru", "Пустой Пробел", "   "),
        ("purge-user-2", "p2@test.ru", "Студент Капс", "LEARNER"),
        ("purge-user-3", "p3@test.ru", "Слушатель", "student"),
        ("purge-user-4", "p4@test.ru", "Гость", "guest"),
    ]

    with client.app.state.session_factory() as session:
        for uid, _, _, _ in staff_variations + purge_variations:
            existing = session.get(User, uid)
            if existing:
                session.delete(existing)
        session.commit()

        for uid, email, name, role in staff_variations + purge_variations:
            session.add(User(id=uid, keycloak_subject=email, name=name, role=role, active=True))
        session.commit()

    with client.app.state.session_factory() as session:
        seed_database(session)
        session.commit()

    with client.app.state.session_factory() as session:
        for uid, _, _, _ in staff_variations:
            u = session.get(User, uid)
            assert u is not None, f"Staff variation user {uid} should be preserved across re-seeding!"

        for uid, _, _, _ in purge_variations:
            u = session.get(User, uid)
            assert u is None, f"Non-staff user {uid} should be purged across re-seeding!"


def test_lms_pool_idempotence_and_course_slug_matching(client: TestClient):
    """Adversarial R2: Verify _get_or_create_lms_pool is strictly idempotent and that
    program lookup by slug (e.g. 'devops') matches program-devops.
    """
    from app.integrations.service import _get_or_create_lms_pool

    with client.app.state.session_factory() as session:
        org1, prog1 = _get_or_create_lms_pool(session)
        session.commit()

    with client.app.state.session_factory() as session:
        org2, prog2 = _get_or_create_lms_pool(session)
        assert org1.id == org2.id
        assert prog1.id == prog2.id
        assert org2.name == "ИТ Школа Ростелекома (Пул заявок)"
        assert prog2.name == "Общий пул программ LMS"

    # Test program match via slug "devops"
    admin_headers = {"X-Demo-User": "administrator"}
    resp = client.post(
        "/api/v1/integrations/upload/json",
        json=[{"order_id": "SLUG-001", "course": "devops", "status": "paid", "amount": 10000}],
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    with client.app.state.session_factory() as session:
        item = session.query(IntegrationInbox).filter(IntegrationInbox.external_id == "SLUG-001").first()
        assert item is not None
        assert item.payload.get("matched_program_id") == "program-devops"


def test_seed_database_purges_non_staff_with_organization_access(client: TestClient):
    """Adversarial R1: Verify that a non-staff user with an active OrganizationAccess
    grant is safely purged by seed_database() without Foreign Key constraint violations.
    """
    from app.models import OrganizationAccess

    bad_user_id = "rogue-learner-with-grant"
    with client.app.state.session_factory() as session:
        existing_u = session.get(User, bad_user_id)
        if existing_u:
            for g in session.query(OrganizationAccess).filter(OrganizationAccess.user_id == bad_user_id).all():
                session.delete(g)
            session.delete(existing_u)
            session.commit()

        bad_user = User(
            id=bad_user_id,
            keycloak_subject="rogue.grant@test.ru",
            name="Нештатный Слушатель с Доступом",
            role="learner",
            active=True,
        )
        session.add(bad_user)
        session.flush()

        grant = OrganizationAccess(
            user_id=bad_user_id,
            organization_id="org-1",
            can_create=True,
            read_all=True,
        )
        session.add(grant)
        session.commit()

    # Re-run seed_database
    with client.app.state.session_factory() as session:
        seed_database(session)
        session.commit()

    # Verify both user and its OrganizationAccess grant were cleanly purged
    with client.app.state.session_factory() as session:
        assert session.get(User, bad_user_id) is None
        grants = session.query(OrganizationAccess).filter(OrganizationAccess.user_id == bad_user_id).all()
        assert len(grants) == 0


def test_lms_pool_name_synchronization(client: TestClient):
    """Adversarial R2: Verify _get_or_create_lms_pool repairs names if pool entities
    exist under canonical IDs but with outdated or altered names.
    """
    from app.integrations.service import _get_or_create_lms_pool
    from app.models import Direction, Organization, Program

    with client.app.state.session_factory() as session:
        # Pre-seed or alter canonical IDs with outdated names
        org = session.get(Organization, "org-lms-pool")
        if not org:
            org = Organization(id="org-lms-pool", name="Устаревшее имя пула", type="school")
            session.add(org)
        else:
            org.name = "Устаревшее имя пула"

        prog = session.get(Program, "program-lms-pool")
        if not prog:
            dir_rec = session.query(Direction).first()
            prog = Program(id="program-lms-pool", name="Устаревшая программа пула", direction_id=dir_rec.id)
            session.add(prog)
        else:
            prog.name = "Устаревшая программа пула"
        session.commit()

    # Call _get_or_create_lms_pool
    with client.app.state.session_factory() as session:
        pool_org, pool_prog = _get_or_create_lms_pool(session)
        session.commit()
        assert pool_org.id == "org-lms-pool"
        assert pool_org.name == "ИТ Школа Ростелекома (Пул заявок)"
        assert pool_prog.id == "program-lms-pool"
        assert pool_prog.name == "Общий пул программ LMS"





