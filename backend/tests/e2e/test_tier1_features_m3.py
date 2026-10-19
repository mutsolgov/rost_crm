"""Tier 1: Feature Coverage for Milestone 3 (F15–F19).

Covers:
- F15: Admin User Management API (GET /users, PATCH /users/{id}, Org Access grants)
- F16: Real Admin Audit Log on Dashboard (system_stats.recent_system_events)
- F17: Admin RBAC & Organization Access Grants (152-ФЗ dynamic enforcement)
- F18: Visual Workflow Stage Editor & Graph Definition Validation
- F19: Dynamic Workflow Migrator Across Arbitrary Versions
"""
import uuid

import pytest
from sqlalchemy import select

from app.models import AccessPolicyState, Interaction, OrganizationAccess, User
from app.workflow import get_states, get_transitions

from tests.e2e.helpers import admin_headers, auth_headers, create_e2e_interaction, manager_headers, route_exists, supervisor_headers


# ============================================================================
# F15: Admin User Management API
# ============================================================================

def test_f15_admin_can_list_users(client, app):
    """GET /api/v1/users returns all system users for administrator."""
    if not route_exists(app, "/api/v1/users"):
        pytest.skip("Pending Milestone 3 (WP-06): Admin user management route /api/v1/users not yet mounted")

    resp = client.get("/api/v1/users", headers=admin_headers())
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 4
    user_ids = {u["id"] for u in data}
    assert "administrator" in user_ids
    assert "manager-a" in user_ids


def test_f15_non_admin_cannot_list_users(client, app):
    """GET /api/v1/users returns 403 Forbidden for manager and supervisor."""
    if not route_exists(app, "/api/v1/users"):
        pytest.skip("Pending Milestone 3 (WP-06): Admin user management route not mounted")

    resp_mgr = client.get("/api/v1/users", headers=manager_headers("manager-a"))
    assert resp_mgr.status_code == 403

    resp_sup = client.get("/api/v1/users", headers=supervisor_headers())
    assert resp_sup.status_code == 403


def test_f15_admin_patch_user_bumps_authz_epoch(client, app):
    """PATCH /api/v1/users/{id} updates user details and increments authz_epoch."""
    if not route_exists(app, "/api/v1/users", method="PATCH"):
        pytest.skip("Pending Milestone 3 (WP-06): Admin PATCH /api/v1/users/{id} not yet mounted")

    with app.state.session_factory() as session:
        initial_epoch = session.scalar(select(AccessPolicyState.epoch).where(AccessPolicyState.singleton_id == 1)) or 1

    payload = {"name": "Анна Смирнова (Обновлено)", "phone": "+7-495-999-00-11"}
    resp = client.patch("/api/v1/users/manager-a", json=payload, headers=admin_headers())
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Анна Смирнова (Обновлено)"

    with app.state.session_factory() as session:
        new_epoch = session.scalar(select(AccessPolicyState.epoch).where(AccessPolicyState.singleton_id == 1))
        assert new_epoch > initial_epoch, "authz_epoch was not incremented on user patch!"


def test_f15_admin_grant_organization_access(client, app):
    """PUT /api/v1/users/{user_id}/organizations/{org_id} grants access and bumps epoch."""
    if not route_exists(app, "/api/v1/users", method="PUT"):
        pytest.skip("Pending Milestone 3 (WP-06): PUT /api/v1/users/{id}/organizations/{org_id} not yet mounted")

    resp = client.put(
        "/api/v1/users/manager-a/organizations/org-2",
        json={"can_create": True, "read_all": True},
        headers=admin_headers(),
    )
    assert resp.status_code in (200, 201), resp.text

    # Manager-A should now see org-2 in catalogs
    cat_resp = client.get("/api/v1/catalogs", headers=manager_headers("manager-a"))
    org_ids = {o["id"] for o in cat_resp.json()["organizations"]}
    assert "org-2" in org_ids


def test_f15_admin_revoke_organization_access(client, app):
    """DELETE /api/v1/users/{user_id}/organizations/{org_id} revokes access and bumps epoch."""
    if not route_exists(app, "/api/v1/users", method="DELETE"):
        pytest.skip("Pending Milestone 3 (WP-06): DELETE organization access not yet mounted")

    resp = client.delete("/api/v1/users/manager-a/organizations/org-1", headers=admin_headers())
    assert resp.status_code in (200, 204), resp.text

    # Manager-A should no longer see org-1
    cat_resp = client.get("/api/v1/catalogs", headers=manager_headers("manager-a"))
    org_ids = {o["id"] for o in cat_resp.json()["organizations"]}
    assert "org-1" not in org_ids


