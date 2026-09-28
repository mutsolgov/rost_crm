import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from app.models import User, Organization, IntegrationInbox

ORGANIZER_FILE_PATH = Path(__file__).resolve().parents[2] / "данные предоставленные организаторами/Загрузка пользователей.xlsx"

EXPECTED_USERS = [
    {
        "name": "Черепанова Светлана Васильевна",
        "email": "cherepanona.s@test.ru",
        "phone": "79990234365",
        "role": "manager",
    },
    {
        "name": "Кричанов Максим Сергеевич",
        "email": "max_crich@mail.ru",
        "phone": "79977361351",
        "role": "manager",
    },
    {
        "name": "Григорьев Станислав Семенович",
        "email": "grigorev355@gmail.com",
        "phone": "79947392263",
        "role": "manager",
    },
    {
        "name": "Осипенко Ирина Викторовна",
        "email": "osipenko833484@mail.ru",
        "phone": "79934253846",
        "role": "manager",
    },
    {
        "name": "Иванов Михаил Петрович",
        "email": "mp_ivanov@mail.ru",
        "phone": "79924583434",
        "role": "manager",
    },
]

@pytest.fixture
def file_bytes():
    assert ORGANIZER_FILE_PATH.exists(), f"Organizer file missing at {ORGANIZER_FILE_PATH}"
    return ORGANIZER_FILE_PATH.read_bytes()


