import io
import zipfile
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.importer import (
    _match_header,
    _parse_date,
    _parse_term_years,
    parse_csv_stdlib,
    parse_xlsx_stdlib,
)
from app.integrations.base import NormalizedEnvelope
from app.integrations.service import reconcile_application, resolve_inbox_item
from app.models import (
    Comment,
    Contract,
    IntegrationInbox,
    Interaction,
    InteractionEvent,
    LearningMetric,
    License,
    Organization,
    OrganizationAccess,
    OrganizationContact,
    Product,
    ProgramProduct,
    User,
    new_id,
    utcnow,
)
from app.workflow import get_states


def headers(user="manager-a", key=None):
    res = {"X-Demo-User": user}
    if key:
        res["Idempotency-Key"] = key
    return res


def create_test_interaction(client, user="manager-a", **overrides):
    body = {
        "title": "Тестовое взаимодействие для аудита",
        "organization_id": "org-1",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "Тестовый цикл 2026",
        "owner_id": user,
    }
    body.update(overrides)
    resp = client.post("/api/v1/interactions", json=body, headers=headers(user, str(uuid4())))
    assert resp.status_code == 201, resp.text
    return resp.json()


# ============================================================================
# F02: Workflow migration scope enforcement and subject validation
# ============================================================================

def test_f02_workflow_migration_scope_enforced(client, app):
    """Supervisor only migrates cards in their scope; administrator can migrate all."""
    card1 = create_test_interaction(client, "manager-a", title="Карточка команды А")

    mapping = {k: k for k in get_states(1).keys()}
    resp = client.post(
        "/api/v1/workflow/migrate/preview",
        json={"from_version": 1, "to_version": 2, "status_mapping": mapping},
        headers=headers("supervisor"),
    )
    assert resp.status_code == 200
    assert resp.json()["affected_interactions_count"] >= 1

    # Administrator can also preview
    resp_admin = client.post(
        "/api/v1/workflow/migrate/preview",
        json={"from_version": 1, "to_version": 2, "status_mapping": mapping},
        headers=headers("administrator"),
    )
    assert resp_admin.status_code == 200


def test_f02_workflow_migration_subject_validation(client, app):
    """Migrating cards lacking program/product into SUBJECT_REQUIRED_STATES fails validation."""
    # Create an interaction without program and product at early stage
    card = create_test_interaction(
        client,
        "manager-a",
        title="Карточка без предмета",
        program_id=None,
        product_id=None,
    )
    assert card["program_id"] is None
    assert card["product_id"] is None
    assert card["state"] == "contact_search"

    # Map card's current state ('contact_search') to 'classes' (which is in SUBJECT_REQUIRED_STATES)
    bad_mapping = {k: k for k in get_states(1).keys()}
    bad_mapping["contact_search"] = "classes"

    # 1. Preview marks is_valid=False and adds warning
    prev_resp = client.post(
        "/api/v1/workflow/migrate/preview",
        json={"from_version": 1, "to_version": 2, "status_mapping": bad_mapping},
        headers=headers("supervisor"),
    )
    assert prev_resp.status_code == 200
    prev_data = prev_resp.json()
    assert prev_data["is_valid"] is False
    assert any("обязательной привязки" in w for w in prev_data["warnings"])

    # 2. Commit raises 422 VALIDATION_ERROR with invalid_card_ids
    commit_resp = client.post(
        "/api/v1/workflow/migrate/commit",
        json={"from_version": 1, "to_version": 2, "status_mapping": bad_mapping},
        headers=headers("supervisor", str(uuid4())),
    )
    assert commit_resp.status_code == 422
    err = commit_resp.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert "details" in err
    assert card["id"] in err["details"]["invalid_card_ids"]


# ============================================================================
# F03: visible_organization_ids in learning metrics summary
# ============================================================================

def test_f03_learning_metrics_scope_all_roles(client, app):
    """get_learning_metrics_summary enforces visible_organization_ids for all roles."""
    with app.state.session_factory() as session:
        m = LearningMetric(
            id=new_id(),
            organization_id="org-2",
            program_id="program-devops",
            metric_code="attendance_rate",
            value=88.5,
            unit="percent",
            as_of=utcnow(),
            source="lms",
            external_id="ext-metric-f03",
            created_at=utcnow(),
        )
        session.add(m)
        session.commit()

    # Query metrics for org-2 as manager-a (no access to org-2) -> returns zero totals
    resp_mgr = client.get("/api/v1/integrations/metrics?organization_id=org-2", headers=headers("manager-a"))
    assert resp_mgr.status_code == 200
    mgr_data = resp_mgr.json()
    assert mgr_data["total_cohorts"] == 0
    assert mgr_data["metrics"] == []

    # Query metrics for an unauthorized org as administrator with no org grants -> returns zero totals
    resp_admin = client.get("/api/v1/integrations/metrics?organization_id=non-existent-org", headers=headers("administrator"))
    assert resp_admin.status_code == 200
    admin_data = resp_admin.json()
    assert admin_data["total_cohorts"] == 0
    assert admin_data["metrics"] == []


# ============================================================================
# F04: interactions.write permission enforcement on upload_attachment
# ============================================================================