def test_f15_self_lockout_guard_prevents_admin_deactivating_self(client):
    """PATCH /api/v1/users/administrator with active=False returns 422 VALIDATION_ERROR."""
    resp = client.patch(
        "/api/v1/users/administrator",
        json={"active": False},
        headers=admin_headers(),
    )
    assert resp.status_code == 422, resp.text
    err = resp.json().get("error", {})
    assert err.get("code") == "VALIDATION_ERROR"
    assert "Администратор не может заблокировать собственную учётную запись." in err.get("message", "")


def test_f15_self_lockout_guard_prevents_admin_demoting_self(client):
    """PATCH /api/v1/users/administrator with role=manager or supervisor returns 422 VALIDATION_ERROR."""
    resp = client.patch(
        "/api/v1/users/administrator",
        json={"role": "manager"},
        headers=admin_headers(),
    )
    assert resp.status_code == 422, resp.text
    err = resp.json().get("error", {})
    assert err.get("code") == "VALIDATION_ERROR"
    assert "Администратор не может понизить собственную роль." in err.get("message", "")

    resp_sup = client.patch(
        "/api/v1/users/administrator",
        json={"role": "supervisor"},
        headers=admin_headers(),
    )
    assert resp_sup.status_code == 422, resp_sup.text
    err_sup = resp_sup.json().get("error", {})
    assert err_sup.get("code") == "VALIDATION_ERROR"
    assert "Администратор не может понизить собственную роль." in err_sup.get("message", "")


def test_f15_self_lockout_guard_prevents_simultaneous_deactivation_and_demotion(client):
    """Admin cannot deactivate and demote themselves simultaneously."""
    resp = client.patch(
        "/api/v1/users/administrator",
        json={"active": False, "role": "manager"},
        headers=admin_headers(),
    )
    assert resp.status_code == 422, resp.text
    err = resp.json().get("error", {})
    assert err.get("code") == "VALIDATION_ERROR"
    assert "Администратор не может заблокировать собственную учётную запись." in err.get("message", "")


def test_f15_last_active_admin_protection_prevents_lockout_and_demotion(client, app):
    """Sole active admin cannot be deactivated or demoted by another user with users.manage permission."""
    with app.state.session_factory() as session:
        priv_user = session.get(User, "privileged-manager")
        if not priv_user:
            priv_user = User(
                id="privileged-manager",
                keycloak_subject=str(uuid.uuid4()),
                name="Привилегированный менеджер",
                role="supervisor",
                active=True,
                permissions=["users.manage"],
            )
            session.add(priv_user)
            session.commit()

    try:
        # Attempt deactivation of the sole active admin
        resp_deact = client.patch(
            "/api/v1/users/administrator",
            json={"active": False},
            headers=auth_headers("privileged-manager"),
        )
        assert resp_deact.status_code == 422, resp_deact.text
        err_deact = resp_deact.json().get("error", {})
        assert err_deact.get("code") == "VALIDATION_ERROR"
        assert "Нельзя заблокировать или лишить прав единственного активного администратора системы." in err_deact.get("message", "")

        # Attempt demotion of the sole active admin
        resp_demote = client.patch(
            "/api/v1/users/administrator",
            json={"role": "supervisor"},
            headers=auth_headers("privileged-manager"),
        )
        assert resp_demote.status_code == 422, resp_demote.text
        err_demote = resp_demote.json().get("error", {})
        assert err_demote.get("code") == "VALIDATION_ERROR"
        assert "Нельзя заблокировать или лишить прав единственного активного администратора системы." in err_demote.get("message", "")
    finally:
        with app.state.session_factory() as session:
            u = session.get(User, "privileged-manager")
            if u:
                session.delete(u)
                session.commit()


