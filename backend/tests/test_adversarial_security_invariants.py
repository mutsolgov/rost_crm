"""Adversarial Security Challenger Test Suite (challenger_security_2).

Exhaustive empirical stress tests targeting 4 core security invariants:
1. Invariant 1: Complete elimination of `scope_clause` bypass across all routes,
   unauthenticated paths, catalog responses, filter injections, autocompletes, and cross-team boundaries.
2. Invariant 2: Technical administrator role strictly isolated with ZERO implicit
   access to commercial interactions unless explicitly granted in OrganizationAccess.
3. Invariant 3: Zero-oracle upload guard indistinguishability between non-existent
   and unauthorized foreign interactions across 8 attack vectors.
4. Invariant 4: Zero leakage of credentials, bearer tokens, passwords, or PII into
   exception responses, error payloads, server logs, or stdout/stderr.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import io
import json
import logging
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import (
    Attachment,
    Contract,
    Interaction,
    License,
    Organization,
    OrganizationAccess,
    OrganizationContact,
    Team,
    User,
)


@pytest.fixture
def db_session(app):
    with app.state.session_factory() as session:
        yield session


def headers(user="manager-a", key=None, auth_token=None):
    res = {}
    if user:
        res["X-Demo-User"] = user
    if key:
        res["Idempotency-Key"] = key
    if auth_token:
        res["Authorization"] = f"Bearer {auth_token}"
    return res


def create_test_card(client, user="manager-a", org_id=None, **overrides):
    if not org_id:
        org_id = "org-2" if user == "manager-b" else "org-1"
    body = {
        "title": f"Adversarial Test Card {uuid4().hex[:8]}",
        "organization_id": org_id,
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "2026-Security-Challenge",
        "owner_id": user,
    }
    body.update(overrides)
    res = client.post("/api/v1/interactions", json=body, headers=headers(user, str(uuid4())))
    assert res.status_code == 201, f"Failed to create card: {res.text}"
    return res.json()


# ==============================================================================
# CHALLENGE 1: Scope Clause Bypass Resistance
# ==============================================================================

def test_unauthenticated_requests_blocked_across_all_endpoints(client):
    """Every protected endpoint must return strict 401 UNAUTHENTICATED when called without auth."""
    card = create_test_card(client, user="manager-a")
    card_id = card["id"]
    fake_uuid = str(uuid4())

    endpoints = [
        ("GET", "/api/v1/me", None),
        ("GET", "/api/v1/catalogs", None),
        ("GET", "/api/v1/workflow", None),
        ("GET", "/api/v1/interactions", None),
        ("GET", f"/api/v1/interactions/{card_id}", None),
        ("PATCH", f"/api/v1/interactions/{card_id}", {"expected_revision": 1, "title": "Hack"}),
        ("POST", "/api/v1/interactions", {"title": "Hack", "organization_id": "org-1"}),
        ("POST", f"/api/v1/interactions/{card_id}/transitions", {"transition_code": "x", "expected_revision": 1}),
        ("POST", f"/api/v1/interactions/{card_id}/comments", {"body": "Hack", "expected_revision": 1}),
        ("POST", f"/api/v1/interactions/{card_id}/assignments", {"owner_id": "manager-a", "expected_revision": 1}),
        ("GET", "/api/v1/dashboard", None),
        ("GET", f"/api/v1/interactions/{card_id}/attachments", None),
        ("GET", f"/api/v1/interactions/{card_id}/attachments/{fake_uuid}/download", None),
        ("POST", "/api/v1/reports/snapshot", {"as_of": "2026-01-01T00:00:00Z"}),
        ("POST", "/api/v1/reports/snapshot/export", {"as_of": "2026-01-01T00:00:00Z"}),
        ("POST", "/api/v1/reports/activity", {"from_date": "2026-01-01T00:00:00Z", "to_date": "2026-02-01T00:00:00Z"}),
        ("POST", "/api/v1/reports/activity/export", {"from_date": "2026-01-01T00:00:00Z", "to_date": "2026-02-01T00:00:00Z"}),
        ("POST", "/api/v1/reports/created", {"from_date": "2026-01-01T00:00:00Z", "to_date": "2026-02-01T00:00:00Z"}),
        ("POST", "/api/v1/reports/created/export", {"from_date": "2026-01-01T00:00:00Z", "to_date": "2026-02-01T00:00:00Z"}),
        ("POST", "/api/v1/workflow/migrate/preview", {"from_version": 1, "to_version": 2, "status_mapping": {}}),
        ("POST", "/api/v1/workflow/migrate/commit", {"from_version": 1, "to_version": 2, "status_mapping": {}}),
        ("GET", "/api/v1/integrations/status", None),
        ("POST", "/api/v1/integrations/sync/lms", None),
        ("GET", "/api/v1/integrations/inbox", None),
        ("POST", f"/api/v1/integrations/inbox/{fake_uuid}/resolve", {"action": "reject"}),
        ("GET", "/api/v1/integrations/metrics", None),
    ]

    for method, path, json_body in endpoints:
        req_headers = {"Idempotency-Key": str(uuid4())}
        if method == "GET":
            resp = client.get(path, headers=req_headers)
        elif method == "POST":
            resp = client.post(path, json=json_body or {}, headers=req_headers)
        elif method == "PATCH":
            resp = client.patch(path, json=json_body or {}, headers=req_headers)
        else:
            pytest.fail(f"Unsupported method {method}")

        assert resp.status_code == 401, f"Expected 401 for unauthenticated {method} {path}, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["error"]["code"] == "UNAUTHENTICATED"


def test_inactive_and_nonexistent_users_blocked(client, db_session):
    """Users marked inactive or non-existent IDs must receive 401 UNAUTHENTICATED."""
    # 1. Non-existent user
    resp_fake = client.get("/api/v1/interactions", headers=headers("nonexistent-user-xyz"))
    assert resp_fake.status_code == 401
    assert resp_fake.json()["error"]["code"] == "UNAUTHENTICATED"

    # 2. Deactivated user
    user = db_session.get(User, "manager-a")
    original_active = user.active
    try:
        user.active = False
        db_session.commit()

        resp_deact = client.get("/api/v1/interactions", headers=headers("manager-a"))
        assert resp_deact.status_code == 401
        assert resp_deact.json()["error"]["code"] == "UNAUTHENTICATED"
    finally:
        user.active = original_active
        db_session.commit()


def test_catalogs_never_leak_foreign_organizations_or_contacts(client, db_session):
    """Manager A catalogs must ONLY contain org-1 entities; org-2 and its contacts/contracts/licenses must be excluded."""
    res_a = client.get("/api/v1/catalogs", headers=headers("manager-a"))
    assert res_a.status_code == 200
    data_a = res_a.json()

    org_ids_a = {o["id"] for o in data_a["organizations"]}
    contact_orgs_a = {c["organization_id"] for c in data_a["contacts"]}
    contract_orgs_a = {c["organization_id"] for c in data_a["contracts"]}
    license_orgs_a = {l["organization_id"] for l in data_a["licenses"]}

    assert "org-1" in org_ids_a
    assert "org-2" not in org_ids_a, "CRITICAL: org-2 leaked to manager-a in catalogs['organizations']!"
    assert "org-2" not in contact_orgs_a, "CRITICAL: org-2 contact leaked to manager-a!"
    assert "org-2" not in contract_orgs_a, "CRITICAL: org-2 contract leaked to manager-a!"
    assert "org-2" not in license_orgs_a, "CRITICAL: org-2 license leaked to manager-a!"


def test_filter_and_wildcard_probing_cannot_bypass_scope(client):
    """Adversarial query parameters and SQL wildcards cannot extract out-of-scope interactions."""
    card_a = create_test_card(client, user="manager-a", title="Card A Searchable")
    card_b = create_test_card(client, user="manager-b", title="Card B Confidential")

    # 1. Manager A filters by unauthorized organization_id=org-2 -> 422 VALIDATION_ERROR
    res_probe_org = client.get("/api/v1/interactions?organization_id=org-2", headers=headers("manager-a"))
    assert res_probe_org.status_code == 422
    assert res_probe_org.json()["error"]["code"] == "VALIDATION_ERROR"

    # 2. Manager A queries by owner_id=manager-b -> filtered out or 0 items
    res_probe_owner = client.get("/api/v1/interactions?owner_id=manager-b", headers=headers("manager-a"))
    assert res_probe_owner.status_code == 200
    items_owner = res_probe_owner.json()["items"]
    assert len(items_owner) == 0, f"Manager A should see 0 items for owner_id=manager-b, got: {items_owner}"

    # 3. Manager A attempts SQL wildcard match q=%
    res_wildcard_pct = client.get("/api/v1/interactions?q=%", headers=headers("manager-a"))
    assert res_wildcard_pct.status_code == 200
    for item in res_wildcard_pct.json()["items"]:
        assert item["owner_id"] == "manager-a"
        assert item["organization_id"] != "org-2"

    # 4. Manager A attempts SQL injection string q=' OR '1'='1
    res_sqli = client.get("/api/v1/interactions?q=' OR '1'='1", headers=headers("manager-a"))
    assert res_sqli.status_code == 200
    for item in res_sqli.json()["items"]:
        assert item["owner_id"] == "manager-a"
        assert item["organization_id"] != "org-2"


def test_cross_team_supervisor_isolation(client, db_session):
    """Supervisor cannot see or modify interactions of other teams when not explicitly granted."""
    # Create supervisor for another team: "south"
    sup_south = User(
        id="supervisor-south",
        keycloak_subject=str(uuid4()),
        name="Руководитель Юг",
        role="supervisor",
        team_id="south",
        permissions=[],
        active=True,
    )
    db_session.merge(sup_south)
    # Ensure no OrganizationAccess grants for supervisor-south on org-1
    existing_grant = db_session.get(OrganizationAccess, ("supervisor-south", "org-1"))
    if existing_grant:
        db_session.delete(existing_grant)
    db_session.commit()

    # Manager A (team north) creates interaction in org-1
    card_a = create_test_card(client, user="manager-a", org_id="org-1", title="Team North Card")
    card_a_id = card_a["id"]

    # Supervisor South (team south) attempts direct access -> 404 NOT_FOUND
    res_sup = client.get(f"/api/v1/interactions/{card_a_id}", headers=headers("supervisor-south"))
    assert res_sup.status_code == 404
    assert res_sup.json()["error"]["code"] == "NOT_FOUND"

    # Supervisor South attempts reassignment on foreign team card -> 404 NOT_FOUND
    res_reassign = client.post(
        f"/api/v1/interactions/{card_a_id}/assignments",
        json={"expected_revision": 1, "owner_id": "manager-a", "reason": "Hostile takeover"},
        headers=headers("supervisor-south", str(uuid4())),
    )
    assert res_reassign.status_code == 404
    assert res_reassign.json()["error"]["code"] == "NOT_FOUND"


def test_manager_cannot_execute_workflow_migration_or_integrations_manage(client):
    """Manager role must receive 403 FORBIDDEN when attempting privileged administrative endpoints."""
    # 1. Workflow migration preview
    res_wf_prev = client.post(
        "/api/v1/workflow/migrate/preview",
        json={"from_version": 1, "to_version": 2, "status_mapping": {"contact_search": "contact_search"}},
        headers=headers("manager-a"),
    )
    assert res_wf_prev.status_code == 403
    assert res_wf_prev.json()["error"]["code"] == "FORBIDDEN"

    # 2. Workflow migration commit
    res_wf_commit = client.post(
        "/api/v1/workflow/migrate/commit",
        json={"from_version": 1, "to_version": 2, "status_mapping": {"contact_search": "contact_search"}},
        headers=headers("manager-a", str(uuid4())),
    )
    assert res_wf_commit.status_code == 403
    assert res_wf_commit.json()["error"]["code"] == "FORBIDDEN"

    # 3. Integrations status
    res_int_status = client.get("/api/v1/integrations/status", headers=headers("manager-a"))
    assert res_int_status.status_code == 403
    assert res_int_status.json()["error"]["code"] == "FORBIDDEN"

    # 4. Integrations inbox
    res_int_inbox = client.get("/api/v1/integrations/inbox", headers=headers("manager-a"))
    assert res_int_inbox.status_code == 403
    assert res_int_inbox.json()["error"]["code"] == "FORBIDDEN"


# ==============================================================================
# CHALLENGE 2: Administrator Commercial Data Isolation
# ==============================================================================

def test_administrator_has_zero_implicit_access_to_commercial_interactions(client, db_session):
    """Verify administrator cannot view interactions, dashboard counts, or catalogs without OrganizationAccess."""
    card_a = create_test_card(client, user="manager-a", title="Commercial Card A")
    card_b = create_test_card(client, user="manager-b", title="Commercial Card B")

    # Ensure admin has no OrganizationAccess
    admin_grants = db_session.scalars(
        select(OrganizationAccess).where(OrganizationAccess.user_id == "administrator")
    ).all()
    for g in admin_grants:
        db_session.delete(g)
    db_session.commit()

    # 1. GET /interactions -> 0 items
    r_list = client.get("/api/v1/interactions", headers=headers("administrator"))
    assert r_list.status_code == 200
    assert r_list.json()["total"] == 0
    assert r_list.json()["items"] == []

    # 2. GET /interactions/{id} -> 404
    assert client.get(f"/api/v1/interactions/{card_a['id']}", headers=headers("administrator")).status_code == 404
    assert client.get(f"/api/v1/interactions/{card_b['id']}", headers=headers("administrator")).status_code == 404

    # 3. GET /dashboard -> 0 interactions
    r_dash = client.get("/api/v1/dashboard", headers=headers("administrator"))
    assert r_dash.status_code == 200
    dash_data = r_dash.json()
    assert dash_data["total_interactions"] == 0
    assert dash_data["total_organizations"] == 0
    assert dash_data["recent_events"] == []

    # 4. Reports (snapshot, activity, created) -> 0 rows
    r_snap = client.post(
        "/api/v1/reports/snapshot",
        json={"as_of": "2027-01-01T00:00:00Z"},
        headers=headers("administrator"),
    )
    assert r_snap.status_code == 200
    assert r_snap.json()["total_interactions"] == 0
    assert r_snap.json()["rows"] == []

    r_act = client.post(
        "/api/v1/reports/activity",
        json={"from_date": "2025-01-01T00:00:00Z", "to_date": "2027-01-01T00:00:00Z"},
        headers=headers("administrator"),
    )
    assert r_act.status_code == 200
    assert r_act.json()["total_transitions"] == 0
    assert r_act.json()["rows"] == []

    r_created = client.post(
        "/api/v1/reports/created",
        json={"from_date": "2025-01-01T00:00:00Z", "to_date": "2027-01-01T00:00:00Z"},
        headers=headers("administrator"),
    )
    assert r_created.status_code == 200
    assert len(r_created.json()["rows"]) == 0

    # 5. Catalogs -> empty organizations, contacts, contracts, licenses
    r_cat = client.get("/api/v1/catalogs", headers=headers("administrator"))
    assert r_cat.status_code == 200
    cat_data = r_cat.json()
    assert cat_data["organizations"] == []
    assert cat_data["contacts"] == []
    assert cat_data["contracts"] == []
    assert cat_data["licenses"] == []


def test_administrator_scoped_when_explicitly_granted(client, db_session):
    """When granted read_all=True on org-1, admin sees org-1 interactions, but STILL receives 404 for org-2."""
    card_a = create_test_card(client, user="manager-a", org_id="org-1")
    card_b = create_test_card(client, user="manager-b", org_id="org-2")

    # Grant admin access to org-1 ONLY
    grant = OrganizationAccess(user_id="administrator", organization_id="org-1", can_create=True, read_all=True)
    db_session.merge(grant)
    db_session.commit()

    try:
        # Admin can access card A (org-1)
        res_a = client.get(f"/api/v1/interactions/{card_a['id']}", headers=headers("administrator"))
        assert res_a.status_code == 200
        assert res_a.json()["id"] == card_a["id"]

        # Admin CANNOT access card B (org-2) -> Strict 404
        res_b = client.get(f"/api/v1/interactions/{card_b['id']}", headers=headers("administrator"))
        assert res_b.status_code == 404
        assert res_b.json()["error"]["code"] == "NOT_FOUND"

        # Admin catalogs contain org-1, but strictly NOT org-2
        res_cat = client.get("/api/v1/catalogs", headers=headers("administrator"))
        assert res_cat.status_code == 200
        cat_orgs = {o["id"] for o in res_cat.json()["organizations"]}
        assert "org-1" in cat_orgs
        assert "org-2" not in cat_orgs
    finally:
        # Cleanup grant
        existing = db_session.get(OrganizationAccess, ("administrator", "org-1"))
        if existing:
            db_session.delete(existing)
            db_session.commit()


# ==============================================================================
# CHALLENGE 3: Zero-Oracle Upload Guard Robustness
# ==============================================================================

def test_zero_oracle_upload_guard_indistinguishable_oracle(client):
    """Verify that uploading to an unauthorized foreign card is completely indistinguishable
    from uploading to a non-existent card, regardless of malicious payload, file size, or extension.
    """
    card_b = create_test_card(client, user="manager-b", title="Target Foreign Card")
    target_id = card_b["id"]
    ghost_id = str(uuid4())

    attack_payloads = [
        ("malware.exe", b"MZ\x90\x00" + b"A" * 100, "application/x-dosexec", "executable binary"),
        ("script.sh", b"#!/bin/bash\nrm -rf /", "application/x-sh", "shell script"),
        ("fake.pdf", b"NOT_A_REAL_PDF_HEADER", "application/pdf", "corrupted magic bytes"),
        ("null.pdf\x00.exe", b"%PDF-1.4\nvalid", "application/pdf", "null byte poisoning"),
        ("../../../etc/passwd", b"%PDF-1.4\nvalid", "application/pdf", "path traversal"),
        ("huge.pdf", b"%PDF-1.4\n" + b"0" * (26_214_400 + 100), "application/pdf", "oversized >25MB"),
        ("clean.pdf", b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>%%EOF", "application/pdf", "legitimate pdf"),
        ("clean.xlsx", b"PK\x03\x04\x14\x00\x00\x00" + b"\x00" * 100, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "legitimate xlsx"),
    ]

    for fname, payload_bytes, mime, description in attack_payloads:
        # 1. Target: Foreign Card (Manager A attacking Manager B)
        resp_foreign = client.post(
            f"/api/v1/interactions/{target_id}/attachments",
            files={"file": (fname, payload_bytes, mime)},
            headers=headers("manager-a"),
        )
        # 2. Baseline: Completely non-existent card
        resp_ghost = client.post(
            f"/api/v1/interactions/{ghost_id}/attachments",
            files={"file": (fname, payload_bytes, mime)},
            headers=headers("manager-a"),
        )

        assert resp_foreign.status_code == 404, (
            f"Oracle leak on {description}! Expected 404, got {resp_foreign.status_code}: {resp_foreign.text}"
        )
        assert resp_ghost.status_code == 404

        json_foreign = resp_foreign.json()
        json_ghost = resp_ghost.json()

        assert json_foreign["error"]["code"] == "NOT_FOUND"
        assert json_ghost["error"]["code"] == "NOT_FOUND"
        assert json_foreign["error"]["message"] == json_ghost["error"]["message"]


# ==============================================================================
# CHALLENGE 4: Credential and PII Leakage Resistance
# ==============================================================================

def test_exception_handler_masks_all_internals_and_never_leaks_pii(client):
    """Triggering errors (404, 422, 409, 500) must return uniform error envelopes
    without tracebacks, file paths, SQL statements, or reflected credentials.
    """
    secret_token = "secret-token-abcdef1234567890"

    # 1. Error on invalid JSON with sensitive token in headers
    resp_bad_json = client.post(
        "/api/v1/interactions",
        content="INVALID JSON BODY {{{",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {secret_token}", "X-Demo-User": "manager-a"},
    )
    assert resp_bad_json.status_code in (400, 422)
    assert secret_token not in resp_bad_json.text
    assert "Traceback" not in resp_bad_json.text
    assert "File \"" not in resp_bad_json.text

    # 2. 404 error envelope format
    resp_404 = client.get(f"/api/v1/interactions/{uuid4()}", headers=headers("manager-a"))
    assert resp_404.status_code == 404
    data_404 = resp_404.json()
    assert set(data_404.keys()) == {"error"}
    assert {"code", "message", "request_id"}.issubset(set(data_404["error"].keys()))

    # 3. Check health ready DB failure masking
    # Even if DB connection were broken, /health/ready masks detail with 'База данных недоступна.'
    resp_ready = client.get("/health/ready")
    assert resp_ready.status_code in (200, 503)
    if resp_ready.status_code == 503:
        assert resp_ready.json() == {"error": {"code": "NOT_READY", "message": "База данных недоступна."}}


def test_user_model_has_no_password_field_in_database(db_session):
    """Verify that User model does not persist passwords or credentials in CRM DB."""
    from sqlalchemy import inspect
    mapper = inspect(User)
    column_names = [c.key for c in mapper.columns]
    forbidden_columns = ["password", "password_hash", "secret", "token", "hashed_password"]
    for col in forbidden_columns:
        assert col not in column_names, f"CRITICAL: User model contains forbidden credential column '{col}'!"


def test_manager_cannot_create_card_for_another_manager_or_in_unauthorized_org(client):
    """Manager A cannot forge ownership to Manager B or create card in unauthorized org-2."""
    # 1. Spoof owner_id
    body_spoof = {
        "title": "Card with Spoofed Owner",
        "organization_id": "org-1",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "2026-Spoof",
        "owner_id": "manager-b",
    }
    res_spoof = client.post("/api/v1/interactions", json=body_spoof, headers=headers("manager-a", str(uuid4())))
    assert res_spoof.status_code == 403
    assert res_spoof.json()["error"]["code"] == "FORBIDDEN"

    # 2. Unauthorized organization_id
    body_unauth_org = {
        "title": "Card in Unauthorized Org",
        "organization_id": "org-2",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "2026-Spoof",
        "owner_id": "manager-a",
    }
    res_org = client.post("/api/v1/interactions", json=body_unauth_org, headers=headers("manager-a", str(uuid4())))
    assert res_org.status_code == 404
    assert res_org.json()["error"]["code"] == "NOT_FOUND"


def test_cross_interaction_attachment_download_prevented(client):
    """Manager A owning two cards cannot download Card 1's attachment via Card 2's URL (Cross-card IDOR)."""
    card_1 = create_test_card(client, user="manager-a", title="Card 1")
    card_2 = create_test_card(client, user="manager-a", title="Card 2")

    fake_pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>%%EOF"
    upload_res = client.post(
        f"/api/v1/interactions/{card_1['id']}/attachments",
        files={"file": ("doc1.pdf", fake_pdf, "application/pdf")},
        headers=headers("manager-a"),
    )
    assert upload_res.status_code == 201
    att_1_id = upload_res.json()["id"]

    # Valid download via Card 1 -> 200 OK
    res_valid = client.get(
        f"/api/v1/interactions/{card_1['id']}/attachments/{att_1_id}/download",
        headers=headers("manager-a"),
    )
    assert res_valid.status_code == 200

    # Cross-card download via Card 2 -> 404 NOT_FOUND!
    res_cross = client.get(
        f"/api/v1/interactions/{card_2['id']}/attachments/{att_1_id}/download",
        headers=headers("manager-a"),
    )
    assert res_cross.status_code == 404
    assert res_cross.json()["error"]["code"] == "NOT_FOUND"


def test_server_logs_and_stdout_never_echo_passwords_or_auth_tokens(client, caplog, capsys):
    """Ensure that execution of API calls leaves no traces of bearer tokens or secrets in logs or stdout."""
    secret_token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.sensitive_payload_data.signature"

    with caplog.at_level(logging.DEBUG):
        client.get("/api/v1/interactions", headers={"Authorization": f"Bearer {secret_token}"})
        client.get(f"/api/v1/interactions/{uuid4()}", headers={"Authorization": f"Bearer {secret_token}"})
        client.post(
            "/api/v1/interactions",
            content="CORRUPTED_PAYLOAD",
            headers={"Authorization": f"Bearer {secret_token}", "Content-Type": "application/json"},
        )

    captured = capsys.readouterr()
    # Check stdout & stderr
    assert secret_token not in captured.out
    assert secret_token not in captured.err

    # Check logger records
    for record in caplog.records:
        assert secret_token not in record.message


def test_team_foreign_key_referential_integrity_and_preseed(db_session):
    """TASK-D06: Verify pre-seeded teams and FK constraints on users and interactions."""
    # 1. Base teams are pre-seeded
    for team_id in ("north", "south", "team-alpha", "team-beta"):
        team = db_session.get(Team, team_id)
        assert team is not None, f"Team '{team_id}' must be pre-seeded"
        assert team.name

    # 2. User with non-existent team_id fails under FK integrity (arbitrary string, empty, whitespace)
    for bad_team in ("nonexistent-team-id", "", "   "):
        invalid_user = User(
            id=f"user-fk-test-{uuid4()}",
            keycloak_subject=str(uuid4()),
            name="Invalid Team User",
            role="manager",
            team_id=bad_team,
            permissions=[],
            active=True,
        )
        db_session.add(invalid_user)
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    # 3. Interaction with non-existent team_id fails under FK integrity (arbitrary string, empty, whitespace)
    for bad_team in ("nonexistent-team-id", "", "   "):
        invalid_ix = Interaction(
            id=f"ix-fk-test-{uuid4()}",
            title="Invalid Team Interaction",
            organization_id="org-1",
            owner_id="manager-a",
            cycle_label="2026",
            state="contact_search",
            team_id=bad_team,
        )
        db_session.add(invalid_ix)
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    # 4. Nullable team_id=None succeeds for both User and Interaction
    null_user = User(
        id=f"user-null-team-{uuid4()}",
        keycloak_subject=str(uuid4()),
        name="Null Team User",
        role="administrator",
        team_id=None,
        permissions=[],
        active=True,
    )
    db_session.add(null_user)
    db_session.flush()

    null_ix = Interaction(
        id=f"ix-null-team-{uuid4()}",
        title="Null Team Interaction",
        organization_id="org-1",
        owner_id="manager-a",
        cycle_label="2026",
        state="contact_search",
        team_id=None,
    )
    db_session.add(null_ix)
    db_session.flush()
    db_session.rollback()

    # 5. Duplicate Team ID raises IntegrityError
    dup_team = Team(id="north", name="Duplicate North Team")
    db_session.add(dup_team)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    # 6. Deleting a team triggers ON DELETE SET NULL on user and interaction
    temp_team = Team(id=f"team-temp-{uuid4()}", name="Temporary Team")
    db_session.add(temp_team)
    db_session.flush()

    user_with_temp_team = User(
        id=f"user-setnull-{uuid4()}",
        keycloak_subject=str(uuid4()),
        name="Set Null User",
        role="manager",
        team_id=temp_team.id,
        permissions=[],
        active=True,
    )
    ix_with_temp_team = Interaction(
        id=f"ix-setnull-{uuid4()}",
        title="Set Null Interaction",
        organization_id="org-1",
        owner_id="manager-a",
        cycle_label="2026",
        state="contact_search",
        team_id=temp_team.id,
    )
    db_session.add_all([user_with_temp_team, ix_with_temp_team])
    db_session.commit()

    db_session.delete(temp_team)
    db_session.commit()

    db_session.refresh(user_with_temp_team)
    db_session.refresh(ix_with_temp_team)
    assert user_with_temp_team.team_id is None
    assert ix_with_temp_team.team_id is None


def test_cross_team_reassignment_and_null_team_isolation(client, db_session):
    """TASK-D06: Interaction reassignment synchronizes team_id; null team supervisor cannot leak unassigned managers."""
    from app.seed import seed_database

    # 1. Seed idempotency: re-running seed_database does not raise duplicate key errors on teams
    seed_database(db_session)
    db_session.flush()

    # 2. Supervisor with team_id=None must not leak managers who have team_id=None in catalogs
    sup_none = User(
        id=f"sup-null-{uuid4()}",
        keycloak_subject=str(uuid4()),
        name="Null Team Supervisor",
        role="supervisor",
        team_id=None,
        permissions=[],
        active=True,
    )
    mgr_none = User(
        id=f"mgr-null-{uuid4()}",
        keycloak_subject=str(uuid4()),
        name="Null Team Manager",
        role="manager",
        team_id=None,
        permissions=[],
        active=True,
    )
    db_session.add_all([sup_none, mgr_none])
    db_session.commit()

    res_cat = client.get("/api/v1/catalogs", headers=headers(sup_none.id))
    assert res_cat.status_code == 200
    owner_ids_in_cat = [o["id"] for o in res_cat.json()["owners"]]
    assert mgr_none.id not in owner_ids_in_cat, "Unassigned manager must not leak into catalog of teamless supervisor"

    # 3. Cross-team reassignment updates Interaction.team_id and preserves supervisor team isolation
    mgr_south = User(
        id=f"mgr-south-{uuid4()}",
        keycloak_subject=str(uuid4()),
        name="Manager South",
        role="manager",
        team_id="south",
        permissions=[],
        active=True,
    )
    sup_south = User(
        id=f"sup-south-{uuid4()}",
        keycloak_subject=str(uuid4()),
        name="Supervisor South",
        role="supervisor",
        team_id="south",
        permissions=[],
        active=True,
    )
    sup_north_strict = User(
        id=f"sup-north-{uuid4()}",
        keycloak_subject=str(uuid4()),
        name="Supervisor North Strict",
        role="supervisor",
        team_id="north",
        permissions=[],
        active=True,
    )
    admin_user = User(
        id=f"admin-assign-{uuid4()}",
        keycloak_subject=str(uuid4()),
        name="Admin Assigner",
        role="administrator",
        team_id=None,
        permissions=["interactions.assign"],
        active=True,
    )
    admin_grant = OrganizationAccess(
        user_id=admin_user.id,
        organization_id="org-1",
        can_create=True,
        read_all=True,
    )
    db_session.add_all([mgr_south, sup_south, sup_north_strict, admin_user])
    db_session.flush()
    db_session.add(admin_grant)
    db_session.commit()

    # Manager A (team north) creates interaction
    card_north = create_test_card(client, user="manager-a", org_id="org-1", title="Team North Card for Transfer")
    card_id = card_north["id"]

    # Before transfer: sup_north_strict can access it, sup_south gets 404 NOT_FOUND
    res_sup_n = client.get(f"/api/v1/interactions/{card_id}", headers=headers(sup_north_strict.id))
    assert res_sup_n.status_code == 200

    res_sup_s = client.get(f"/api/v1/interactions/{card_id}", headers=headers(sup_south.id))
    assert res_sup_s.status_code == 404

    # Admin reassigns to mgr_south (team south)
    res_assign = client.post(
        f"/api/v1/interactions/{card_id}/assignments",
        json={"expected_revision": 1, "owner_id": mgr_south.id, "reason": "Transfer to Team South"},
        headers=headers(admin_user.id, str(uuid4())),
    )
    assert res_assign.status_code == 200

    # Verify interaction.team_id was updated in the DB
    ix_record = db_session.get(Interaction, card_id)
    assert ix_record.owner_id == mgr_south.id
    assert ix_record.team_id == "south"

    # After transfer: sup_south can access it, sup_north_strict gets 404 NOT_FOUND!
    res_sup_s_after = client.get(f"/api/v1/interactions/{card_id}", headers=headers(sup_south.id))
    assert res_sup_s_after.status_code == 200

    res_sup_n_after = client.get(f"/api/v1/interactions/{card_id}", headers=headers(sup_north_strict.id))
    assert res_sup_n_after.status_code == 404

    # 4. Teamless supervisor cannot assign interactions (blocked by team scope or allowed_owner)
    res_assign_teamless = client.post(
        f"/api/v1/interactions/{card_id}/assignments",
        json={"expected_revision": 2, "owner_id": mgr_south.id, "reason": "Teamless takeover"},
        headers=headers(sup_none.id, str(uuid4())),
    )
    assert res_assign_teamless.status_code in (403, 404)
    assert res_assign_teamless.json()["error"]["code"] in ("FORBIDDEN", "NOT_FOUND")


def test_concurrent_team_deletion_and_referential_integrity(app):
    """TASK-D06: Multi-threaded concurrent user creation and team deletion under PRAGMA foreign_keys=ON."""
    from sqlalchemy.orm import Session
    from sqlalchemy.exc import IntegrityError

    team_id = f"team-race-{uuid4().hex[:8]}"
    with app.state.session_factory() as session:
        team = Team(id=team_id, name="Race Team")
        session.add(team)
        session.commit()

    def user_worker(idx):
        try:
            with app.state.session_factory() as session:
                u = User(
                    id=f"u-race-{uuid4()}",
                    keycloak_subject=str(uuid4()),
                    name=f"Race User {idx}",
                    role="manager",
                    team_id=team_id,
                    permissions=[],
                    active=True,
                )
                session.add(u)
                session.commit()
                return "created"
        except IntegrityError:
            return "integrity_error"

    def delete_worker():
        try:
            with app.state.session_factory() as session:
                t = session.get(Team, team_id)
                if t:
                    session.delete(t)
                    session.commit()
                    return "deleted"
                return "not_found"
        except Exception as e:
            return f"error:{type(e).__name__}"

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(user_worker, i) for i in range(16)]
        futures.append(executor.submit(delete_worker))
        outcomes = [f.result() for f in futures]

    assert "deleted" in outcomes

    # Verify that all users that were successfully created have team_id set to NULL by ON DELETE SET NULL
    with app.state.session_factory() as session:
        race_users = list(session.scalars(select(User).where(User.name.like("Race User %"))))
        for u in race_users:
            assert u.team_id is None, f"User {u.id} has team_id={u.team_id}, expected None after team deletion!"



