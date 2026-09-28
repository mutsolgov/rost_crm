import pytest
import io
import zipfile
import xml.etree.ElementTree as ET
from fastapi.testclient import TestClient

from app.models import User, Organization, Product, Team, OrganizationContact
from app.importer import parse_tabular_file

def make_test_xlsx(rows):
    """Helper to generate a minimal valid xlsx in-memory from list of row lists without openpyxl."""
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
        # Build shared strings
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

        # Build sheet
        sheet_xml = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']
        for r_idx, row in enumerate(rows, 1):
            sheet_xml.append(f'<row r="{r_idx}">')
            for c_idx, cell in enumerate(row, 1):
                col_letter = chr(ord('A') + c_idx - 1)
                ref = f"{col_letter}{r_idx}"
                s_idx = sst_map[str(cell)]
                sheet_xml.append(f'<c r="{ref}" t="s"><v>{s_idx}</v></c>')
            sheet_xml.append('</row>')
        sheet_xml.append('</sheetData></worksheet>')
        z.writestr("xl/worksheets/sheet1.xml", "".join(sheet_xml))

    return bio.getvalue()

def test_parse_vendors_xlsx():
    rows = [
        ["Вендор", "Продукты", "Контактное лицо", "Email", "Телефон", "Сайт"],
        ["ООО Рога и Копыта", "CRM Платформа; Аналитика Pro, Робот v2", "Иван Иванов", "ivan@horns.ru", "+79991112233", "https://horns.ru"],
        ["АО КиберСофт", "Антивирус 360, Файрвол Корп", "Петр Петров", "petr@cybersoft.ru", "+79992223344", "https://cybersoft.ru"]
    ]
    content = make_test_xlsx(rows)
    parsed = parse_tabular_file(content, "Вендоры.xlsx")
    assert len(parsed) == 2
    assert parsed[0]["_file_type"] == "vendors"
    assert parsed[0]["name"] == "ООО Рога и Копыта"
    assert "CRM Платформа" in parsed[0]["products"]
    assert "Аналитика Pro" in parsed[0]["products"]
    assert "Робот v2" in parsed[0]["products"]