def test_adversarial_preview_autodetect_both_endpoints(client: TestClient, file_bytes: bytes):
    """Verifies that both preview endpoints auto-detect 'lms_learners' correctly without import_type query param."""
    endpoints = [
        "/api/v1/imports/organizations/preview",
        "/api/v1/catalogs/organizations/import/preview",
    ]
    headers = {"X-Demo-User": "administrator"}

    for ep in endpoints:
        files = {"file": ("Загрузка пользователей.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        resp = client.post(ep, files=files, headers=headers)
        assert resp.status_code == 200, f"Failed on {ep}: {resp.text}"
        data = resp.json()
        assert data.get("detected_type") == "lms_learners", f"Expected 'lms_learners' on {ep}, got {data.get('detected_type')}"
        assert data.get("redirect") == "/integrations"
        assert "Распознан реестр слушателей LMS" in data.get("message", "")
        assert data.get("total_rows") == 5
        assert data.get("valid_count") == 5
        assert data.get("error_count") == 0


def test_adversarial_preview_format_override(client: TestClient, file_bytes: bytes):
    """Verifies query param format override: ?import_type=organizations, ?import_type=vendors, ?import_type=users."""
    headers = {"X-Demo-User": "administrator"}

    # 1. Override to organizations
    files_org = {"file": ("Загрузка пользователей.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp_org = client.post("/api/v1/catalogs/organizations/import/preview?import_type=organizations", files=files_org, headers=headers)
    assert resp_org.status_code == 200, resp_org.text
    data_org = resp_org.json()
    assert data_org.get("detected_type") == "organizations"

    # 2. Override to vendors
    files_ven = {"file": ("Загрузка пользователей.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp_ven = client.post("/api/v1/catalogs/organizations/import/preview?import_type=vendors", files=files_ven, headers=headers)
    assert resp_ven.status_code == 200, resp_ven.text
    data_ven = resp_ven.json()
    assert data_ven.get("detected_type") == "vendors"

    # 3. Explicit override to users
    files_usr = {"file": ("Загрузка пользователей.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp_usr = client.post("/api/v1/catalogs/organizations/import/preview?import_type=users", files=files_usr, headers=headers)
    assert resp_usr.status_code == 200, resp_usr.text
    data_usr = resp_usr.json()
    assert data_usr.get("detected_type") == "users"
    assert data_usr.get("valid_count") == 5


def test_adversarial_commit_idempotency_replay_protection(client: TestClient, file_bytes: bytes):
    """Verifies commit endpoint with Idempotency-Key replay protection and database deduplication."""
    headers = {"X-Demo-User": "administrator"}

    commit_payload = {
        "source_name": "Загрузка пользователей.xlsx",
        "rows": [],
    }
    idempotency_key = "idemp-adv-replay-001"
    commit_headers = dict(headers, **{"Idempotency-Key": idempotency_key})

    # Call 1: Initial commit
    resp1 = client.post("/api/v1/catalogs/organizations/import/commit", json=commit_payload, headers=commit_headers)
    assert resp1.status_code == 200, resp1.text
    data1 = resp1.json()
    assert data1["status"] == "committed"
    assert data1["detected_type"] == "lms_learners"
    assert data1["created_users"] == 0

    # Check DB after Call 1: zero learners in User table
    with client.app.state.session_factory() as session:
        users_after_call1 = session.query(User).filter(
            User.keycloak_subject.in_([u["email"] for u in EXPECTED_USERS])
        ).all()
        assert len(users_after_call1) == 0

    # Call 2: Replay with identical Idempotency-Key and payload
    resp2 = client.post("/api/v1/catalogs/organizations/import/commit", json=commit_payload, headers=commit_headers)
    assert resp2.status_code == 200, resp2.text
    data2 = resp2.json()
    assert data2 == data1, "Replay response must be identical to original response"

    # Verify no duplicates in database after Call 2
    with client.app.state.session_factory() as session:
        users_after_call2 = session.query(User).filter(
            User.keycloak_subject.in_([u["email"] for u in EXPECTED_USERS])
        ).all()
        assert len(users_after_call2) == 0


def test_adversarial_commit_idempotency_conflict_on_mismatched_payload(client: TestClient, file_bytes: bytes):
    """Verifies that reusing the same Idempotency-Key with different payload triggers 409 IDEMPOTENCY_CONFLICT."""
    headers = {"X-Demo-User": "administrator"}

    idempotency_key = "idemp-adv-conflict-002"
    commit_headers = dict(headers, **{"Idempotency-Key": idempotency_key})

    # Call 1: Initial commit
    resp1 = client.post(
        "/api/v1/catalogs/organizations/import/commit",
        json={"source_name": "Загрузка пользователей.xlsx", "rows": [{"name": "item-1"}]},
        headers=commit_headers,
    )
    assert resp1.status_code == 200

    # Call 2: Same Idempotency-Key, modified payload
    resp2 = client.post(
        "/api/v1/catalogs/organizations/import/commit",
        json={"source_name": "Загрузка пользователей.xlsx", "rows": [{"name": "item-2"}]},
        headers=commit_headers,
    )
    assert resp2.status_code == 409, f"Expected 409 IDEMPOTENCY_CONFLICT, got {resp2.status_code}: {resp2.text}"
    err = resp2.json().get("error", {})
    assert err.get("code") == "IDEMPOTENCY_CONFLICT"


def test_adversarial_multipart_direct_commit(client: TestClient, file_bytes: bytes):
    """Verifies direct multipart commit: POST /api/v1/catalogs/organizations/import/commit with file and Idempotency-Key."""
    headers = {"X-Demo-User": "administrator", "Idempotency-Key": "idemp-adv-multipart-003"}
    files = {"file": ("Загрузка пользователей.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}

    resp = client.post("/api/v1/catalogs/organizations/import/commit", files=files, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "committed"
    assert data["detected_type"] == "lms_learners"
    assert data["created_users"] == 0

    # Replay multipart call
    files2 = {"file": ("Загрузка пользователей.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp2 = client.post("/api/v1/catalogs/organizations/import/commit", files=files2, headers=headers)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2 == data


def test_adversarial_db_values_verification(client: TestClient, file_bytes: bytes):
    """Strict verification of domain purity and IntegrationInbox values: 0 learners in User table, all 5 in IntegrationInbox."""
    headers = {"X-Demo-User": "administrator", "Idempotency-Key": "idemp-adv-db-verify-004"}
    files = {"file": ("Загрузка пользователей.xlsx", file_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}

    # First trigger preview (which ingests to IntegrationInbox)
    resp_prev = client.post("/api/v1/catalogs/organizations/import/preview", files=files, headers={"X-Demo-User": "administrator"})
    assert resp_prev.status_code == 200

    resp = client.post("/api/v1/catalogs/organizations/import/commit", files=files, headers=headers)
    assert resp.status_code == 200

    with client.app.state.session_factory() as session:
        for expected in EXPECTED_USERS:
            # 1. Zero learners in User table
            user = session.query(User).filter(User.keycloak_subject == expected["email"]).first()
            assert user is None, f"Learner {expected['email']} must NOT be in User table"

            # 2. IntegrationInbox contains learner
            inbox = session.query(IntegrationInbox).filter(
                IntegrationInbox.source == "lms",
                IntegrationInbox.entity_type == "learner",
                IntegrationInbox.external_id == expected["email"],
            ).first()
            assert inbox is not None, f"Learner {expected['email']} not found in IntegrationInbox"
            p = inbox.payload
            assert p["email"] == expected["email"]
            assert p["full_name"] == expected["name"]
            assert p["phone"] == expected["phone"]
            assert "snils" in p
            assert "passport_number" in p
            assert "education" in p
