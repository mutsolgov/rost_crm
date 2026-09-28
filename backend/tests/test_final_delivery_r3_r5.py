import io
import zipfile
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import BackgroundJob, Organization, User, WorkflowVersion, utcnow
from app.services import bump_authz_epoch, process_background_job


def headers(user="supervisor", key=None):
    res = {"X-Demo-User": user}
    if key:
        res["Idempotency-Key"] = key
    return res


def test_job_download_lifecycle_and_security(client, app):
    # 1. Enqueue job as manager-a
    req_body = {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "knowledge_cutoff": datetime.now(timezone.utc).isoformat(),
    }
    resp = client.post("/api/v1/jobs/reports/snapshot", json=req_body, headers=headers("manager-a"))
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]

    # 2. Before completion: download returns 409 JOB_NOT_READY
    dl_early = client.get(f"/api/v1/jobs/{job_id}/download?format=xlsx", headers=headers("manager-a"))
    assert dl_early.status_code == 409
    assert dl_early.json()["error"]["code"] == "JOB_NOT_READY"

    # 3. 152-FZ isolation: other manager receives 404
    dl_other = client.get(f"/api/v1/jobs/{job_id}/download?format=xlsx", headers=headers("manager-b"))
    assert dl_other.status_code == 404
    assert dl_other.json()["error"]["code"] == "NOT_FOUND"

    # 4. Invalid format returns 422
    dl_inv = client.get(f"/api/v1/jobs/{job_id}/download?format=exe", headers=headers("manager-a"))
    assert dl_inv.status_code == 422
    assert dl_inv.json()["error"]["code"] == "VALIDATION_ERROR"

    # 5. Process job in DB
    with app.state.session_factory() as session:
        job = process_background_job(session, job_id)
        assert job.status == "completed"

    # 6. Completed download for all formats
    # XLSX
    dl_xlsx = client.get(f"/api/v1/jobs/{job_id}/download?format=xlsx", headers=headers("manager-a"))
    assert dl_xlsx.status_code == 200
    assert dl_xlsx.headers["X-Report-Format"] == "xlsx"
    assert "attachment" in dl_xlsx.headers["Content-Disposition"]
    assert dl_xlsx.content.startswith(b"PK\x03\x04")

    # PDF
    dl_pdf = client.get(f"/api/v1/jobs/{job_id}/download?format=pdf", headers=headers("manager-a"))
    assert dl_pdf.status_code == 200
    assert dl_pdf.headers["X-Report-Format"] == "pdf"
    assert dl_pdf.content.startswith(b"%PDF-1.4")
    assert b"%%EOF" in dl_pdf.content

    # CSV
    dl_csv = client.get(f"/api/v1/jobs/{job_id}/download?format=csv", headers=headers("manager-a"))
    assert dl_csv.status_code == 200
    assert dl_csv.headers["X-Report-Format"] == "csv"

    # JSON
    dl_json = client.get(f"/api/v1/jobs/{job_id}/download?format=json", headers=headers("manager-a"))
    assert dl_json.status_code == 200
    assert dl_json.headers["X-Report-Format"] == "json"
    assert "rows" in dl_json.json()

    # 7. 152-FZ scope invalidation on authz epoch bump: returns 403 REPORT_SCOPE_CHANGED
    with app.state.session_factory() as session:
        bump_authz_epoch(session)
        session.commit()

    dl_after_epoch = client.get(f"/api/v1/jobs/{job_id}/download?format=xlsx", headers=headers("manager-a"))
    assert dl_after_epoch.status_code == 403
    assert dl_after_epoch.json()["error"]["code"] == "REPORT_SCOPE_CHANGED"


