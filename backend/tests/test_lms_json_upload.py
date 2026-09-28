import pytest
from fastapi.testclient import TestClient

from app.models import IntegrationInbox, LearningMetric

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

        # Verify LearningMetric aggregation
        metrics = {m.metric_code: m.value for m in session.query(LearningMetric).all()}
        assert metrics.get("applications_count", 0) >= 4
        assert metrics.get("payments_count", 0) >= 2

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


