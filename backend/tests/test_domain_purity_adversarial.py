"""Adversarial Backend & Domain Purity Test Suite (Milestone M1)
Author: Challenger 1 (Adversarial Backend & Domain Purity Challenger)

Empirical stress tests for:
1. Learner separation from CRM User table during preview and commit import under all variations of filenames, headers, and forced parameters.
2. GET /api/v1/catalogs leak prevention under all roles, permissions, rogue user injection, and interaction owner links.
3. seed_database purge mechanism verifying lingering learner accounts cleanup and idempotency.
4. RBAC enforcement: Manager 403 Forbidden across all learner upload and import endpoints vs Supervisor/Administrator access.
"""

import io
import json
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.models import IntegrationInbox, Interaction, Organization, User
from app.seed import seed_database
from app.importer import preview_organizations_import, commit_organizations_import, _detect_file_type, parse_tabular_file


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LEARNERS_FILE = REPO_ROOT / "данные предоставленные организаторами" / "Загрузка пользователей.xlsx"
PAYMENTS_FILE = REPO_ROOT / "данные предоставленные организаторами" / "Данные оплат.json"

KNOWN_LEARNER_IDS = ["cherepanona-s", "max_crich", "grigorev355", "osipenko833484", "mp_ivanov"]
KNOWN_LEARNER_EMAILS = [
    "cherepanona.s@test.ru",
    "max_crich@mail.ru",
    "grigorev355@gmail.com",
    "osipenko833484@mail.ru",
    "mp_ivanov@mail.ru",
]


def make_test_xlsx(rows: list[list]) -> bytes:
    """Helper to generate a minimal valid xlsx in-memory from list of row lists without external deps."""
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedString+xml"/>'
            '</Types>'
        ))
        z.writestr("_rels/.rels", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>'
        ))
        z.writestr("xl/_rels/workbook.xml.rels", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
            '</Relationships>'
        ))
        z.writestr("xl/workbook.xml", (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/></sheets>'
            '</workbook>'
        ))
        sst = []
        sst_map = {}
        for row in rows:
            for cell in row:
                s = str(cell)
                if s not in sst_map:
                    sst_map[s] = len(sst)
                    sst.append(s)

        sst_xml = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{}" uniqueCount="{}">'.format(len(sst), len(sst))]
        for s in sst:
            sst_xml.append(f"<si><t>{s}</t></si>")
        sst_xml.append("</sst>")
        z.writestr("xl/sharedStrings.xml", "".join(sst_xml))

        sheet_xml = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']
        for r_idx, row in enumerate(rows, start=1):
            sheet_xml.append(f'<row r="{r_idx}">')
            for c_idx, cell in enumerate(row, start=1):
                col_letter = chr(64 + c_idx)
                s_idx = sst_map[str(cell)]
                sheet_xml.append(f'<c r="{col_letter}{r_idx}" t="s"><v>{s_idx}</v></c>')
            sheet_xml.append('</row>')
        sheet_xml.append('</sheetData></worksheet>')
        z.writestr("xl/worksheets/sheet1.xml", "".join(sheet_xml))
    return bio.getvalue()


def make_test_csv(rows: list[list], delimiter: str = ",", encoding: str = "utf-8", bom: bool = False) -> bytes:
    """Helper to generate a CSV in-memory with optional BOM and delimiter."""
    output = io.StringIO()
    for row in rows:
        escaped = [f'"{str(val)}"' if (delimiter in str(val) or "\n" in str(val) or '"' in str(val)) else str(val) for val in row]
        output.write(delimiter.join(escaped) + "\n")
    raw = output.getvalue().encode(encoding)
    if bom and encoding == "utf-8":
        return b"\xef\xbb\xbf" + raw
    return raw


@pytest.fixture
def real_learners_bytes():
    assert LEARNERS_FILE.exists(), f"Missing {LEARNERS_FILE}"
    return LEARNERS_FILE.read_bytes()


# ==============================================================================
# SECTION 1: Adversarial Learner Creation via Import (Filenames & Headers Variations)
# ==============================================================================

