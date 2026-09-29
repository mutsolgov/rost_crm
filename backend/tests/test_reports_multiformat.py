import io
import zipfile
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest


def headers(user="supervisor", key=None):
    res = {"X-Demo-User": user}
    if key:
        res["Idempotency-Key"] = key
    return res


def create_interaction(client, user="manager-a", **changes):
    body = {
        "title": "Отчётное взаимодействие",
        "organization_id": "org-1",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "Тестовый цикл отчётов",
        "owner_id": user,
    }
    body.update(changes)
    response = client.post("/api/v1/interactions", json=body, headers=headers(user, str(uuid4())))
    assert response.status_code == 201, response.text
    return response.json()


def test_snapshot_export_json_xlsx_pdf(client):
    create_interaction(client, "manager-a")
    now_iso = datetime.now(timezone.utc).isoformat()
    req = {
        "as_of": now_iso,
        "knowledge_cutoff": now_iso,
        "as_of_inclusive": True,
    }

    # JSON export
    json_resp = client.post("/api/v1/reports/snapshot/export?format=json", json=req, headers=headers("supervisor"))
    assert json_resp.status_code == 200
    assert json_resp.headers["X-Report-Format"] == "json"
    assert "attachment" in json_resp.headers["Content-Disposition"]
    data = json_resp.json()
    assert data["report_type"] == "snapshot"
    assert data["total_interactions"] >= 1
    assert "counts_by_state" in data

    # XLSX export
    xlsx_resp = client.post("/api/v1/reports/snapshot/export?format=xlsx", json=req, headers=headers("supervisor"))
    assert xlsx_resp.status_code == 200
    assert xlsx_resp.headers["X-Report-Format"] == "xlsx"
    assert xlsx_resp.headers["Content-Type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert xlsx_resp.content.startswith(b"PK\x03\x04")
    # Verify readable OpenXML zip
    with zipfile.ZipFile(io.BytesIO(xlsx_resp.content)) as zf:
        assert "xl/worksheets/sheet1.xml" in zf.namelist()
        assert "xl/worksheets/sheet2.xml" in zf.namelist()
        assert "xl/styles.xml" in zf.namelist()

    # XLS export (legacy format alias supported for TZ compliance)
    xls_resp = client.post("/api/v1/reports/snapshot/export?format=xls", json=req, headers=headers("supervisor"))
    assert xls_resp.status_code == 200
    assert xls_resp.headers["X-Report-Format"] == "xls"
    assert "application/vnd.ms-excel" in xls_resp.headers["Content-Type"]
    assert xls_resp.content.startswith(b"PK\x03\x04")

    # PDF export
    pdf_resp = client.post("/api/v1/reports/snapshot/export?format=pdf", json=req, headers=headers("supervisor"))
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["X-Report-Format"] == "pdf"
    assert pdf_resp.headers["Content-Type"] == "application/pdf"
    assert pdf_resp.content.startswith(b"%PDF-1.4")
    assert b"%%EOF" in pdf_resp.content


def test_activity_report_and_exports(client):
    item = create_interaction(client, "manager-a")
    iid = item["id"]

    # Perform a transition
    trans_resp = client.post(
        f"/api/v1/interactions/{iid}/transitions",
        json={
            "transition_code": "contact_search_to_needs_clarification",
            "expected_revision": 1,
            "comment": "Начало обсуждения",
        },
        headers=headers("manager-a", str(uuid4())),
    )
    assert trans_resp.status_code == 200

    now_dt = datetime.now(timezone.utc)
    from_iso = (now_dt - timedelta(hours=1)).isoformat()
    to_iso = (now_dt + timedelta(hours=1)).isoformat()
    cutoff_iso = (now_dt + timedelta(hours=1)).isoformat()

    req = {
        "from": from_iso,
        "to": to_iso,
        "knowledge_cutoff": cutoff_iso,
    }

    # Direct query
    act_resp = client.post("/api/v1/reports/activity", json=req, headers=headers("supervisor"))
    assert act_resp.status_code == 200
    act_data = act_resp.json()
    assert act_data["report_type"] == "activity"
    assert act_data["total_transitions"] >= 1
    assert "counts_by_to_state" in act_data
    assert "counts_by_historical_owner" in act_data
    assert iid in act_data["interaction_ids"]

    # XLSX export
    act_xlsx = client.post("/api/v1/reports/activity/export?format=xlsx", json=req, headers=headers("supervisor"))
    assert act_xlsx.status_code == 200
    assert act_xlsx.content.startswith(b"PK\x03\x04")

    # PDF export
    act_pdf = client.post("/api/v1/reports/activity/export?format=pdf", json=req, headers=headers("supervisor"))
    assert act_pdf.status_code == 200
    assert act_pdf.content.startswith(b"%PDF-1.4")


def test_created_report_and_exports(client):
    item = create_interaction(client, "manager-a")
    iid = item["id"]

    now_dt = datetime.now(timezone.utc)
    from_iso = (now_dt - timedelta(hours=1)).isoformat()
    to_iso = (now_dt + timedelta(hours=1)).isoformat()
    cutoff_iso = (now_dt + timedelta(hours=1)).isoformat()

    req = {
        "from": from_iso,
        "to": to_iso,
        "knowledge_cutoff": cutoff_iso,
    }

    # Query
    c_resp = client.post("/api/v1/reports/created", json=req, headers=headers("supervisor"))
    assert c_resp.status_code == 200
    c_data = c_resp.json()
    assert c_data["report_type"] == "created"
    assert c_data["total_created"] >= 1
    assert iid in c_data["interaction_ids"]
    assert "counts_by_organization" in c_data

    # XLSX export
    c_xlsx = client.post("/api/v1/reports/created/export?format=xlsx", json=req, headers=headers("supervisor"))
    assert c_xlsx.status_code == 200
    assert c_xlsx.content.startswith(b"PK\x03\x04")

    # PDF export
    c_pdf = client.post("/api/v1/reports/created/export?format=pdf", json=req, headers=headers("supervisor"))
    assert c_pdf.status_code == 200
    assert c_pdf.content.startswith(b"%PDF-1.4")



def test_unsupported_export_format_returns_422(client):
    now_iso = datetime.now(timezone.utc).isoformat()
    req = {"as_of": now_iso, "knowledge_cutoff": now_iso}
    resp = client.post("/api/v1/reports/snapshot/export?format=doc", json=req, headers=headers("supervisor"))
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_activity_report_historical_owner_resolution_after_reassignment(client):
    """Verifies that activity report resolves historical owner at event time, not current owner."""
    item = create_interaction(client, "manager-a")
    iid = item["id"]

    # Manager A transitions contact_search -> needs_clarification
    t1 = client.post(
        f"/api/v1/interactions/{iid}/transitions",
        json={
            "transition_code": "contact_search_to_needs_clarification",
            "expected_revision": item["revision"],
            "comment": "Первый этап менеджера А",
        },
        headers=headers("manager-a", str(uuid4())),
    )
    assert t1.status_code == 200
    rev1 = t1.json()["revision"]

    # Supervisor reassigns interaction to manager-b
    assign_resp = client.post(
        f"/api/v1/interactions/{iid}/assignments",
        json={
            "owner_id": "manager-b",
            "expected_revision": rev1,
            "reason": "Передача новому менеджеру",
        },
        headers=headers("supervisor", str(uuid4())),
    )
    assert assign_resp.status_code == 200
    rev2 = assign_resp.json()["revision"]

    # Manager B transitions needs_clarification -> meeting
    t2 = client.post(
        f"/api/v1/interactions/{iid}/transitions",
        json={
            "transition_code": "needs_clarification_to_meeting",
            "expected_revision": rev2,
            "comment": "Второй этап менеджера Б",
        },
        headers=headers("manager-b", str(uuid4())),
    )
    assert t2.status_code == 200

    now_dt = datetime.now(timezone.utc)
    req = {
        "from": (now_dt - timedelta(hours=1)).isoformat(),
        "to": (now_dt + timedelta(hours=1)).isoformat(),
        "knowledge_cutoff": (now_dt + timedelta(hours=1)).isoformat(),
    }

    act_resp = client.post("/api/v1/reports/activity", json=req, headers=headers("supervisor"))
    assert act_resp.status_code == 200
    act_data = act_resp.json()

    # Historical owner resolution must reflect both managers:
    owner_counts = act_data["counts_by_historical_owner"]
    assert "manager-a" in owner_counts and owner_counts["manager-a"] >= 1
    assert "manager-b" in owner_counts and owner_counts["manager-b"] >= 1


def test_snapshot_zero_buckets_for_all_fifteen_states(client):
    """Authoritative requirement from 05-report-fixture.json: all 15 states must exist in counts_by_state."""
    now_iso = datetime.now(timezone.utc).isoformat()
    req = {"as_of": now_iso, "knowledge_cutoff": now_iso}

    resp = client.post("/api/v1/reports/snapshot", json=req, headers=headers("supervisor"))
    assert resp.status_code == 200
    counts = resp.json()["counts_by_state"]

    expected_15_states = [
        "contact_search", "needs_clarification", "meeting", "document_exchange",
        "document_revision", "document_signing", "materials_transfer", "deployment",
        "teacher_training", "curriculum_update", "classes", "materials_update",
        "teacher_upskilling", "completed", "cancelled",
    ]
    for state in expected_15_states:
        assert state in counts, f"Missing state '{state}' in counts_by_state"
        assert isinstance(counts[state], int)
        assert counts[state] >= 0


def test_xlsx_formula_injection_defense(client):
    """Formula-like characters (=, +, -, @) in strings are encoded as inlineStr in XLSX, preventing formula execution."""
    formula_title = "=HYPERLINK(\"http://malicious.example.com\", \"Click Me\")"
    create_interaction(client, "manager-a", title=formula_title)

    now_iso = datetime.now(timezone.utc).isoformat()
    req = {"as_of": now_iso, "knowledge_cutoff": now_iso}

    xlsx_resp = client.post("/api/v1/reports/snapshot/export?format=xlsx", json=req, headers=headers("supervisor"))
    assert xlsx_resp.status_code == 200
    assert xlsx_resp.content.startswith(b"PK\x03\x04")

    with zipfile.ZipFile(io.BytesIO(xlsx_resp.content)) as zf:
        sheet1_xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        # Ensure it is written as inline string, not a formula tag <f>
        assert "<f>" not in sheet1_xml
        assert "t=\"inlineStr\"" in sheet1_xml
        assert "HYPERLINK" in sheet1_xml