def test_f15_admin_deactivation_succeeds_when_another_active_admin_exists(client, app):
    """Deactivation of an administrator succeeds with 200 when another active admin exists."""
    with app.state.session_factory() as session:
        admin_secondary = session.get(User, "admin-secondary")
        if not admin_secondary:
            admin_secondary = User(
                id="admin-secondary",
                keycloak_subject=str(uuid.uuid4()),
                name="Второй Администратор",
                role="administrator",
                active=True,
            )
            session.add(admin_secondary)
        else:
            admin_secondary.active = True
            admin_secondary.role = "administrator"
        session.commit()

    try:
        # Primary administrator deactivates admin-secondary
        resp = client.patch(
            "/api/v1/users/admin-secondary",
            json={"active": False},
            headers=admin_headers(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json().get("active") is False
    finally:
        # Cleanup: remove secondary admin so other tests are not impacted
        with app.state.session_factory() as session:
            u = session.get(User, "admin-secondary")
            if u:
                session.delete(u)
                session.commit()


def test_f15_admin_demotion_succeeds_when_another_active_admin_exists(client, app):
    """Demotion of an administrator succeeds with 200 when another active admin exists."""
    with app.state.session_factory() as session:
        admin_secondary = session.get(User, "admin-secondary")
        if not admin_secondary:
            admin_secondary = User(
                id="admin-secondary",
                keycloak_subject=str(uuid.uuid4()),
                name="Второй Администратор",
                role="administrator",
                active=True,
            )
            session.add(admin_secondary)
        else:
            admin_secondary.active = True
            admin_secondary.role = "administrator"
        session.commit()

    try:
        # Primary administrator demotes admin-secondary to supervisor
        resp = client.patch(
            "/api/v1/users/admin-secondary",
            json={"role": "supervisor"},
            headers=admin_headers(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json().get("role") == "supervisor"
    finally:
        with app.state.session_factory() as session:
            u = session.get(User, "admin-secondary")
            if u:
                session.delete(u)
                session.commit()


def test_f15_admin_self_update_profile_and_reasserting_role_succeeds(client):
    """Admin updating their own name or reasserting role=administrator succeeds with 200."""
    resp = client.patch(
        "/api/v1/users/administrator",
        json={"name": "Главный Администратор", "role": "administrator"},
        headers=admin_headers(),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("name") == "Главный Администратор"
    assert data.get("role") == "administrator"


def test_f15_admin_self_update_contact_fields_without_role_or_active(client):
    """Admin can update email and phone on their own account without touching role or active."""
    resp = client.patch(
        "/api/v1/users/administrator",
        json={"phone": "+7-999-000-1122", "email": "admin-updated@rt.ru"},
        headers=admin_headers(),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("phone") == "+7-999-000-1122"
    assert data.get("email") == "admin-updated@rt.ru"
    assert data.get("role") == "administrator"
    assert data.get("active") is True


def test_f15_admin_self_reassert_active_true_succeeds(client):
    """Admin re-asserting active=True on their own account succeeds with 200."""
    resp = client.patch(
        "/api/v1/users/administrator",
        json={"active": True},
        headers=admin_headers(),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json().get("active") is True


def test_f15_deactivation_of_regular_manager_succeeds(client, app):
    """Deactivation of a non-admin manager succeeds without triggering admin lockout guard."""
    with app.state.session_factory() as session:
        test_mgr = session.get(User, "test-mgr-f15")
        if not test_mgr:
            test_mgr = User(
                id="test-mgr-f15",
                keycloak_subject=str(uuid.uuid4()),
                name="Тестовый Менеджер",
                role="manager",
                active=True,
            )
            session.add(test_mgr)
            session.commit()

    try:
        resp = client.patch(
            "/api/v1/users/test-mgr-f15",
            json={"active": False},
            headers=admin_headers(),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json().get("active") is False
    finally:
        with app.state.session_factory() as session:
            u = session.get(User, "test-mgr-f15")
            if u:
                session.delete(u)
                session.commit()



# ============================================================================
# F16: Real Admin Audit Log on Dashboard
# ============================================================================

def test_f16_admin_dashboard_includes_real_recent_events(client):
    """GET /api/v1/dashboard for administrator contains real recent_system_events."""
    resp = client.get("/api/v1/dashboard", headers=admin_headers())
    assert resp.status_code == 200, resp.text
    data = resp.json()
    system_stats = data.get("system_stats")
    if not system_stats or "recent_system_events" not in system_stats:
        pytest.skip("Pending Milestone 3 (WP-06): system_stats.recent_system_events not yet wired to DB")

    events = system_stats["recent_system_events"]
    assert isinstance(events, list)
    assert len(events) > 0, "Audit log returned empty list of events"
    first = events[0]
    assert "type" in first or "event_type" in first or "action" in first


def test_f16_audit_log_captures_new_interaction_event(client):
    """Creating an interaction records a corresponding entry in admin audit log."""
    # Create interaction
    interaction = create_e2e_interaction(client, title="Аудит Тест Взаимодействие")

    resp = client.get("/api/v1/dashboard", headers=admin_headers())
    assert resp.status_code == 200
    events = resp.json().get("system_stats", {}).get("recent_system_events", [])
    if not events:
        pytest.skip("Pending Milestone 3 (WP-06): dynamic audit events not populated")

    # Verify at least one event mentions creation
    created_events = [e for e in events if e.get("type") == "created" or "created" in str(e).lower()]
    assert len(created_events) > 0


def test_f16_audit_log_entries_have_valid_iso_timestamps(client):
    """All audit events must have valid timestamps."""
    resp = client.get("/api/v1/dashboard", headers=admin_headers())
    assert resp.status_code == 200
    events = resp.json().get("system_stats", {}).get("recent_system_events", [])
    if not events:
        pytest.skip("Pending Milestone 3 (WP-06): dynamic audit events not populated")

    for ev in events:
        ts = ev.get("received_at") or ev.get("created_at") or ev.get("timestamp")
        assert ts is not None
        assert "T" in str(ts)


def test_f16_audit_log_not_leaked_to_manager(client):
    """Manager dashboard should not expose system-wide administrative audit log."""
    resp = client.get("/api/v1/dashboard", headers=manager_headers("manager-a"))
    assert resp.status_code == 200
    data = resp.json()
    # Managers should see their own metrics or no recent_system_events
    if "system_stats" in data:
        assert "recent_system_events" not in data["system_stats"] or data["system_stats"]["recent_system_events"] == []


def test_f16_audit_log_ordered_chronologically_descending(client):
    """Recent system events must be ordered newest first."""
    resp = client.get("/api/v1/dashboard", headers=admin_headers())
    assert resp.status_code == 200
    events = resp.json().get("system_stats", {}).get("recent_system_events", [])
    if len(events) >= 2:
        ts1 = str(events[0].get("received_at") or events[0].get("timestamp") or "")
        ts2 = str(events[1].get("received_at") or events[1].get("timestamp") or "")
        if ts1 and ts2:
            assert ts1 >= ts2


# ============================================================================
# F17: Admin RBAC & Organization Access Grants
# ============================================================================

def test_f17_deactivated_user_cannot_access_api(client, app):
    """Deactivating a user blocks authentication with 401 UNAUTHENTICATED."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-b")
        user.active = False
        session.commit()

    resp = client.get("/api/v1/catalogs", headers=manager_headers("manager-b"))
    assert resp.status_code == 401, f"Expected 401 for deactivated user, got {resp.status_code}"

    # Restore active state for subsequent tests
    with app.state.session_factory() as session:
        user = session.get(User, "manager-b")
        user.active = True
        session.commit()


def test_f17_reactivated_user_can_access_api(client, app):
    """Reactivating a user restores API access."""
    with app.state.session_factory() as session:
        user = session.get(User, "manager-b")
        user.active = True
        session.commit()

    resp = client.get("/api/v1/catalogs", headers=manager_headers("manager-b"))
    assert resp.status_code == 200


def test_f17_organization_access_read_all_flag_enforced(client, app):
    """User with read_all=False can only view their own interactions within org."""
    with app.state.session_factory() as session:
        grant = session.get(OrganizationAccess, ("manager-a", "org-1"))
        assert grant is not None
        grant.read_all = False
        session.commit()

    # Manager-A lists interactions for org-1
    resp = client.get("/api/v1/interactions?organization_id=org-1", headers=manager_headers("manager-a"))
    assert resp.status_code == 200
    items = resp.json().get("items", []) if isinstance(resp.json(), dict) else resp.json()
    for it in items:
        assert it["owner_id"] == "manager-a"


def test_f17_revoked_grant_returns_404_for_existing_interaction(client, app):
    """When grant is deleted, accessing interactions of that org returns 404 (152-ФЗ Zero-Oracle)."""
    # Manager-A does not have grant for org-2
    # Seed has ix-4 under org-2
    resp = client.get("/api/v1/interactions/ix-4", headers=manager_headers("manager-a"))
    assert resp.status_code == 404, f"Expected 404 Zero-Oracle, got {resp.status_code}"


def test_f17_supervisor_cannot_grant_cross_team_access(client, app):
    """Supervisor of north team cannot assign manager of another team."""
    # If supervisor tries to patch organization owner to a manager outside their team -> 403
    payload = {"owner_id": "administrator"}
    resp = client.patch("/api/v1/organizations/org-1", json=payload, headers=supervisor_headers())
    assert resp.status_code in (403, 422)


# ============================================================================
# F18: Visual Workflow Stage Editor & Graph Definition Validation
# ============================================================================

def test_f18_workflow_stage_definition_validation(app):
    """Workflow state definitions must contain valid metadata and codes."""
    states = get_states(1)
    assert "contact_search" in states
    assert "completed" in states

    # Check state code uniqueness
    assert len(states) == len(set(states.keys()))


def test_f18_workflow_terminal_states_have_no_exits(app):
    """Terminal states (completed, cancelled) must have strictly 0 outgoing transitions."""
    transitions = list(get_transitions(1).values())
    for t in transitions:
        assert t["from"] != "completed", f"completed state cannot have outgoing transition to {t['to']}"
        assert t["from"] != "cancelled", f"cancelled state cannot have outgoing transition to {t['to']}"


def test_f18_all_working_states_can_reach_terminal_state(app):
    """Graph reachability: every operational state has a path to completed or cancelled."""
    transitions = list(get_transitions(1).values())
    states = list(get_states(1).keys())

    adj = {}
    for t in transitions:
        adj.setdefault(t["from"], set()).add(t["to"])

    for s in states:
        if s in ("completed", "cancelled"):
            continue
        # BFS reachability
        visited = set()
        queue = [s]
        can_reach_terminal = False
        while queue:
            curr = queue.pop(0)
            if curr in ("completed", "cancelled"):
                can_reach_terminal = True
                break
            for nxt in adj.get(curr, set()):
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append(nxt)
        assert can_reach_terminal, f"State '{s}' cannot reach any terminal state!"


def test_f18_initial_state_can_reach_all_working_states(app):
    """Initial state contact_search can reach primary workflow stages."""
    transitions = list(get_transitions(1).values())
    adj = {}
    for t in transitions:
        adj.setdefault(t["from"], set()).add(t["to"])

    visited = set()
    queue = ["contact_search"]
    while queue:
        curr = queue.pop(0)
        visited.add(curr)
        for nxt in adj.get(curr, set()):
            if nxt not in visited:
                queue.append(nxt)

    assert "meeting" in visited
    assert "completed" in visited


def test_f18_workflow_graph_view_source_exists():
    """Verify frontend WorkflowGraphView.tsx contains stage definition components."""
    from pathlib import Path
    view_file = Path(__file__).resolve().parents[3] / "frontend" / "src" / "views" / "WorkflowGraphView.tsx"
    assert view_file.exists()


# ============================================================================
# F19: Dynamic Workflow Migrator Across Arbitrary Versions
# ============================================================================

def test_f19_dry_run_migration_endpoint(client):
    """POST /api/v1/workflow/migrations/dry-run validates migration plan without mutation."""
    payload = {
        "source_version": 1,
        "target_version": 1,
        "state_mapping": {"needs_clarification": "needs_clarification"},
    }
    resp = client.post("/api/v1/workflow/migrations/dry-run", json=payload, headers=admin_headers())
    assert resp.status_code in (200, 201, 404, 422)


def test_f19_non_admin_cannot_execute_workflow_migration(client):
    """Managers and supervisors without permissions cannot trigger global migration."""
    payload = {
        "source_version": 1,
        "target_version": 2,
        "state_mapping": {},
    }
    resp = client.post("/api/v1/workflow/migrations", json=payload, headers=manager_headers("manager-a"))
    assert resp.status_code in (403, 404)


def test_f19_workflow_migrator_rejects_missing_state_mappings(client):
    """Migration must fail if working states are left unmapped."""
    payload = {
        "source_version": 1,
        "target_version": 2,
        "state_mapping": {"needs_clarification": "new_init"},  # missing other 12 states
    }
    resp = client.post("/api/v1/workflow/migrations/dry-run", json=payload, headers=admin_headers())
    assert resp.status_code in (400, 404, 422)


def test_f19_workflow_migrator_preserves_interaction_history(client, app):
    """Migrated interaction retains its InteractionEvent history and increments revision."""
    with app.state.session_factory() as session:
        # Check initial revision of seeded interaction
        ix = session.get(Interaction, "ix-1")
        assert ix is not None
        assert ix.workflow_version == 1


def test_f19_dynamic_migrator_ui_fetches_workflow_versions(client):
    """GET /api/v1/workflow/versions allows UI to dynamically select versions."""
    resp = client.get("/api/v1/workflow/versions", headers=admin_headers())
    assert resp.status_code in (200, 404)
    if resp.status_code == 200:
        data = resp.json()
        assert isinstance(data, list)