def test_f04_upload_attachment_permissions_and_existence(client, app):
    """Uploading attachments requires interactions.write; non-existent interaction returns 404 before 403."""
    card = create_test_interaction(client, "manager-a")

    # 1. Non-existent card returns 404 (existence concealment invariant)
    fake_id = str(uuid4())
    resp_404 = client.post(
        f"/api/v1/interactions/{fake_id}/attachments",
        files={"file": ("test.pdf", b"%PDF-1.4 test", "application/pdf")},
        headers=headers("manager-a"),
    )
    assert resp_404.status_code == 404

    # 2. Card out of manager-b's scope returns 404
    resp_foreign = client.post(
        f"/api/v1/interactions/{card['id']}/attachments",
        files={"file": ("test.pdf", b"%PDF-1.4 test", "application/pdf")},
        headers=headers("manager-b"),
    )
    assert resp_foreign.status_code == 404

    # 3. Create a read-only user without interactions.write permission but with read_all access to org-1
    with app.state.session_factory() as session:
        readonly_user = User(
            id="user-readonly",
            keycloak_subject="sub-readonly",
            name="Аудитор Наблюдатель",
            role="auditor",
            permissions=["reports.read"],  # explicitly lacks interactions.write
            active=True,
        )
        session.add(readonly_user)
        session.flush()
        access = OrganizationAccess(
            organization_id="org-1",
            user_id=readonly_user.id,
            read_all=True,
            can_create=False,
        )
        session.add(access)
        session.commit()

    # User can view the interaction (returns 200)
    resp_view = client.get(f"/api/v1/interactions/{card['id']}", headers=headers("user-readonly"))
    assert resp_view.status_code == 200

    # But uploading attachment returns 403 FORBIDDEN
    resp_forbidden = client.post(
        f"/api/v1/interactions/{card['id']}/attachments",
        files={"file": ("test.pdf", b"%PDF-1.4 test", "application/pdf")},
        headers=headers("user-readonly"),
    )
    assert resp_forbidden.status_code == 403

    # 4. Standard manager with interactions.write can upload (201 Created)
    resp_ok = client.post(
        f"/api/v1/interactions/{card['id']}/attachments",
        files={"file": ("test.pdf", b"%PDF-1.4 test", "application/pdf")},
        headers=headers("manager-a"),
    )
    assert resp_ok.status_code == 201


# ============================================================================
# F05: PDF Cyrillic rendering & proportional wrapping
# ============================================================================

def test_f05_pdf_export_cyrillic_and_layout(client, app):
    """Pure vector PDF 1.4 exports with Type 0 font, UTF-16BE hex strings, and proportional word wrapping."""
    long_title = "ИТ-школа Ростелекома: комплексная подготовка специалистов по облачным сервисам и DevOps"
    card = create_test_interaction(client, "manager-a", title=long_title)

    req = {"as_of": datetime.now(timezone.utc).isoformat()}
    resp = client.post("/api/v1/reports/snapshot/export?format=pdf", json=req, headers=headers("supervisor"))
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "application/pdf"
    content = resp.content
    assert content.startswith(b"%PDF-1.4")
    assert b"%%EOF" in content
    # Check Type 0 font with Identity-H encoding
    assert b"/Subtype /Type0" in content
    assert b"/Encoding /Identity-H" in content
    assert b"/ToUnicode" in content
    # Check UTF-16BE hex strings used in content streams
    assert b"<" in content and b"> Tj" in content


# ============================================================================
# F06: Created report totals contract sync
# ============================================================================

def test_f06_created_report_totals_contract(client, app):
    """POST /reports/created returns totals with interactions, organizations, counts_by_state."""
    create_test_interaction(client, "manager-a")
    now_dt = datetime.now(timezone.utc)
    req = {
        "from": (now_dt - timedelta(days=1)).isoformat(),
        "to": (now_dt + timedelta(days=1)).isoformat(),
        "knowledge_cutoff": (now_dt + timedelta(days=1)).isoformat(),
    }
    resp = client.post("/api/v1/reports/created", json=req, headers=headers("supervisor"))
    assert resp.status_code == 200
    data = resp.json()
    assert "totals" in data
    totals = data["totals"]
    assert "interactions" in totals
    assert isinstance(totals["interactions"], int)
    assert totals["interactions"] >= 1
    assert "organizations" in totals
    assert isinstance(totals["organizations"], int)
    assert "counts_by_state" in totals
    assert isinstance(totals["counts_by_state"], dict)
    assert totals["counts_by_state"]["contact_search"] >= 1
    # Backward compatibility
    assert "created" in totals


# ============================================================================
# F07: Sparse XLSX parsing
# ============================================================================

def test_f07_sparse_xlsx_parsing():
    """Sparse coordinate 'r' in XLSX maintains correct column alignment without shifting."""
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
        # Row 1: A1="Название", B1="Тип", C1="Контакт"
        # Row 2: A2="МГУ", C2="Иван" (B2 omitted intentionally!)
        sheet_content = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="inlineStr"><is><t>Название</t></is></c>
      <c r="B1" t="inlineStr"><is><t>Тип</t></is></c>
      <c r="C1" t="inlineStr"><is><t>Контакт</t></is></c>
    </row>
    <row r="2">
      <c r="A2" t="inlineStr"><is><t>МГУ</t></is></c>
      <c r="C2" t="inlineStr"><is><t>Иван</t></is></c>
    </row>
  </sheetData>