def test_organization_patch_and_owner_assignment(client, app):
    # Set manager-b to a different team 'south' to test team boundary enforcement
    with app.state.session_factory() as session:
        mb = session.get(User, "manager-b")
        if mb:
            mb.team_id = "south"
            session.commit()

    # 1. Manager cannot assign organization owner (403)
    resp_mgr = client.patch(
        "/api/v1/organizations/org-1",
        json={"owner_id": "manager-a"},
        headers=headers("manager-a"),
    )
    assert resp_mgr.status_code == 403
    assert resp_mgr.json()["error"]["code"] == "FORBIDDEN"

    # 2. Supervisor assigns manager-a (same team) -> 200
    resp_sup = client.patch(
        "/api/v1/organizations/org-1",
        json={"owner_id": "manager-a"},
        headers=headers("supervisor"),
    )
    assert resp_sup.status_code == 200
    data = resp_sup.json()
    assert data["id"] == "org-1"
    assert data["owner_id"] == "manager-a"

    # Verify catalog contains owner_id
    cat_resp = client.get("/api/v1/catalogs", headers=headers("supervisor"))
    assert cat_resp.status_code == 200
    orgs = cat_resp.json()["organizations"]
    org_1 = next(o for o in orgs if o["id"] == "org-1")
    assert org_1["owner_id"] == "manager-a"

    # 3. Supervisor cannot assign manager from another team (manager-b in team 'south', supervisor in 'north')
    resp_cross = client.patch(
        "/api/v1/organizations/org-1",
        json={"owner_id": "manager-b"},
        headers=headers("supervisor"),
    )
    assert resp_cross.status_code == 403
    assert resp_cross.json()["error"]["code"] == "FORBIDDEN"

    # 4. Administrator can assign any manager across teams
    resp_admin = client.patch(
        "/api/v1/organizations/org-1",
        json={"owner_id": "manager-b"},
        headers=headers("administrator"),
    )
    assert resp_admin.status_code == 200
    assert resp_admin.json()["owner_id"] == "manager-b"

    # Verify administrator catalogs contains all active managers
    cat_admin_resp = client.get("/api/v1/catalogs", headers=headers("administrator"))
    assert cat_admin_resp.status_code == 200
    admin_owners = cat_admin_resp.json()["owners"]
    admin_owner_ids = {o["id"] for o in admin_owners}
    assert "manager-a" in admin_owner_ids
    assert "manager-b" in admin_owner_ids

    # 5. Unassign owner (owner_id = None)
    resp_unassign = client.patch(
        "/api/v1/organizations/org-1",
        json={"owner_id": None},
        headers=headers("supervisor"),
    )
    assert resp_unassign.status_code == 200
    assert resp_unassign.json()["owner_id"] is None

    # 6. Assign non-existent user returns 422
    resp_bad_user = client.patch(
        "/api/v1/organizations/org-1",
        json={"owner_id": "non-existent-user"},
        headers=headers("supervisor"),
    )
    assert resp_bad_user.status_code == 422
    assert resp_bad_user.json()["error"]["code"] == "VALIDATION_ERROR"

    # 7. Non-existent organization returns 404
    resp_bad_org = client.patch(
        "/api/v1/organizations/non-existent-org",
        json={"owner_id": "manager-a"},
        headers=headers("supervisor"),
    )
    assert resp_bad_org.status_code == 404
    assert resp_bad_org.json()["error"]["code"] == "NOT_FOUND"