@pytest.mark.parametrize("adversarial_filename", [
    "Загрузка пользователей.xlsx",
    "users.xlsx",
    "users.csv",
    "crm_operators.xlsx",
    "сотрудники_ртк.xlsx",
    "staff_directory.xlsx",
    "organizations.xlsx",
    "vendors.xlsx",
    "learners.csv",
    "random_data_dump.xlsx",
    "unknown_file.bin",
    "",
])
def test_adversarial_real_file_with_various_filenames_never_creates_users(
    client: TestClient,
    real_learners_bytes: bytes,
    adversarial_filename: str,
):
    """Stress test: Renaming the real learners file to any filename (users.xlsx, staff, etc.)
    MUST NOT trick preview_organizations_import into creating User accounts in DB.
    """
    admin_headers = {"X-Demo-User": "administrator"}
    fname = adversarial_filename if adversarial_filename else "unnamed.xlsx"
    files = {"file": (fname, real_learners_bytes, "application/octet-stream")}

    resp = client.post("/api/v1/catalogs/organizations/import/preview", files=files, headers=admin_headers)
    assert resp.status_code == 200, f"Failed on filename {adversarial_filename}: {resp.text}"
    body = resp.json()

    assert body["detected_type"] == "lms_learners"
    assert body["redirect"] == "/integrations"
    assert body["users_created"] == 0
    assert len(body.get("preview_rows", [])) == 0

    # Verify zero users in DB with learner emails or IDs
    with client.app.state.session_factory() as session:
        for email in KNOWN_LEARNER_EMAILS:
            u = session.query(User).filter(User.keycloak_subject == email).first()
            assert u is None, f"Learner {email} was created in User table under filename {adversarial_filename}!"
        for lid in KNOWN_LEARNER_IDS:
            u = session.query(User).filter(User.id == lid).first()
            assert u is None, f"Learner ID {lid} was created in User table under filename {adversarial_filename}!"