def test_vendors_import_preview_and_commit(client: TestClient):
    rows = [
        ["Вендор", "Продукты", "Контактное лицо", "Email", "Телефон", "Сайт"],
        ["ООО ТестВендор Альфа", "Продукт А, Продукт Б", "Алексей Смирнов", "smirnov@alpha.ru", "+79001234567", "https://alpha.ru"]
    ]
    content = make_test_xlsx(rows)
    headers = {"X-Demo-User": "administrator"}
    
    # 1. Preview
    files = {"file": ("Вендоры.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp = client.post("/api/v1/catalogs/organizations/import/preview", files=files, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["detected_type"] == "vendors"
    assert data["valid_count"] == 1
    assert data["rows"][0]["mapped_fields"]["type"] == "vendor"
    assert len(data["rows"][0]["products"]) == 2

    # 2. Commit
    commit_payload = {
        "source_name": "Вендоры.xlsx",
        "rows": [
            {
                "row_number": 2,
                "is_valid": True,
                "errors": [],
                "warnings": [],
                "mapped_fields": data["rows"][0]["mapped_fields"],
                "raw_values": data["rows"][0]["raw_values"],
                "products": data["rows"][0]["products"]
            }
        ]
    }
    commit_headers = dict(headers, **{"Idempotency-Key": "idemp-vendor-1"})
    resp = client.post("/api/v1/catalogs/organizations/import/commit?import_type=vendors", json=commit_payload, headers=commit_headers)
    assert resp.status_code == 200, resp.text
    c_data = resp.json()
    assert c_data["created_vendors"] == 1
    assert c_data["detected_type"] == "vendors"
    assert c_data["details"]["products_created"] == 2

    # Check database
    with client.app.state.session_factory() as session:
        vendor_org = session.query(Organization).filter(Organization.name == "ООО ТестВендор Альфа").first()
        assert vendor_org is not None
        assert vendor_org.type == "vendor"
        contacts = session.query(OrganizationContact).filter(OrganizationContact.organization_id == vendor_org.id).all()
        assert len(contacts) >= 1
        assert contacts[0].full_name == "Алексей Смирнов"

        products = session.query(Product).filter(Product.vendor == vendor_org.name).all()
        p_names = {p.name for p in products}
        assert "Продукт А" in p_names
        assert "Продукт Б" in p_names

def test_users_import_preview_and_commit(client: TestClient):
    rows = [
        ["ФИО", "Email", "Роль", "Команда"],
        ["Тестовый Менеджер", "new_manager@rost_crm.local", "Менеджер", "Команда Продаж Юг"],
        ["Тестовый Руководитель", "new_supervisor@rost_crm.local", "Руководитель", "Команда Продаж Юг"]
    ]
    content = make_test_xlsx(rows)
    headers = {"X-Demo-User": "administrator"}

    # 1. Preview
    files = {"file": ("Загрузка пользователей.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp = client.post("/api/v1/catalogs/organizations/import/preview", files=files, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["detected_type"] == "users"
    assert data["valid_count"] == 2

    # 2. Commit
    commit_payload = {
        "source_name": "Загрузка пользователей.xlsx",
        "rows": data["rows"]
    }
    commit_headers = dict(headers, **{"Idempotency-Key": "idemp-user-1"})
    resp = client.post("/api/v1/catalogs/organizations/import/commit?import_type=users", json=commit_payload, headers=commit_headers)
    assert resp.status_code == 200, resp.text
    c_data = resp.json()
    assert c_data["created_count"] == 2
    assert c_data["detected_type"] == "users"

    # Verify users created
    with client.app.state.session_factory() as session:
        u1 = session.query(User).filter(User.keycloak_subject == "new_manager@rost_crm.local").first()
        assert u1 is not None
        assert u1.role == "manager"
        assert u1.name == "Тестовый Менеджер"

        u2 = session.query(User).filter(User.keycloak_subject == "new_supervisor@rost_crm.local").first()
        assert u2 is not None
        assert u2.role == "supervisor"
        assert u2.team_id == u1.team_id


def test_parse_vendors_multiproduct_newlines_and_delimiters():
    from app.importer import _parse_product_names, _match_header, _detect_file_type
    
    # 1. Newlines and quotes
    p1 = _parse_product_names("«RT.DataLake»\n«RT.Warehouse»")
    assert p1 == ["RT.DataLake", "RT.Warehouse"]

    # 2. Numbered list with semicolons and newlines
    p2 = _parse_product_names("1. Продукт Раз;\n2. Продукт Два;\n3. Продукт Три")
    assert p2 == ["Продукт Раз", "Продукт Два", "Продукт Три"]

    # 3. Compound header "Продукты вендора" must map to product, not vendor
    assert _match_header("Продукты вендора", "vendors") == "product"
    assert _match_header("ИТ-продукты", "vendors") == "product"
    assert _detect_file_type(["Компания", "ИТ-продукты", "Контакты"]) == "vendors"


def test_vendors_compound_header_and_auto_commit(client: TestClient):
    # Tests compound headers and committing without explicit ?import_type= in query string
    rows = [
        ["Вендор", "Продукты вендора", "ФИО представителя", "Email", "Телефон"],
        ["ООО ИнноВендор", "«ИнноБаза», «ИнноШлюз»", "Сергей Сидоров", "sidorov@inno.ru", "+79110001122"]
    ]
    content = make_test_xlsx(rows)
    headers = {"X-Demo-User": "administrator"}

    # 1. Preview
    files = {"file": ("Вендоры.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp = client.post("/api/v1/catalogs/organizations/import/preview", files=files, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["detected_type"] == "vendors"
    assert data["rows"][0]["products"] == ["ИнноБаза", "ИнноШлюз"]

    # 2. Commit WITHOUT ?import_type= in query string
    commit_payload = {
        "rows": [
            {
                "is_valid": True,
                "mapped_fields": data["rows"][0]["mapped_fields"],
                "data": data["rows"][0]["data"],
                "products": data["rows"][0]["products"]
            }
        ]
    }
    commit_headers = dict(headers, **{"Idempotency-Key": "idemp-inno-auto"})
    resp = client.post("/api/v1/imports/commit", json=commit_payload, headers=commit_headers)
    assert resp.status_code == 200, resp.text
    c_data = resp.json()
    assert c_data["detected_type"] == "vendors"
    assert c_data["details"]["products_created"] == 2

    with client.app.state.session_factory() as session:
        v = session.query(Organization).filter(Organization.name == "ООО ИнноВендор").first()
        assert v is not None
        assert v.type == "vendor"
        prods = session.query(Product).filter(Product.vendor == "ООО ИнноВендор").all()
        assert {p.name for p in prods} == {"ИнноБаза", "ИнноШлюз"}


def test_1c_domestic_software_name_preservation():
    from app.importer import _parse_product_names
    # Domestic 1C software must preserve leading 1
    assert _parse_product_names("1С:Предприятие") == ["1С:Предприятие"]
    assert _parse_product_names("1C:ERP") == ["1C:ERP"]
    assert _parse_product_names("1C") == ["1C"]
    # List numbering must still be stripped
    assert _parse_product_names("1. 1C:ERP;\n2. 1С:Предприятие") == ["1C:ERP", "1С:Предприятие"]
    assert _parse_product_names("• Postgres Pro, - МойОфис") == ["Postgres Pro", "МойОфис"]


def test_vendor_contact_and_phone_headers_disambiguation(client: TestClient):
    # Tests that headers with 'представитель' or 'контакт' do not hijack phone/email/product
    from app.importer import _match_header
    assert _match_header("Телефон представителя", "vendors") == "phone"
    assert _match_header("Email представителя", "vendors") == "email"
    assert _match_header("Контактный телефон", "vendors") == "phone"
    assert _match_header("Контактный email", "vendors") == "email"
    assert _match_header("Представитель вендора", "vendors") == "contact_name"
    assert _match_header("Контактное лицо", "vendors") == "contact_name"
    assert _match_header("ПО вендора", "vendors") == "product"
    assert _match_header("Телефон сотрудника", "users") == "phone"
    assert _match_header("Email пользователя", "users") == "email"


def test_vendor_multiline_separate_rows_for_same_vendor(client: TestClient):
    # Vendor with multiple products on separate rows must NOT be rejected as duplicate error
    rows = [
        ["Вендор", "ПО", "Контактное лицо", "Телефон", "Email"],
        ["Группа Астра", "Astra Linux Special Edition", "Иванов И.И.", "+79991112233", "ivanov@astra.ru"],
        ["Группа Астра", "Брест", "Иванов И.И.", "+79991112233", "ivanov@astra.ru"]
    ]
    content = make_test_xlsx(rows)
    headers = {"X-Demo-User": "administrator"}

    # 1. Preview
    files = {"file": ("Вендоры.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp = client.post("/api/v1/catalogs/organizations/import/preview", files=files, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["valid_count"] == 2
    assert data["error_count"] == 0
    assert data["rows"][0]["status"] == "create"
    assert data["rows"][1]["status"] == "update"

    # 2. Commit
    commit_payload = {
        "rows": [
            {
                "is_valid": True,
                "mapped_fields": data["rows"][0]["mapped_fields"],
                "data": data["rows"][0]["data"],
                "products": data["rows"][0]["products"]
            },
            {
                "is_valid": True,
                "mapped_fields": data["rows"][1]["mapped_fields"],
                "data": data["rows"][1]["data"],
                "products": data["rows"][1]["products"]
            }
        ]
    }
    commit_headers = dict(headers, **{"Idempotency-Key": "idemp-astra-multi"})
    resp = client.post("/api/v1/imports/commit?import_type=vendors", json=commit_payload, headers=commit_headers)
    assert resp.status_code == 200, resp.text
    c_data = resp.json()
    assert c_data["details"]["products_created"] == 2

    with client.app.state.session_factory() as session:
        v = session.query(Organization).filter(Organization.name == "Группа Астра").first()
        assert v is not None
        assert v.type == "vendor"
        prods = session.query(Product).filter(Product.vendor == "Группа Астра").all()
        assert {p.name for p in prods} == {"Astra Linux Special Edition", "Брест"}


def test_user_import_email_priority_over_name(client: TestClient):
    # Ensure email matching takes precedence over name collision
    with client.app.state.session_factory() as session:
        # Pre-create User with name "Сергей Васильев" and old email
        u = session.query(User).filter(User.keycloak_subject == "vasiliev_old@rt.ru").first()
        if not u:
            u = User(id="user-vasiliev", keycloak_subject="vasiliev_old@rt.ru", name="Сергей Васильев", role="manager", active=True)
            session.add(u)
            session.commit()

    rows = [
        ["ФИО", "Email", "Роль", "Команда"],
        ["Сергей Васильев", "vasiliev_new@rt.ru", "Менеджер", "Команда Центр"]
    ]
    content = make_test_xlsx(rows)
    headers = {"X-Demo-User": "administrator"}

    files = {"file": ("Загрузка пользователей.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp = client.post("/api/v1/catalogs/organizations/import/preview", files=files, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["detected_type"] == "users"
    assert data["valid_count"] == 1


def test_product_names_parentheses_and_brackets_preservation():
    from app.importer import _parse_product_names
    # Domestic products with parentheses or brackets at the end must keep their closing delimiter
    input_str = "«Astra Linux (Special Edition)», МойОфис [Таблица], 1. 1С:ERP (версия 2.5), (Полностью в скобках)"
    parsed = _parse_product_names(input_str)
    assert parsed == [
        "Astra Linux (Special Edition)",
        "МойОфис [Таблица]",
        "1С:ERP (версия 2.5)",
        "Полностью в скобках",
    ]


def test_vendor_contact_fio_header_mapping():
    from app.importer import _match_header
    assert _match_header("ФИО", file_type="vendors") == "contact_name"
    assert _match_header("Контактное лицо", file_type="vendors") == "contact_name"
    assert _match_header("Лицо для связи", file_type="vendors") == "contact_name"
    assert _match_header("Вендор", file_type="vendors") == "vendor"
    assert _match_header("ПО", file_type="vendors") == "product"


def test_organizer_users_xlsx_file_auto_detection_and_parsing(client: TestClient):
    """Verifies that the real organizers' file 'Загрузка пользователей.xlsx' is auto-detected
    as 'lms_learners' without query parameter 'import_type', redirected to Integrations,
    persisted into IntegrationInbox, and creates exactly 0 user accounts in the CRM User table.
    """
    from pathlib import Path
    from app.models import User, IntegrationInbox
    from app.importer import preview_organizations_import

    # 1. Resolve real file path
    repo_root = Path(__file__).resolve().parent.parent.parent
    real_file_path = repo_root / "данные предоставленные организаторами" / "Загрузка пользователей.xlsx"
    assert real_file_path.exists(), f"Real organizers file not found at {real_file_path}"
    file_bytes = real_file_path.read_bytes()

    headers = {"X-Demo-User": "administrator"}

    # 2. Preview Phase via HTTP endpoint without import_type query parameter
    files = {
        "file": (
            "Загрузка пользователей.xlsx",
            file_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    resp = client.post("/api/v1/catalogs/organizations/import/preview", files=files, headers=headers)
    assert resp.status_code == 200, resp.text
    preview_data = resp.json()

    # Assertions on preview
    assert preview_data["detected_type"] == "lms_learners"
    assert preview_data["redirect"] == "/integrations"
    assert "Распознан реестр слушателей LMS" in preview_data["message"]
    assert preview_data["total_rows"] == 5
    assert preview_data["valid_rows"] == 5
    assert preview_data["valid_count"] == 5
    assert preview_data["error_count"] == 0

    expected_users = [
        {
            "name": "Черепанова Светлана Васильевна",
            "email": "cherepanona.s@test.ru",
            "phone": "79990234365",
        },
        {
            "name": "Кричанов Максим Сергеевич",
            "email": "max_crich@mail.ru",
            "phone": "79977361351",
        },
        {
            "name": "Григорьев Станислав Семенович",
            "email": "grigorev355@gmail.com",
            "phone": "79947392263",
        },
        {
            "name": "Осипенко Ирина Викторовна",
            "email": "osipenko833484@mail.ru",
            "phone": "79934253846",
        },
        {
            "name": "Иванов Михаил Петрович",
            "email": "mp_ivanov@mail.ru",
            "phone": "79924583434",
        },
    ]

    # 3. Direct function verification of preview_organizations_import without import_type
    with client.app.state.session_factory() as session:
        admin_user = session.query(User).filter(User.role == "administrator").first()
        assert admin_user is not None
        direct_preview = preview_organizations_import(
            db=session,
            user=admin_user,
            file_bytes=file_bytes,
            filename="Загрузка пользователей.xlsx",
            import_type=None,
        )
        assert direct_preview["detected_type"] == "lms_learners"
        assert direct_preview["redirect"] == "/integrations"
        assert direct_preview["total_rows"] == 5
        assert direct_preview["valid_rows"] == 5
        assert direct_preview["valid_count"] == 5
        assert direct_preview["error_count"] == 0

    # 4. Commit Phase via HTTP commit endpoint without import_type query parameter
    commit_payload = {
        "source_name": "Загрузка пользователей.xlsx",
        "rows": [],
    }
    commit_headers = dict(headers, **{"Idempotency-Key": "idemp-organizer-users-real-test"})
    commit_resp = client.post("/api/v1/catalogs/organizations/import/commit", json=commit_payload, headers=commit_headers)
    assert commit_resp.status_code == 200, commit_resp.text
    commit_result = commit_resp.json()
    assert commit_result["detected_type"] == "lms_learners"
    assert commit_result["created_users"] == 0
    assert commit_result["created_count"] == 0

    # 5. Database Verification: 0 learners in User table, all 5 in IntegrationInbox
    with client.app.state.session_factory() as session:
        for exp in expected_users:
            db_user = session.query(User).filter(User.keycloak_subject == exp["email"]).first()
            assert db_user is None, f"Learner {exp['email']} must NOT be in User table!"

        learner_inbox_items = session.query(IntegrationInbox).filter(
            IntegrationInbox.source == "lms",
            IntegrationInbox.entity_type == "learner",
        ).all()
        assert len(learner_inbox_items) == 5
        inbox_emails = {it.payload.get("email") for it in learner_inbox_items}
        for exp in expected_users:
            assert exp["email"] in inbox_emails