def test_dynamic_workflow_versions_endpoints(client, app):
    from app.workflow import WORKFLOW_REGISTRY
    try:
        # 1. List workflow versions (initially empty or seeded)
        resp_list = client.get("/api/v1/workflow/versions", headers=headers("manager-a"))
        assert resp_list.status_code == 200
        assert isinstance(resp_list.json(), list)

        # 2. Manager cannot create workflow version (403)
        resp_mgr = client.post(
            "/api/v1/workflow/versions",
            json={"version": 3, "name": "Оптимизированный процесс v3", "definition": {}},
            headers=headers("manager-a"),
        )
        assert resp_mgr.status_code == 403

        # 3. Administrator creates draft v3
        resp_admin = client.post(
            "/api/v1/workflow/versions",
            json={
                "version": 3,
                "name": "Оптимизированный процесс v3",
                "description": "Сокращённый цикл согласования",
                "definition": {
                    "schema_version": "1.0",
                    "template_code": "rtk_custom_v3",
                    "version": 3,
                    "name": "Оптимизированный процесс v3",
                    "initial_state": "contact_search",
                    "states": [
                        {"code": "contact_search", "name": "Поиск контакта", "kind": "initial"},
                        {"code": "completed", "name": "Завершено", "kind": "terminal"},
                    ],
                    "transitions": [
                        {
                            "code": "contact_to_completed",
                            "from": "contact_search",
                            "to": "completed",
                            "kind": "forward",
                            "comment_required": False,
                            "condition_refs": [],
                        }
                    ],
                },
            },
            headers=headers("administrator"),
        )
        assert resp_admin.status_code == 201
        created_v3 = resp_admin.json()
        assert created_v3["version"] == 3
        assert created_v3["is_published"] is False

        # 4. Duplicate version returns 409
        resp_dup = client.post(
            "/api/v1/workflow/versions",
            json={"version": 3, "name": "Дубликат", "definition": {}},
            headers=headers("administrator"),
        )
        assert resp_dup.status_code == 409
        assert resp_dup.json()["error"]["code"] == "CONFLICT"

        # 5. Manager cannot publish (403)
        resp_pub_mgr = client.post("/api/v1/workflow/versions/3/publish", headers=headers("manager-a"))
        assert resp_pub_mgr.status_code == 403

        # 6. Administrator publishes v3
        resp_pub = client.post("/api/v1/workflow/versions/3/publish", headers=headers("administrator"))
        assert resp_pub.status_code == 200
        assert resp_pub.json()["status"] == "published"
        assert resp_pub.json()["is_published"] is True

        # 7. GET /api/v1/workflow?version=3 now returns the dynamic workflow
        resp_get_v3 = client.get("/api/v1/workflow?version=3", headers=headers("manager-a"))
        assert resp_get_v3.status_code == 200
        v3_data = resp_get_v3.json()
        assert v3_data["version"] == 3
        assert len(v3_data["states"]) == 2
    finally:
        WORKFLOW_REGISTRY.pop(3, None)


def test_reports_selected_columns_and_pdf_font_embedding(client):
    # Create an interaction with cyrillic text
    resp_create = client.post(
        "/api/v1/interactions",
        json={
            "title": "Интеграция с Санкт-Петербургским политехническим университетом Петра Великого",
            "organization_id": "org-1",
            "program_id": "program-devops",
            "product_id": "product-cloud",
            "cycle_label": "Осенний семестр 2026",
            "owner_id": "manager-a",
        },
        headers=headers("manager-a", str(uuid4())),
    )
    assert resp_create.status_code == 201

    now_iso = datetime.now(timezone.utc).isoformat()
    req_payload = {
        "as_of": now_iso,
        "knowledge_cutoff": now_iso,
        "selected_columns": ["title", "organization_name"],
    }

    # 1. JSON export with selected_columns
    resp_json = client.post("/api/v1/reports/snapshot/export?format=json", json=req_payload, headers=headers("supervisor"))
    assert resp_json.status_code == 200
    rows = resp_json.json()["rows"]
    assert len(rows) >= 1
    first_row = rows[0]
    assert "title" in first_row
    assert "organization_name" in first_row
    assert "state_name" not in first_row

    # 2. CSV export with selected_columns
    resp_csv = client.post("/api/v1/reports/snapshot/export?format=csv", json=req_payload, headers=headers("supervisor"))
    assert resp_csv.status_code == 200
    csv_text = resp_csv.content.decode("utf-8-sig")
    first_line = csv_text.splitlines()[0]
    assert "Название" in first_line
    assert "Организация" in first_line
    assert "Программа" not in first_line

    # 3. XLSX export with selected_columns
    resp_xlsx = client.post("/api/v1/reports/snapshot/export?format=xlsx", json=req_payload, headers=headers("supervisor"))
    assert resp_xlsx.status_code == 200
    with zipfile.ZipFile(io.BytesIO(resp_xlsx.content)) as zf:
        sheet1 = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert "Название" in sheet1
        assert "Организация" in sheet1

    # 4. PDF export with TrueType Cyrillic font embedding and BT/ET syntax check
    resp_pdf = client.post("/api/v1/reports/snapshot/export?format=pdf", json=req_payload, headers=headers("supervisor"))
    assert resp_pdf.status_code == 200
    pdf_bytes = resp_pdf.content
    assert pdf_bytes.startswith(b"%PDF-1.4")
    assert b"%%EOF" in pdf_bytes
    assert b"/FontFile2" in pdf_bytes
    assert b"/CIDToGIDMap" in pdf_bytes
    assert b"/LiberationSans" in pdf_bytes