@pytest.mark.parametrize("header_variant,headers,sample_row", [
    (
        "snils_only",
        ["Фамилия", "Имя", "Email", "Телефон", "СНИЛС"],
        ["Иванов", "Иван", "ivanov_snils@test.ru", "79991112233", "123-456-789 00"],
    ),
    (
        "passport_series_only",
        ["ФИО", "Почта", "Телефон", "Серия паспорта", "Номер паспорта"],
        ["Петров Петр", "petrov_pass@test.ru", "79992223344", "4510", "123456"],
    ),
    (
        "birth_date_only",
        ["Фамилия", "Имя", "Отчество", "Email", "Дата рождения"],
        ["Сидоров", "Сидор", "Сидорович", "sidorov_bday@test.ru", "15.05.1995"],
    ),
    (
        "diploma_only",
        ["ФИО", "Email", "Номер телефона", "Вуз по диплому", "Номер диплома"],
        ["Кузнецов К.К.", "kuznetsov_dip@test.ru", "79993334455", "МГУ", "ДИП-998877"],
    ),
    (
        "registration_address_only",
        ["ФИО", "Email", "Телефон", "Адрес регистрации", "Регион"],
        ["Смирнов А.А.", "smirnov_addr@test.ru", "79994445566", "г. Москва, ул. Ленина", "Москва"],
    ),
    (
        "profession_only",
        ["ФИО", "Email", "Телефон", "Профессия"],
        ["Попов П.П.", "popov_prof@test.ru", "79995556677", "Тестировщик"],
    ),
    (
        "dative_case_only",
        ["ФИО", "Email", "Телефон", "ФИО (в дательном падеже)"],
        ["Васильев В.В.", "vasiliev_dat@test.ru", "79996667788", "Васильеву Василию"],
    ),
    (
        "uppercase_mixed_case",
        ["ФАМИЛИЯ", "ИМЯ", "EMAIL", "СНИЛС", "ПАСПОРТ"],
        ["Гришин", "Григорий", "grishin_up@test.ru", "999-888-777 66", "4500 112233"],
    ),
])
def test_adversarial_header_variations_detected_as_learners(
    client: TestClient,
    header_variant: str,
    headers: list[str],
    sample_row: list[str],
):
    """Stress test: Any tabular file containing learner document/identity markers (even if disguised as users.xlsx)
    MUST be classified as lms_learners and NEVER create users in CRM User table.
    """
    admin_headers = {"X-Demo-User": "administrator"}
    xlsx_bytes = make_test_xlsx([headers, sample_row])

    # Upload with adversarial filename users.xlsx
    files = {"file": ("users.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp = client.post("/api/v1/catalogs/organizations/import/preview", files=files, headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()

    assert body["detected_type"] == "lms_learners", f"Failed for {header_variant}: detected {body.get('detected_type')}"
    assert body["redirect"] == "/integrations"
    assert body["users_created"] == 0

    # Ensure learner was ingested into IntegrationInbox and NOT into User table
    test_email = next(x for x in sample_row if "@" in str(x))
    with client.app.state.session_factory() as session:
        inbox_item = session.query(IntegrationInbox).filter(
            IntegrationInbox.source == "lms",
            IntegrationInbox.entity_type == "learner",
            IntegrationInbox.external_id == test_email.lower(),
        ).first()
        assert inbox_item is not None, f"Expected IntegrationInbox record for {test_email}"

        user_item = session.query(User).filter(User.keycloak_subject == test_email.lower()).first()
        assert user_item is None, f"Learner {test_email} leaked into User table!"


@pytest.mark.parametrize("delimiter,bom", [(",", True), (";", False), ("\t", False)])
def test_adversarial_csv_delimiters_and_bom_detected_as_learners(
    client: TestClient,
    delimiter: str,
    bom: bool,
):
    """Stress test: CSV files with UTF-8 BOM, semicolons, or tabs containing learner markers
    must be correctly identified as lms_learners without leaking to User table.
    """
    admin_headers = {"X-Demo-User": "administrator"}
    headers = ["Фамилия", "Имя", "Email", "Телефон", "СНИЛС"]
    row = ["Тестов", "Тест", f"test_csv_{delimiter}_{bom}@test.ru", "79998887766", "111-222-333 44"]
    csv_bytes = make_test_csv([headers, row], delimiter=delimiter, bom=bom)

    files = {"file": ("learners_export.csv", csv_bytes, "text/csv")}
    resp = client.post("/api/v1/catalogs/organizations/import/preview", files=files, headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["detected_type"] == "lms_learners"
    assert body["users_created"] == 0


def test_commit_organizations_import_with_learner_rows_creates_zero_users(client: TestClient):
    """Stress test: If commit_organizations_import is called with learner rows and import_type='lms_learners',
    it must return 0 created users and 0 updated users.
    """
    admin_headers = {
        "X-Demo-User": "administrator",
        "Idempotency-Key": "test-commit-learners-idemp-1",
    }
    payload = {
        "import_type": "lms_learners",
        "rows": [
            {
                "full_name": "Черепанова Светлана Васильевна",
                "email": "cherepanona.s@test.ru",
                "snils": "111-222-333 44",
                "passport_series": "4510",
                "passport_number": "123456",
            }
        ]
    }
    resp = client.post("/api/v1/catalogs/organizations/import/commit", json=payload, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    res = resp.json()

    assert res["created_users"] == 0
    assert res["updated_users"] == 0
    assert res["import_type"] == "lms_learners"

    with client.app.state.session_factory() as session:
        u = session.query(User).filter(User.keycloak_subject == "cherepanona.s@test.ru").first()
        assert u is None, "Learner must not exist in User table!"


def test_commit_organizations_import_detects_learner_markers_even_without_import_type(client: TestClient):
    """Stress test: If commit is called without specifying import_type, but first row has snils/passport markers,
    it must auto-detect lms_learners and create 0 users.
    """
    admin_headers = {
        "X-Demo-User": "administrator",
        "Idempotency-Key": "test-commit-learners-idemp-2",
    }
    payload = {
        "rows": [
            {
                "full_name": "Кричанов Максим Сергеевич",
                "email": "max_crich@mail.ru",
                "snils": "999-888-777 66",
            }
        ]
    }
    resp = client.post("/api/v1/catalogs/organizations/import/commit", json=payload, headers=admin_headers)
    assert resp.status_code == 200
    res = resp.json()
    assert res["created_users"] == 0
    assert res["import_type"] == "lms_learners"

    with client.app.state.session_factory() as session:
        u = session.query(User).filter(User.keycloak_subject == "max_crich@mail.ru").first()
        assert u is None, "Learner must not be added to User table!"


# ==============================================================================
# SECTION 2: Catalogs Owners Isolation & Leak Prevention
# ==============================================================================

@pytest.mark.parametrize("caller_user", ["administrator", "supervisor", "manager-a", "manager-b"])
def test_catalogs_owners_never_contains_learners_under_any_caller(client: TestClient, caller_user: str):
    """R1.2: GET /api/v1/catalogs must NEVER leak any learner into `owners`, regardless of caller role."""
    headers = {"X-Demo-User": caller_user}
    resp = client.get("/api/v1/catalogs", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    owners = data["owners"]

    for o in owners:
        assert o["id"] not in KNOWN_LEARNER_IDS, f"Leaked learner ID {o['id']} in catalogs for {caller_user}"
        assert o["role"] in ("manager", "supervisor", "administrator"), f"Invalid owner role {o['role']}"


def test_catalogs_owners_filters_out_rogue_learner_with_manager_role(client: TestClient):
    """Stress test: If a rogue learner user was inserted into DB with role='manager',
    GET /api/v1/catalogs MUST still exclude them via learner_ids filter.
    """
    with client.app.state.session_factory() as session:
        rogue_user = User(
            id="cherepanona-s",
            keycloak_subject="cherepanona.s@test.ru",
            name="Черепанова Светлана Васильевна",
            role="manager",
            team_id="north",
            active=True,
        )
        session.add(rogue_user)
        session.commit()

    resp = client.get("/api/v1/catalogs", headers={"X-Demo-User": "administrator"})
    assert resp.status_code == 200
    owners = resp.json()["owners"]

    owner_ids = [o["id"] for o in owners]
    assert "cherepanona-s" not in owner_ids, "Rogue learner cherepanona-s was NOT filtered out of catalogs.owners!"


def test_catalogs_owners_filters_out_user_with_learner_role(client: TestClient):
    """Stress test: If a user exists in DB with role='learner' or role='student',
    GET /api/v1/catalogs MUST exclude them because valid_roles is manager/supervisor/administrator.
    """
    with client.app.state.session_factory() as session:
        student_user = User(
            id="random-student-99",
            keycloak_subject="student99@test.ru",
            name="Студент Случайный",
            role="learner",
            active=True,
        )
        session.add(student_user)
        session.commit()

    resp = client.get("/api/v1/catalogs", headers={"X-Demo-User": "administrator"})
    assert resp.status_code == 200
    owners = resp.json()["owners"]

    owner_ids = [o["id"] for o in owners]
    assert "random-student-99" not in owner_ids, "User with role 'learner' was leaked in catalogs.owners!"


def test_catalogs_owners_filters_out_learner_even_if_assigned_as_interaction_owner(client: TestClient):
    """Stress test: Even if an interaction is owned by a learner ID, catalogs.owners
    MUST NOT include that learner ID.
    """
    with client.app.state.session_factory() as session:
        rogue_user = User(
            id="mp_ivanov",
            keycloak_subject="mp_ivanov@mail.ru",
            name="Иванов Михаил Петрович",
            role="manager",
            team_id="north",
            active=True,
        )
        session.add(rogue_user)
        session.flush()

        ix = session.get(Interaction, "ix-1")
        if ix:
            ix.owner_id = "mp_ivanov"
        session.commit()

    resp = client.get("/api/v1/catalogs", headers={"X-Demo-User": "administrator"})
    assert resp.status_code == 200
    owners = resp.json()["owners"]

    owner_ids = [o["id"] for o in owners]
    assert "mp_ivanov" not in owner_ids, "mp_ivanov leaked into catalogs.owners via interaction ownership!"


# ==============================================================================
# SECTION 3: seed_database Cleanout & Idempotency
# ==============================================================================

def test_seed_database_purges_all_lingering_learner_accounts(client: TestClient):
    """R1.1: seed_database must purge all legacy/mistaken learner records from User table
    by both learner_ids and learner_emails.
    """
    # 1. Inject rogue learner accounts into the database
    with client.app.state.session_factory() as session:
        for lid, lemail in zip(KNOWN_LEARNER_IDS, KNOWN_LEARNER_EMAILS):
            existing = session.get(User, lid)
            if not existing:
                session.add(User(
                    id=lid,
                    keycloak_subject=lemail,
                    name=f"Learner {lid}",
                    role="manager",
                    active=True,
                ))
        session.commit()

    # Verify they were inserted
    with client.app.state.session_factory() as session:
        count = session.query(User).filter(User.id.in_(KNOWN_LEARNER_IDS)).count()
        assert count == len(KNOWN_LEARNER_IDS), "Setup failed to inject rogue learners"

    # 2. Run seed_database
    with client.app.state.session_factory() as session:
        seed_database(session)
        session.commit()

    # 3. Verify ALL lingering learners are purged
    with client.app.state.session_factory() as session:
        for lid in KNOWN_LEARNER_IDS:
            u = session.get(User, lid)
            assert u is None, f"Learner {lid} was NOT purged by seed_database!"
        for lemail in KNOWN_LEARNER_EMAILS:
            u = session.query(User).filter(User.keycloak_subject == lemail).first()
            assert u is None, f"Learner email {lemail} was NOT purged by seed_database!"

        # Ensure genuine staff are intact
        for staff_id in ["manager-a", "manager-b", "supervisor", "administrator"]:
            staff = session.get(User, staff_id)
            assert staff is not None, f"Genuine staff {staff_id} was mistakenly removed!"
            assert staff.active is True


def test_seed_database_idempotent_multiple_runs(client: TestClient):
    """Verify seed_database can be called repeatedly without errors or corrupting state."""
    with client.app.state.session_factory() as session:
        seed_database(session)
        session.commit()
        seed_database(session)
        session.commit()

        users = session.query(User).all()
        user_ids = {u.id for u in users}
        assert "manager-a" in user_ids
        assert "manager-b" in user_ids
        assert "supervisor" in user_ids
        assert "administrator" in user_ids
        assert not any(lid in user_ids for lid in KNOWN_LEARNER_IDS)


# ==============================================================================
# SECTION 4: RBAC Enforcement
# ==============================================================================

def test_rbac_manager_forbidden_to_upload_learners(client: TestClient, real_learners_bytes: bytes):
    """R2.3: POST /api/v1/integrations/upload/learners MUST reject manager role with 403 Forbidden."""
    manager_headers = {"X-Demo-User": "manager-a"}
    files = {
        "file": (
            "Загрузка пользователей.xlsx",
            real_learners_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    resp = client.post("/api/v1/integrations/upload/learners", files=files, headers=manager_headers)
    assert resp.status_code == 403, f"Expected 403 Forbidden for manager, got {resp.status_code}: {resp.text}"
    err = resp.json().get("error", {})
    assert err.get("code") == "FORBIDDEN"


def test_rbac_manager_forbidden_to_upload_lms_payments_json(client: TestClient):
    """POST /api/v1/integrations/upload/json MUST reject manager role with 403 Forbidden."""
    manager_headers = {"X-Demo-User": "manager-a"}
    resp = client.post("/api/v1/integrations/upload/json", json=[], headers=manager_headers)
    assert resp.status_code == 403
    assert resp.json().get("error", {}).get("code") == "FORBIDDEN"


def test_rbac_manager_forbidden_to_import_via_catalogs_modal(client: TestClient, real_learners_bytes: bytes):
    """Manager does not have 'organizations.create' permission, so preview/commit in catalogs must return 403."""
    manager_headers = {"X-Demo-User": "manager-a"}
    files = {
        "file": (
            "Загрузка пользователей.xlsx",
            real_learners_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    resp = client.post("/api/v1/catalogs/organizations/import/preview", files=files, headers=manager_headers)
    assert resp.status_code == 403
    assert resp.json().get("error", {}).get("code") == "FORBIDDEN"


def test_rbac_supervisor_and_administrator_allowed_to_upload_learners(client: TestClient, real_learners_bytes: bytes):
    """Supervisor and Administrator roles MUST be permitted to upload learners (200 OK)."""
    for role in ["supervisor", "administrator"]:
        headers = {"X-Demo-User": role}
        files = {
            "file": (
                "Загрузка пользователей.xlsx",
                real_learners_bytes,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        }
        resp = client.post("/api/v1/integrations/upload/learners", files=files, headers=headers)
        assert resp.status_code == 200, f"Role {role} failed to upload learners: {resp.text}"
        assert resp.json()["status"] == "success"