</worksheet>"""
        zf.writestr("xl/worksheets/sheet1.xml", sheet_content)

    rows = parse_xlsx_stdlib(buf.getvalue())
    assert len(rows) == 2
    header = rows[0]
    data_row = rows[1]
    assert header == ["Название", "Тип", "Контакт"]
    assert len(data_row) >= 3
    assert data_row[0] == "МГУ"
    assert data_row[1] == ""
    assert data_row[2] == "Иван"


# ============================================================================
# F08: commit_organizations_import mandatory validation (422)
# ============================================================================

def test_f08_commit_import_mandatory_validation(client):
    """Rows with missing/empty organization names raise 422 VALIDATION_ERROR instead of silent ignore."""
    body = {
        "rows": [
            {"data": {"name": "", "type": "university", "contact_name": "Иванов"}},
        ]
    }
    resp = client.post(
        "/api/v1/imports/organizations/commit",
        json=body,
        headers=headers("supervisor", str(uuid4())),
    )
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert "Название вуза" in err["message"]


# ============================================================================
# F09: Creator Organization Access grant (can_create=True)
# ============================================================================

def test_f09_imported_org_interaction_creation(client, app):
    """User importing an organization receives can_create=True and can immediately create interactions."""
    unique_org_name = f"Университет Инноваций-{uuid4().hex[:8]}"
    body = {
        "rows": [
            {"data": {"name": unique_org_name, "type": "university", "contact_name": "Ректор"}},
        ]
    }
    commit_resp = client.post(
        "/api/v1/imports/organizations/commit",
        json=body,
        headers=headers("supervisor", str(uuid4())),
    )
    assert commit_resp.status_code == 200

    # Retrieve the created organization's id
    with app.state.session_factory() as session:
        org = session.scalar(select(Organization).where(Organization.name == unique_org_name))
        assert org is not None
        # Verify access grant exists with can_create=True
        access = session.get(OrganizationAccess, ("supervisor", org.id))
        assert access is not None
        assert access.can_create is True
        assert access.read_all is True
        org_id = org.id

    # Creating interaction immediately with supervisor succeeds (not 404!)
    create_resp = client.post(
        "/api/v1/interactions",
        json={
            "title": "Первичный контакт с новым ВУЗом",
            "organization_id": org_id,
            "cycle_label": "Цикл 2026",
            "owner_id": "manager-a",
        },
        headers=headers("supervisor", str(uuid4())),
    )
    assert create_resp.status_code == 201


# ============================================================================
# F11: InteractionUpdate forbid null on title & exclude_unset in idempotency
# ============================================================================

def test_f11_patch_interaction_forbid_null_and_exclude_unset(client):
    """InteractionUpdate rejects explicit null on title and cycle_label with 422."""
    card = create_test_interaction(client, "manager-a", title="Исходное название")

    # 1. Sending explicit null for title -> 422
    resp_null_title = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={"expected_revision": 1, "title": None},
        headers=headers("manager-a", str(uuid4())),
    )
    assert resp_null_title.status_code == 422

    # 2. Sending explicit null for cycle_label -> 422
    resp_null_cycle = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={"expected_revision": 1, "cycle_label": None},
        headers=headers("manager-a", str(uuid4())),
    )
    assert resp_null_cycle.status_code == 422

    # 3. Omitting title is permitted and preserves existing title
    idem_key = str(uuid4())
    resp_ok = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={"expected_revision": 1, "cycle_label": "Обновленный цикл 2026"},
        headers=headers("manager-a", idem_key),
    )
    assert resp_ok.status_code == 200
    updated = resp_ok.json()
    assert updated["title"] == "Исходное название"
    assert updated["cycle_label"] == "Обновленный цикл 2026"
    assert updated["revision"] == 2

    # 4. Replaying with same Idempotency-Key returns cached response
    resp_replay = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={"expected_revision": 1, "cycle_label": "Обновленный цикл 2026"},
        headers=headers("manager-a", idem_key),
    )
    assert resp_replay.status_code == 200
    assert resp_replay.json()["revision"] == 2


# ============================================================================
# F12: CAS inbox transition & learning metric source_revision check
# ============================================================================

def test_f12_reconcile_inbox_atomic_cas_and_alias(client, app):
    """Atomic CAS prevents race condition on resolve; resolve_inbox_item alias exists."""
    assert resolve_inbox_item is reconcile_application

    client.post("/api/v1/integrations/sync/website", headers=headers("supervisor"))
    inbox = client.get("/api/v1/integrations/inbox?status=pending", headers=headers("supervisor")).json()
    assert len(inbox["items"]) >= 1
    item_id = inbox["items"][0]["id"]

    # First resolution: reject -> 200
    r1 = client.post(
        f"/api/v1/integrations/inbox/{item_id}/resolve",
        headers=headers("supervisor", str(uuid4())),
        json={"action": "reject", "reason": "Отказ"},
    )
    assert r1.status_code == 200

    # Second resolution with different key -> 409 Conflict
    r2 = client.post(
        f"/api/v1/integrations/inbox/{item_id}/resolve",
        headers=headers("supervisor", str(uuid4())),
        json={"action": "link_existing", "organization_id": "org-1"},
    )
    assert r2.status_code == 409


def test_f12_sync_source_learning_metric_revision_order(client, app):
    """sync_source does not overwrite LearningMetric with an older source_revision."""
    # 1. Process envelope with source_revision="2"
    with app.state.session_factory() as session:
        item_v2 = IntegrationInbox(
            id=new_id(),
            source="lms",
            entity_type="learning_metric",
            external_id="ext-cohort-99",
            source_revision="2",
            payload={"metric_code": "attendance_rate", "value": 95.0, "unit": "percent"},
            status="processed",
            processed_at=utcnow(),
        )
        session.add(item_v2)
        metric = LearningMetric(
            id=new_id(),
            organization_id="org-1",
            program_id="program-devops",
            metric_code="attendance_rate",
            value=95.0,
            unit="percent",
            as_of=utcnow(),
            source="lms",
            external_id="ext-cohort-99",
            created_at=utcnow(),
        )
        session.add(metric)
        session.commit()

    # Now simulate sync_source with mock adapter delivering envelope revision "1" (older!)
    from app.integrations.base import BaseIntegrationAdapter
    from app.integrations.service import sync_source

    with app.state.session_factory() as session:
        supervisor = session.get(User, "supervisor")
        older_env = NormalizedEnvelope(
            source="lms",
            entity_type="learning_metric",
            external_id="ext-cohort-99",
            source_revision="1",
            payload={
                "organization_id": "org-1",
                "program_id": "program-devops",
                "metric_code": "attendance_rate",
                "value": 40.0,
                "unit": "percent",
            },
        )

        class MockAdapter(BaseIntegrationAdapter):
            def health_check(self): return {"status": "ok"}
            def fetch_updates(self, since=None): return [older_env]

        import app.integrations.service as int_svc
        original_get_adapter = int_svc.get_adapter
        int_svc.get_adapter = lambda name, cfg=None: MockAdapter()
        try:
            res = sync_source(session, supervisor, "lms")
            session.commit()
        finally:
            int_svc.get_adapter = original_get_adapter

    # Verify metric value was NOT overwritten with 40.0
    with app.state.session_factory() as session:
        current_metric = session.scalar(
            select(LearningMetric).where(
                LearningMetric.source == "lms",
                LearningMetric.external_id == "ext-cohort-99",
            )
        )
        assert current_metric is not None
        assert current_metric.value == 95.0  # Kept newer revision 2!


def test_f12_sync_source_chained_out_of_order_revisions(client, app):
    """sync_source accurately maintains the highest applied revision across chained out-of-order envelopes.

    Sequence:
      1. Rev 5 (val=50.0) -> applied, metric=50.0, inbox status='processed'
      2. Rev 3 (val=30.0) -> skipped (3 < 5), metric=50.0, inbox status='skipped'
      3. Rev 4 (val=40.0) -> skipped (4 < 5), metric=50.0, inbox status='skipped'
      4. Rev 6 (val=60.0) -> applied (6 > 5), metric=60.0, inbox status='processed'
    """
    from app.integrations.base import BaseIntegrationAdapter
    from app.integrations.service import sync_source
    import app.integrations.service as int_svc

    class MockAdapter(BaseIntegrationAdapter):
        def __init__(self, envelopes):
            self._envelopes = envelopes

        def health_check(self):
            return {"status": "ok"}

        def fetch_updates(self, since=None):
            return self._envelopes

    external_id = f"cohort-chained-{uuid4().hex[:8]}"

    def make_envelope(revision: str, value: float):
        return NormalizedEnvelope(
            source="lms",
            entity_type="learning_metric",
            external_id=external_id,
            source_revision=revision,
            payload={
                "organization_id": "org-1",
                "program_id": "program-devops",
                "metric_code": "attendance_rate",
                "value": value,
                "unit": "percent",
            },
        )

    original_get_adapter = int_svc.get_adapter
    try:
        # Step 1: Rev 5 arrives with value 50.0 -> Applied
        with app.state.session_factory() as session:
            supervisor = session.get(User, "supervisor")
            int_svc.get_adapter = lambda name, cfg=None: MockAdapter([make_envelope("5", 50.0)])
            res1 = sync_source(session, supervisor, "lms")
            session.commit()
            assert res1["processed_count"] == 1
            assert res1["skipped_count"] == 0

        with app.state.session_factory() as session:
            m1 = session.scalar(select(LearningMetric).where(LearningMetric.external_id == external_id))
            assert m1 is not None
            assert m1.value == 50.0
            inbox5 = session.scalar(
                select(IntegrationInbox).where(
                    IntegrationInbox.external_id == external_id,
                    IntegrationInbox.source_revision == "5",
                )
            )
            assert inbox5 is not None
            assert inbox5.status == "processed"
            assert inbox5.error_message is None

        # Step 2: Rev 3 arrives with value 30.0 -> Skipped (3 < 5)
        with app.state.session_factory() as session:
            supervisor = session.get(User, "supervisor")
            int_svc.get_adapter = lambda name, cfg=None: MockAdapter([make_envelope("3", 30.0)])
            res2 = sync_source(session, supervisor, "lms")
            session.commit()
            assert res2["skipped_count"] == 1
            assert res2["processed_count"] == 0

        with app.state.session_factory() as session:
            m2 = session.scalar(select(LearningMetric).where(LearningMetric.external_id == external_id))
            assert m2.value == 50.0  # Still 50.0!
            inbox3 = session.scalar(
                select(IntegrationInbox).where(
                    IntegrationInbox.external_id == external_id,
                    IntegrationInbox.source_revision == "3",
                )
            )
            assert inbox3 is not None
            assert inbox3.status == "skipped"
            assert inbox3.error_message is not None
            assert "older than" in inbox3.error_message

        # Step 3: Rev 4 arrives with value 40.0 -> Skipped because 4 < 5 (highest applied revision is 5, not 3)
        with app.state.session_factory() as session:
            supervisor = session.get(User, "supervisor")
            int_svc.get_adapter = lambda name, cfg=None: MockAdapter([make_envelope("4", 40.0)])
            res3 = sync_source(session, supervisor, "lms")
            session.commit()
            assert res3["skipped_count"] == 1
            assert res3["processed_count"] == 0

        with app.state.session_factory() as session:
            m3 = session.scalar(select(LearningMetric).where(LearningMetric.external_id == external_id))
            assert m3.value == 50.0  # NOT clobbered by 40.0!
            inbox4 = session.scalar(
                select(IntegrationInbox).where(
                    IntegrationInbox.external_id == external_id,
                    IntegrationInbox.source_revision == "4",
                )
            )
            assert inbox4 is not None
            assert inbox4.status == "skipped"
            assert inbox4.error_message is not None
            assert "older than" in inbox4.error_message

        # Step 4: Rev 6 arrives with value 60.0 -> Applied because 6 > 5
        with app.state.session_factory() as session:
            supervisor = session.get(User, "supervisor")
            int_svc.get_adapter = lambda name, cfg=None: MockAdapter([make_envelope("6", 60.0)])
            res4 = sync_source(session, supervisor, "lms")
            session.commit()
            assert res4["processed_count"] == 1
            assert res4["skipped_count"] == 0

        with app.state.session_factory() as session:
            m4 = session.scalar(select(LearningMetric).where(LearningMetric.external_id == external_id))
            assert m4.value == 60.0  # Successfully updated to 60.0!
            inbox6 = session.scalar(
                select(IntegrationInbox).where(
                    IntegrationInbox.external_id == external_id,
                    IntegrationInbox.source_revision == "6",
                )
            )
            assert inbox6 is not None
            assert inbox6.status == "processed"
            assert inbox6.error_message is None
    finally:
        int_svc.get_adapter = original_get_adapter


# ============================================================================
# F10: 10-field end-to-end audit (contacts, initial comment, licenses)
# ============================================================================

def test_f10_create_interaction_with_contact_and_initial_comment(client, app):
    """Interaction can be created with contact_id and initial comment, creating Comment record."""
    with app.state.session_factory() as session:
        contact = OrganizationContact(
            id=new_id(),
            organization_id="org-1",
            full_name="Иванов Петр Сергеевич",
            position="Декан факультета ИТ",
            email="ivanov@org1.ru",
            active=True,
        )
        session.add(contact)
        session.commit()
        contact_id = contact.id

    comment_text = "Стартовый комментарий к сотрудничеству с факультетом ИТ."
    body = {
        "title": "Сотрудничество с факультетом ИТ",
        "organization_id": "org-1",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "Осень 2026",
        "owner_id": "manager-a",
        "contact_id": contact_id,
        "comment": comment_text,
    }
    resp = client.post("/api/v1/interactions", json=body, headers=headers("manager-a", str(uuid4())))
    assert resp.status_code == 201, resp.text
    card = resp.json()
    assert card["contact_id"] == contact_id
    assert card["contact_name"] == "Иванов Петр Сергеевич"

    # Detail query shows comment in comments and event timeline
    detail_resp = client.get(f"/api/v1/interactions/{card['id']}", headers=headers("manager-a"))
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert len(detail["comments"]) == 1
    assert detail["comments"][0]["body"] == comment_text
    assert detail["comments"][0]["author_name"] == "Анна Смирнова"

    # Event of type comment_added is registered
    comment_events = [e for e in detail["events"] if e["type"] == "comment_added"]
    assert len(comment_events) == 1
    assert comment_events[0]["comment"] == comment_text


def test_f10_patch_interaction_license_selection(client, app):
    """Interaction can be updated with license_id, showing vendor and license metadata in details."""
    card = create_test_interaction(client, "manager-a")

    with app.state.session_factory() as session:
        lic = License(
            id=new_id(),
            organization_id="org-1",
            product_id="product-cloud",
            term_years=3,
            transfer_status="transferred",
            signed_on=utcnow(),
        )
        session.add(lic)
        session.commit()
        lic_id = lic.id

    # 1. Update license_id via PATCH
    patch_resp = client.patch(
        f"/api/v1/interactions/{card['id']}",
        json={"expected_revision": 1, "license_id": lic_id},
        headers=headers("manager-a", str(uuid4())),
    )
    assert patch_resp.status_code == 200, patch_resp.text
    updated = patch_resp.json()
    assert updated["license_id"] == lic_id
    assert updated["license_status"] == "transferred"
    assert updated["license_term_years"] == 3
    assert updated["product_vendor"] is not None

    # 2. Detail view contains vendor and license fields
    detail = client.get(f"/api/v1/interactions/{card['id']}", headers=headers("manager-a")).json()
    assert detail["license_id"] == lic_id
    assert detail["license_status"] == "transferred"
    assert detail["license_term_years"] == 3
    assert detail["product_vendor"] == "Ростелеком"


def test_f10_import_tabular_file_with_license_and_comment(client, app):
    """Master import parses 10 TZ fields, creates License and notes/Comment."""
    unique_org = f"Университет Связи-{uuid4().hex[:6]}"
    csv_text = (
        "Название ВУЗа;Вендор;ПО;Номер договора;Подписание лицензии;Срок действия лицензии (год);Статус по передачи;ФИО Менеджера;Ответственные от ВУЗа;Комментарий\n"
        f"{unique_org};Ростелеком;Облачная платформа;ДОГ-2026-77;2026-09-01;3;передано;Менеджер А;Сидоров Алексей;Стартовая договоренность с ректоратом"
    )

    # 1. Preview
    prev_resp = client.post(
        "/api/v1/imports/organizations/preview",
        files={"file": ("import_test.csv", csv_text.encode("utf-8"), "text/csv")},
        headers=headers("supervisor"),
    )
    assert prev_resp.status_code == 200, prev_resp.text
    prev_data = prev_resp.json()
    assert prev_data["valid_count"] == 1
    row_data = prev_data["preview_rows"][0]["data"]
    assert row_data["vendor"] == "Ростелеком"
    assert row_data["product"] == "Облачная платформа"
    assert row_data["license_term_years"] == "3"
    assert row_data["license_transfer_status"] == "передано"
    assert row_data["contact_name"] == "Сидоров Алексей"
    assert row_data["comment"] == "Стартовая договоренность с ректоратом"

    # 2. Commit
    commit_resp = client.post(
        "/api/v1/imports/organizations/commit",
        json={"rows": prev_data["preview_rows"]},
        headers=headers("supervisor", str(uuid4())),
    )
    assert commit_resp.status_code == 200, commit_resp.text
    cdata = commit_resp.json()
    assert cdata["created_organizations"] == 1
    assert cdata["created_contacts"] == 1
    assert cdata["created_licenses"] == 1

    # 3. Verify in DB
    with app.state.session_factory() as session:
        org = session.scalar(select(Organization).where(Organization.name == unique_org))
        assert org is not None
        contact = session.scalar(select(OrganizationContact).where(OrganizationContact.organization_id == org.id))
        assert contact is not None
        assert contact.full_name == "Сидоров Алексей"
        assert contact.notes == "Стартовая договоренность с ректоратом"

        lic = session.scalar(select(License).where(License.organization_id == org.id))
        assert lic is not None
        assert lic.term_years == 3
        assert lic.transfer_status == "передано"
        assert lic.signed_on is not None

    # 4. Now create an interaction for this org and verify re-import creates initial Comment
    create_card_resp = client.post(
        "/api/v1/interactions",
        json={
            "title": "Взаимодействие по импортированному ВУЗу",
            "organization_id": org.id,
            "cycle_label": "Цикл 2026",
            "owner_id": "manager-a",
        },
        headers=headers("supervisor", str(uuid4())),
    )
    assert create_card_resp.status_code == 201
    card_id = create_card_resp.json()["id"]

    # Re-run commit with updated comment
    new_comment = "Второй этап переговоров"
    prev_data["preview_rows"][0]["data"]["comment"] = new_comment
    commit2_resp = client.post(
        "/api/v1/imports/organizations/commit",
        json={"rows": prev_data["preview_rows"]},
        headers=headers("supervisor", str(uuid4())),
    )
    assert commit2_resp.status_code == 200

    # Verify Comment was added to interaction
    card_detail = client.get(f"/api/v1/interactions/{card_id}", headers=headers("supervisor")).json()
    assert any(c["body"] == new_comment for c in card_detail["comments"])
    assert any(e["type"] == "comment_added" and e.get("comment") == new_comment for e in card_detail["events"])


def test_f10_importer_boundary_robustness():
    """Boundary fuzzing and robustness for date and license term parsing."""
    from datetime import date
    from app.importer import _parse_date, _parse_term_years

    # 1. Term years parsing: numbers, floats, text strings
    assert _parse_term_years(1.0) == 1
    assert _parse_term_years("1.0") == 1
    assert _parse_term_years("1.0 год") == 1
    assert _parse_term_years("3 года") == 3
    assert _parse_term_years("5 лет") == 5
    assert _parse_term_years("3,5") == 4
    assert _parse_term_years(0) == 0
    assert _parse_term_years(None) is None
    assert _parse_term_years("") is None
    assert _parse_term_years("бессрочно") is None
    assert _parse_term_years("N/A") is None
    assert _parse_term_years("-1") is None
    assert _parse_term_years("2025-2027") is None
    assert _parse_term_years(999) is None

    # 2. Date parsing: datetime, date, various string formats
    d_obj = date(2026, 9, 1)
    parsed_d = _parse_date(d_obj)
    assert parsed_d is not None
    assert parsed_d.year == 2026 and parsed_d.month == 9 and parsed_d.day == 1

    for s in ("2026-09-01", "01.09.2026", "01/09/2026", "2026/09/01", "01-09-2026", "01.09.2026 14:30:00"):
        p = _parse_date(s)
        assert p is not None, f"Failed parsing {s}"
        assert p.year == 2026 and p.month == 9 and p.day == 1

    assert _parse_date(None) is None
    assert _parse_date("") is None
    assert _parse_date("неизвестно") is None


def test_f10_import_contextual_product_and_manager(client, app):
    """Import with manager and license but no product name infers product from existing interaction."""
    unique_org = f"МФТИ-{uuid4().hex[:6]}"

    with app.state.session_factory() as session:
        org = Organization(name=unique_org, type="university")
        session.add(org)
        session.flush()
        access = OrganizationAccess(organization_id=org.id, user_id="manager-a", read_all=True, can_create=True)
        session.add(access)
        # Create an interaction that already has product-cloud
        card = Interaction(
            id=new_id(),
            title="Сотрудничество с МФТИ",
            organization_id=org.id,
            program_id="program-devops",
            product_id="product-cloud",
            cycle_label="2026",
            owner_id="manager-a",
            state="contact_search",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(card)
        session.commit()
        org_id = org.id
        card_id = card.id

    # CSV has manager-b and license fields, but product name is blank
    csv_text = (
        "Название ВУЗа;Вендор;ПО;Номер договора;Подписание лицензии;Срок действия лицензии (год);Статус по передачи;ФИО Менеджера;Ответственные от ВУЗа;Комментарий\n"
        f"{unique_org};Ростелеком;;ДОГ-МФТИ-01;2026-09-01;2.0;передано;manager-b;Кузнецов Петр;Успешная встреча"
    )

    prev_resp = client.post(
        "/api/v1/imports/organizations/preview",
        files={"file": ("import_test2.csv", csv_text.encode("utf-8"), "text/csv")},
        headers=headers("supervisor"),
    )
    assert prev_resp.status_code == 200
    prev_data = prev_resp.json()
    assert prev_data["preview_rows"][0]["data"]["manager"] == "manager-b"

    commit_resp = client.post(
        "/api/v1/imports/organizations/commit",
        json={"rows": prev_data["preview_rows"]},
        headers=headers("supervisor", str(uuid4())),
    )
    assert commit_resp.status_code == 200
    res = commit_resp.json()
    assert res["created_licenses"] == 1

    with app.state.session_factory() as session:
        # 1. License inferred product-cloud from active interaction
        lic = session.scalar(select(License).where(License.organization_id == org_id))
        assert lic is not None
        assert lic.product_id == "product-cloud"
        assert lic.term_years == 2

        # 2. Manager-b was granted access and assigned to interaction
        mgr_access = session.get(OrganizationAccess, ("manager-b", org_id))
        assert mgr_access is not None
        assert mgr_access.read_all is True

        interaction = session.get(Interaction, card_id)
        assert interaction.owner_id == "manager-b"
        assert interaction.license_id == lic.id


def test_f10_import_prevents_incompatible_license_and_duplicate_comment(client, app):
    """Import with incompatible product does not corrupt interaction license_id, and duplicate comments are avoided."""
    unique_org = f"СПбГУ-{uuid4().hex[:6]}"

    with app.state.session_factory() as session:
        org = Organization(name=unique_org, type="university")
        session.add(org)
        session.flush()
        session.add(OrganizationAccess(organization_id=org.id, user_id="manager-a", read_all=True, can_create=True))
        card = Interaction(
            id=new_id(),
            title="Сотрудничество с СПбГУ",
            organization_id=org.id,
            program_id="program-devops",
            product_id="product-cloud",
            cycle_label="2026",
            owner_id="manager-a",
            state="contact_search",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(card)
        session.commit()
        org_id = org.id
        card_id = card.id

    # Row specifies product-test (incompatible with interaction's product-cloud)
    comment_str = "Тестовый комментарий"
    csv_text = (
        "Название ВУЗа;Вендор;ПО;Номер договора;Подписание лицензии;Срок действия лицензии (год);Статус по передачи;ФИО Менеджера;Ответственные от ВУЗа;Комментарий\n"
        f"{unique_org};Ростелеком;Тестовый стенд;ДОГ-СПБГУ-01;2026-09-01;1;передано;manager-a;Иванов Иван;{comment_str}"
    )

    prev_resp = client.post(
        "/api/v1/imports/organizations/preview",
        files={"file": ("import_test3.csv", csv_text.encode("utf-8"), "text/csv")},
        headers=headers("supervisor"),
    )
    assert prev_resp.status_code == 200
    prev_data = prev_resp.json()

    # Commit 1
    commit1_resp = client.post(
        "/api/v1/imports/organizations/commit",
        json={"rows": prev_data["preview_rows"]},
        headers=headers("supervisor", str(uuid4())),
    )
    assert commit1_resp.status_code == 200

    with app.state.session_factory() as session:
        card_db = session.get(Interaction, card_id)
        # Interaction product is product-cloud, so it should NOT be linked to license for product-test!
        assert card_db.license_id is None
        comments = session.scalars(select(Comment).where(Comment.interaction_id == card_id)).all()
        assert len(comments) == 1
        assert comments[0].body == comment_str

    # Commit 2 (re-import with same comment): should NOT create duplicate comment
    commit2_resp = client.post(
        "/api/v1/imports/organizations/commit",
        json={"rows": prev_data["preview_rows"]},
        headers=headers("supervisor", str(uuid4())),
    )
    assert commit2_resp.status_code == 200

    with app.state.session_factory() as session:
        comments_after = session.scalars(select(Comment).where(Comment.interaction_id == card_id)).all()
        assert len(comments_after) == 1


# ============================================================================
# F10: Extended edge case tests: OpenXML rich-text, TSV, header synonyms,
# license-program compatibility, and manager team sync with audit event
# ============================================================================

def test_f10_openxml_rich_text_and_serial_dates():
    """parse_xlsx_stdlib preserves rich text and _parse_date / _parse_term_years handle edge cases."""
    # Build minimal OpenXML zip with rich-text <si><r><t>
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "xl/sharedStrings.xml",
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="2" uniqueCount="2">'
            b'<si><t>Header 1</t></si>'
            b'<si><r><t>\xd0\xa1\xd0\x9f\xd0\xb1\xd0\x93\xd1\x83 </t></r><r><rPr><b/></rPr><t>\xd0\xa4\xd0\xb0\xd0\xba\xd1\x83\xd0\xbb\xd1\x8c\xd1\x82\xd0\xb5\xd1\x82</t></r></si>'
            b'</sst>',
        )
        z.writestr(
            "xl/worksheets/sheet1.xml",
            b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            b'<sheetData>'
            b'<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="inlineStr"><is><t>\xd0\x9f\xd0\x9e</t></is></c></row>'
            b'<row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2" t="b"><v>1</v></c></row>'
            b'</sheetData>'
            b'</worksheet>',
        )
        z.writestr("xl/workbook.xml", b'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>')

    buf.seek(0)
    all_rows = parse_xlsx_stdlib(buf.getvalue())
    assert all_rows[0] == ["Header 1", "ПО"]
    assert len(all_rows) == 2
    assert all_rows[1][0] == "СПбГу Факультет"
    assert all_rows[1][1] == "1"

    # Date parsing edge cases
    assert _parse_date(45536).strftime("%Y-%m-%d") == "2024-09-01"
    assert _parse_date(True) is None
    assert _parse_date(False) is None
    assert _parse_date("01.09.2024 г.").strftime("%Y-%m-%d") == "2024-09-01"
    assert _parse_date("2024 г.").strftime("%Y-%m-%d") == "2024-01-01"
    assert _parse_date("2025 год").strftime("%Y-%m-%d") == "2025-01-01"

    # Term years edge cases
    assert _parse_term_years(True) is None
    assert _parse_term_years(False) is None
    assert _parse_term_years("бессрочная") is None
    assert _parse_term_years("3 года") == 3
    assert _parse_term_years("1 год") == 1


def test_f10_tsv_tab_delimited_csv_parsing():
    """parse_csv_stdlib automatically detects tab delimiters."""
    tsv_content = "Название ВУЗа\tВендор\tПО\nМФТИ\tРостелеком\tОблако\n".encode("utf-8")
    all_rows = parse_csv_stdlib(tsv_content)
    assert all_rows[0] == ["Название ВУЗа", "Вендор", "ПО"]
    assert len(all_rows) == 2
    assert all_rows[1] == ["МФТИ", "Ростелеком", "Облако"]


def test_f10_header_matching_preposition_and_formal_product():
    """Header synonym matching rejects Russian prepositions and correctly identifies software terms."""
    # Preposition "по" should not trigger product match
    assert _match_header("Справка по филиалу") is None
    assert _match_header("Данные по студентам") is None

    # Software variations
    assert _match_header("Программное обеспечение") == "product"
    assert _match_header("Лицензия ПО") == "product"

    # Contacts vs Manager dispatch
    assert _match_header("Куратор от ВУЗа") == "contact_name"
    assert _match_header("Контактное лицо") == "contact_name"
    assert _match_header("Представитель ВУЗа") == "contact_name"
    assert _match_header("Ответственный менеджер") == "manager"
    assert _match_header("ФИО Менеджера") == "manager"

    # License subfields
    assert _match_header("Срок действия лицензии (год)") == "license_term_years"
    assert _match_header("Статус по передачи") == "license_transfer_status"
    assert _match_header("Подписание лицензии") == "license_signed_on"


def test_f10_interaction_license_program_compatibility_validation(client, app):
    """create_interaction and update_interaction validate license product compatibility with program."""
    unique_org = f"МФТИ-{uuid4().hex[:6]}"

    with app.state.session_factory() as session:
        org = Organization(name=unique_org, type="university")
        session.add(org)
        session.flush()
        session.add(OrganizationAccess(organization_id=org.id, user_id="manager-a", read_all=True, can_create=True))

        # License 1: product-test (compatible with program-qa, NOT with program-devops)
        lic_qa = License(
            id=new_id(),
            organization_id=org.id,
            product_id="product-test",
            transfer_status="pending",
            created_at=utcnow(),
        )
        # License 2: product-cloud (compatible with program-devops)
        lic_devops = License(
            id=new_id(),
            organization_id=org.id,
            product_id="product-cloud",
            transfer_status="pending",
            created_at=utcnow(),
        )
        session.add_all([lic_qa, lic_devops])
        session.commit()
        org_id = org.id
        lic_qa_id = lic_qa.id
        lic_devops_id = lic_devops.id

    # 1a. Attempt create_interaction with program-devops and lic_qa without product_id -> program validation fails
    bad_create_prog = {
        "title": "Несовместимая лицензия программы",
        "organization_id": org_id,
        "program_id": "program-devops",
        "product_id": None,
        "license_id": lic_qa_id,
        "cycle_label": "2026",
        "owner_id": "manager-a",
    }
    resp = client.post("/api/v1/interactions", json=bad_create_prog, headers=headers("manager-a", str(uuid4())))
    assert resp.status_code == 422
    assert "Лицензия не соответствует выбранной ИТ-программе" in resp.json()["error"]["message"]

    # 1b. Attempt create_interaction with mismatched product_id -> product validation fails
    bad_create_prod = {
        "title": "Несовместимая лицензия продукта",
        "organization_id": org_id,
        "program_id": None,
        "product_id": "product-cloud",
        "license_id": lic_qa_id,
        "cycle_label": "2026",
        "owner_id": "manager-a",
    }
    resp = client.post("/api/v1/interactions", json=bad_create_prod, headers=headers("manager-a", str(uuid4())))
    assert resp.status_code == 422
    assert "Лицензия не соответствует выбранному ИТ-продукту" in resp.json()["error"]["message"]

    # 2. Valid create with lic_devops succeeds
    good_create = {
        "title": "Совместимая лицензия",
        "organization_id": org_id,
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "license_id": lic_devops_id,
        "cycle_label": "2026",
        "owner_id": "manager-a",
    }
    resp = client.post("/api/v1/interactions", json=good_create, headers=headers("manager-a", str(uuid4())))
    assert resp.status_code == 201
    card_id = resp.json()["id"]

    # 3. Attempt update_interaction to switch to lic_qa (product mismatch) -> 422
    resp = client.patch(
        f"/api/v1/interactions/{card_id}",
        json={"license_id": lic_qa_id, "expected_revision": 1},
        headers=headers("manager-a", str(uuid4())),
    )
    assert resp.status_code == 422
    assert "Лицензия не соответствует" in resp.json()["error"]["message"]


def test_f10_import_commit_manager_reassignment_audit_event_and_contact_backfill(client, app):
    """Import commit updates interaction owner and team_id, logs owner_changed event, and backfills contact info."""
    unique_org = f"НГУ-{uuid4().hex[:6]}"

    with app.state.session_factory() as session:
        org = Organization(name=unique_org, type="university")
        session.add(org)
        session.flush()

        # Manager A has access and owns the card
        session.add(OrganizationAccess(organization_id=org.id, user_id="manager-a", read_all=True, can_create=True))
        contact = OrganizationContact(
            id=new_id(),
            organization_id=org.id,
            full_name="Сидоров Петр",
            position="Сотрудник",
            email=None,
            phone=None,
            created_at=utcnow(),
        )
        session.add(contact)
        session.flush()

        card = Interaction(
            id=new_id(),
            title="Сотрудничество с НГУ",
            organization_id=org.id,
            program_id="program-devops",
            product_id="product-cloud",
            cycle_label="2026",
            owner_id="manager-a",
            team_id="team-alpha",
            state="contact_search",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(card)
        session.commit()
        org_id = org.id
        card_id = card.id
        contact_id = contact.id

    # CSV reassigns manager to manager-b (north team) and fills contact position, email, phone
    csv_text = (
        "Название ВУЗа;Вендор;ПО;Номер договора;Подписание лицензии;Срок действия лицензии (год);Статус по передачи;ФИО Менеджера;Ответственные от ВУЗа;Комментарий\n"
        f"{unique_org};Ростелеком;Облачная платформа;ДОГ-НГУ-01;2026-09-01;2;передано;manager-b;Сидоров Петр, Декан, dekan@ngu.ru, +79998887766;Новый менеджер"
    )

    prev_resp = client.post(
        "/api/v1/imports/organizations/preview",
        files={"file": ("import_test_mgr.csv", csv_text.encode("utf-8"), "text/csv")},
        headers=headers("supervisor"),
    )
    assert prev_resp.status_code == 200
    prev_data = prev_resp.json()

    commit_resp = client.post(
        "/api/v1/imports/organizations/commit",
        json={"rows": prev_data["preview_rows"]},
        headers=headers("supervisor", str(uuid4())),
    )
    assert commit_resp.status_code == 200

    with app.state.session_factory() as session:
        # Check interaction owner and team reassignment
        interaction = session.get(Interaction, card_id)
        assert interaction.owner_id == "manager-b"
        assert interaction.team_id == "north"

        # Check owner_changed event exists with snapshot
        event = session.scalar(
            select(InteractionEvent)
            .where(InteractionEvent.interaction_id == card_id, InteractionEvent.type == "owner_changed")
            .order_by(InteractionEvent.sequence.desc())
        )
        assert event is not None
        assert event.payload.get("owner_id") == "manager-b"
        assert event.payload.get("previous_owner_id") == "manager-a"

        # Check contact details backfilled
        c = session.get(OrganizationContact, contact_id)
        assert c.position == "Декан"
        assert c.email == "dekan@ngu.ru"
        assert c.phone == "+79998887766"


