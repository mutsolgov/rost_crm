import io
import zipfile
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import Contract, Organization, OrganizationContact


def headers(user="supervisor", key=None):
    res = {"X-Demo-User": user}
    if key:
        res["Idempotency-Key"] = key
    return res


def make_test_xlsx(rows: list[list[str]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""",
        )
        zf.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        )
        zf.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
        )

        lines = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>',
        ]
        for r_idx, row in enumerate(rows, start=1):
            lines.append(f'<row r="{r_idx}">')
            for c_idx, val in enumerate(row):
                col_letter = chr(ord("A") + c_idx)
                lines.append(f'<c r="{col_letter}{r_idx}" t="inlineStr"><is><t>{val}</t></is></c>')
            lines.append("</row>")
        lines.extend(["</sheetData></worksheet>"])
        zf.writestr("xl/worksheets/sheet1.xml", "\n".join(lines))
    return buf.getvalue()


def test_csv_preview_dry_run_and_commit(client, app):
    csv_content = (
        "Название вуза;Тип;Контактное лицо;Email;Телефон;Договор\n"
        "Тестовый Университет Альфа;university;Иванов Иван;ivanov@alpha.edu;+79991112233;ДОГ-АЛЬФА-01\n"
        "Тестовый Институт Бета;university;Петров Петр;petrov@beta.edu;+79992223344;ДОГ-БЕТА-02\n"
    ).encode("utf-8")

    # Phase 1: Preview
    prev_resp = client.post(
        "/api/v1/imports/organizations/preview",
        files={"file": ("import.csv", csv_content)},
        headers=headers("supervisor"),
    )
    assert prev_resp.status_code == 200, prev_resp.text
    prev_data = prev_resp.json()
    assert prev_data["rows_total"] == 2
    assert prev_data["valid_count"] == 2
    assert prev_data["error_count"] == 0
    assert len(prev_data["preview_rows"]) == 2

    # Verify dry-run invariant: no DB changes occurred yet!
    with app.state.session_factory() as session:
        org_a = session.scalar(select(Organization).where(Organization.name == "Тестовый Университет Альфа"))
        assert org_a is None

    # Phase 2: Commit
    commit_key = str(uuid4())
    commit_payload = {"rows": [r["data"] for r in prev_data["preview_rows"]]}
    commit_resp = client.post(
        "/api/v1/imports/organizations/commit",
        json=commit_payload,
        headers=headers("supervisor", commit_key),
    )
    assert commit_resp.status_code == 200, commit_resp.text
    c_data = commit_resp.json()
    assert c_data["status"] == "committed"
    assert c_data["created_organizations"] == 2
    assert c_data["created_contacts"] == 2
    assert c_data["created_contracts"] == 2

    # Verify DB persistence
    with app.state.session_factory() as session:
        org = session.scalar(select(Organization).where(Organization.name == "Тестовый Университет Альфа"))
        assert org is not None
        contact = session.scalar(select(OrganizationContact).where(OrganizationContact.organization_id == org.id))
        assert contact is not None
        assert contact.full_name == "Иванов Иван"
        contract = session.scalar(select(Contract).where(Contract.organization_id == org.id))
        assert contract is not None
        assert contract.number == "ДОГ-АЛЬФА-01"

    # Verify Idempotency replay
    replay_resp = client.post(
        "/api/v1/imports/organizations/commit",
        json=commit_payload,
        headers=headers("supervisor", commit_key),
    )
    assert replay_resp.status_code == 200
    assert replay_resp.json() == c_data

    # Verify Idempotency conflict on modified payload
    conflict_resp = client.post(
        "/api/v1/imports/organizations/commit",
        json={"rows": []},
        headers=headers("supervisor", commit_key),
    )
    assert conflict_resp.status_code == 409
    assert conflict_resp.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_xlsx_preview_and_error_handling(client):
    rows = [
        ["Название вуза", "Тип", "Контактное лицо", "Договор"],
        ["Университет Гамма", "university", "Сидоров С.", "ДОГ-ГАММА"],
        ["", "university", "Без имени", "ДОГ-ERR"],  # Missing name
        ["Университет Гамма", "university", "Дубль", "ДОГ-DUP"],  # Duplicate name
    ]
    xlsx_bytes = make_test_xlsx(rows)

    resp = client.post(
        "/api/v1/imports/organizations/preview",
        files={"file": ("import.xlsx", xlsx_bytes)},
        headers=headers("supervisor"),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["rows_total"] == 3
    assert data["valid_count"] == 1
    assert data["error_count"] == 2
    assert len(data["errors"]) >= 2


def test_import_existing_organization_updates_and_adds_contracts(client, app):
    """When an organization exists in the DB, preview sets status='update' and commit updates without creating duplicate orgs."""
    csv_content = (
        "Название вуза;Тип;Контактное лицо;Email;Телефон;Договор\n"
        "Московский технический университет;university;Новый Представитель;new@mtu.ru;+79998887766;ДОГ-МТУ-NEW\n"
    ).encode("utf-8")

    prev_resp = client.post(
        "/api/v1/imports/organizations/preview",
        files={"file": ("update.csv", csv_content)},
        headers=headers("supervisor"),
    )
    assert prev_resp.status_code == 200, prev_resp.text
    prev_data = prev_resp.json()
    assert prev_data["rows_total"] == 1
    assert prev_data["valid_count"] == 1
    assert prev_data["error_count"] == 0
    assert prev_data["preview_rows"][0]["status"] == "update"

    commit_payload = {"rows": [r["data"] for r in prev_data["preview_rows"]]}
    commit_resp = client.post(
        "/api/v1/imports/organizations/commit",
        json=commit_payload,
        headers=headers("supervisor", str(uuid4())),
    )
    assert commit_resp.status_code == 200, commit_resp.text
    c_data = commit_resp.json()
    assert c_data["status"] == "committed"
    assert c_data["created_organizations"] == 0
    assert c_data["updated_organizations"] == 1
    assert c_data["created_contacts"] == 1
    assert c_data["created_contracts"] == 1

    # Verify no duplicate organization was inserted
    with app.state.session_factory() as session:
        orgs = list(
            session.scalars(
                select(Organization).where(
                    Organization.name == "Московский технический университет"
                )
            )
        )
        assert len(orgs) == 1
        new_contract = session.scalar(
            select(Contract).where(Contract.number == "ДОГ-МТУ-NEW")
        )
        assert new_contract is not None
        assert new_contract.organization_id == orgs[0].id


def test_import_incompatible_program_product_flagged(client):
    """Preview detects and flags incompatibility between program and product."""
    csv_content = (
        "Название вуза;Тип;Программа;Продукт\n"
        "Университет Дельта;university;DevOps и облачные технологии;Среда тестирования\n"
    ).encode("utf-8")

    prev_resp = client.post(
        "/api/v1/imports/organizations/preview",
        files={"file": ("incompatible.csv", csv_content)},
        headers=headers("supervisor"),
    )
    assert prev_resp.status_code == 200, prev_resp.text
    prev_data = prev_resp.json()
    assert prev_data["rows_total"] == 1
    assert prev_data["valid_count"] == 0
    assert prev_data["error_count"] == 1
    assert not prev_data["preview_rows"][0]["is_valid"]
    assert any("не связаны" in err["message"] or "не совместима" in err["message"] for err in prev_data["errors"])


def test_import_commit_multipart_form_data(client):
    """Verifies that commit endpoint accepts multipart/form-data directly as sent by the UI."""
    csv_content = (
        "Название вуза;Тип;Контактное лицо\n"
        "Санкт-Петербургский Политех;university;Петров П.\n"
    ).encode("utf-8")

    commit_resp = client.post(
        "/api/v1/imports/organizations/commit",
        files={"file": ("polytech.csv", csv_content)},
        headers=headers("supervisor", str(uuid4())),
    )
    assert commit_resp.status_code == 200, commit_resp.text
    commit_data = commit_resp.json()
    assert commit_data["status"] == "committed"
    assert commit_data["created_organizations"] == 1



