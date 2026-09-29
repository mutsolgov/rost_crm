"""Domain 6 Adversarial Security & Zero-Oracle Challenger Verification Suite.

Written by Challenger 1 (Domain 6) to rigorously challenge:
1. Zero-Oracle: Unowned interactions or comments return strict HTTP 404 Not Found (indistinguishable from non-existent).
2. Immutability: Total absence of mutation or deletion routes or services for InteractionEvent and Comment.
3. Identity Spoofing: Client-supplied user_id, author_id, actor_id are strictly rejected (422) or ignored;
   identity is strictly extracted from verified authentication context (JWT / current_user).
4. Role and Team Isolation: Manager, Supervisor, and Administrator boundaries.
"""

from datetime import datetime, timezone, timedelta
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, inspect

from app.models import Comment, Interaction, InteractionEvent, OrganizationAccess, User, Team
from app.config import Settings


def headers(user="manager-a", key=None, auth_token=None):
    h = {}
    if user:
        h["X-Demo-User"] = user
    if key:
        h["Idempotency-Key"] = key
    if auth_token:
        h["Authorization"] = f"Bearer {auth_token}"
    return h


def create_interaction(client: TestClient, user="manager-a", org_id="org-1", **overrides):
    body = {
        "title": f"Domain6 Test Card {uuid4().hex[:8]}",
        "organization_id": org_id,
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "2026-Domain6-Challenge",
        "owner_id": user,
    }
    body.update(overrides)
    res = client.post("/api/v1/interactions", json=body, headers=headers(user, str(uuid4())))
    assert res.status_code == 201, res.text
    return res.json()


# ==============================================================================
# SECTION 1: ZERO-ORACLE SECURITY INVARIANTS
# ==============================================================================

def test_zero_oracle_foreign_vs_nonexistent_indistinguishability(client: TestClient):
    """Verify that foreign interaction access produces identical HTTP 404 responses
    as completely non-existent IDs across all interaction endpoints.
    """
    # Manager B creates a confidential card
    foreign_card = create_interaction(client, user="manager-b", org_id="org-2")
    foreign_id = foreign_card["id"]
    ghost_id = str(uuid4())

    endpoints = [
        ("GET", f"/api/v1/interactions/{{id}}", None),
        ("POST", f"/api/v1/interactions/{{id}}/comments", {"body": "Infiltration", "expected_revision": 1}),
        ("PATCH", f"/api/v1/interactions/{{id}}", {"title": "Hostile Rename", "expected_revision": 1}),
        ("POST", f"/api/v1/interactions/{{id}}/transitions", {"transition_code": "contact_search_to_needs_clarification", "expected_revision": 1}),
        ("POST", f"/api/v1/interactions/{{id}}/assignments", {"owner_id": "manager-a", "reason": "Hostile takeover", "expected_revision": 1}),
        ("GET", f"/api/v1/interactions/{{id}}/attachments", None),
        ("GET", f"/api/v1/interactions/{{id}}/deliveries", None),
        ("POST", f"/api/v1/interactions/{{id}}/deliveries", {"title": "Test Delivery", "item_kind": "license"}),
    ]

    for method, path_tmpl, payload in endpoints:
        path_foreign = path_tmpl.format(id=foreign_id)
        path_ghost = path_tmpl.format(id=ghost_id)
        req_headers = headers("manager-a", key=str(uuid4()))

        if method == "GET":
            resp_foreign = client.get(path_foreign, headers=req_headers)
            resp_ghost = client.get(path_ghost, headers=req_headers)
        elif method == "POST":
            resp_foreign = client.post(path_foreign, json=payload, headers=req_headers)
            resp_ghost = client.post(path_ghost, json=payload, headers=req_headers)
        elif method == "PATCH":
            resp_foreign = client.patch(path_foreign, json=payload, headers=req_headers)
            resp_ghost = client.patch(path_ghost, json=payload, headers=req_headers)
        else:
            pytest.fail(f"Unsupported method {method}")

        # Both MUST return strict 404 Not Found (never 403 Forbidden!)
        assert resp_foreign.status_code == 404, (
            f"Zero-Oracle leak! Endpoint {method} {path_foreign} returned {resp_foreign.status_code} instead of 404"
        )
        assert resp_ghost.status_code == 404

        data_foreign = resp_foreign.json()
        data_ghost = resp_ghost.json()

        assert data_foreign["error"]["code"] == "NOT_FOUND"
        assert data_ghost["error"]["code"] == "NOT_FOUND"
        assert data_foreign["error"]["message"] == data_ghost["error"]["message"]


def test_zero_oracle_cross_role_and_team_isolation(client: TestClient, app):
    """Supervisor South and Admin have zero visibility into unauthorized commercial interactions."""
    card = create_interaction(client, user="manager-a", org_id="org-1")
    card_id = card["id"]

    # 1. Supervisor South (team south) probing Team North's card
    sup_south = User(
        id="supervisor-south-d6",
        keycloak_subject=str(uuid4()),
        name="Руководитель Юга",
        role="supervisor",
        team_id="south",
        permissions=["interactions.comment", "interactions.transition", "interactions.assign"],
        active=True,
    )
    with app.state.session_factory() as session:
        session.merge(sup_south)
        session.commit()

    res_sup = client.get(f"/api/v1/interactions/{card_id}", headers=headers(sup_south.id))
    assert res_sup.status_code == 404
    assert res_sup.json()["error"]["code"] == "NOT_FOUND"

    res_sup_comment = client.post(
        f"/api/v1/interactions/{card_id}/comments",
        json={"body": "Cross-team comment", "expected_revision": 1},
        headers=headers(sup_south.id, str(uuid4())),
    )
    assert res_sup_comment.status_code == 404
    assert res_sup_comment.json()["error"]["code"] == "NOT_FOUND"

    # 2. Administrator without explicit OrganizationAccess
    with app.state.session_factory() as session:
        grants = session.scalars(select(OrganizationAccess).where(OrganizationAccess.user_id == "administrator")).all()
        for g in grants:
            session.delete(g)
        session.commit()

    res_admin = client.get(f"/api/v1/interactions/{card_id}", headers=headers("administrator"))
    assert res_admin.status_code == 404
    assert res_admin.json()["error"]["code"] == "NOT_FOUND"

    res_admin_comment = client.post(
        f"/api/v1/interactions/{card_id}/comments",
        json={"body": "Admin ungranted comment", "expected_revision": 1},
        headers=headers("administrator", str(uuid4())),
    )
    assert res_admin_comment.status_code == 404
    assert res_admin_comment.json()["error"]["code"] == "NOT_FOUND"


# ==============================================================================
# SECTION 2: IMMUTABILITY OF EVENTS AND COMMENTS
# ==============================================================================

def test_immutability_no_update_or_delete_routes_for_comments_and_events(client: TestClient):
    """Verify that no API route exists allowing DELETE, PUT, or PATCH of comments or events."""
    card = create_interaction(client, user="manager-a")
    card_id = card["id"]

    # Add a valid comment
    c_res = client.post(
        f"/api/v1/interactions/{card_id}/comments",
        json={"body": "Audit comment for immutability check", "expected_revision": card["revision"]},
        headers=headers("manager-a", str(uuid4())),
    )
    assert c_res.status_code == 201
    comment_id = c_res.json()["id"]

    # Probing illegal mutation and deletion routes
    forbidden_probes = [
        ("DELETE", f"/api/v1/interactions/{card_id}/comments"),
        ("DELETE", f"/api/v1/interactions/{card_id}/comments/{comment_id}"),
        ("PUT", f"/api/v1/interactions/{card_id}/comments/{comment_id}", {"body": "tampered"}),
        ("PATCH", f"/api/v1/interactions/{card_id}/comments/{comment_id}", {"body": "tampered"}),
        ("DELETE", f"/api/v1/comments/{comment_id}"),
        ("PUT", f"/api/v1/comments/{comment_id}", {"body": "tampered"}),
        ("PATCH", f"/api/v1/comments/{comment_id}", {"body": "tampered"}),
        ("DELETE", f"/api/v1/interactions/{card_id}/events"),
        ("DELETE", f"/api/v1/events/{uuid4()}"),
        ("DELETE", f"/api/v1/interactions/{card_id}"),  # Interactions themselves cannot be deleted!
    ]

    for method, path, *payload in forbidden_probes:
        json_body = payload[0] if payload else None
        if method == "DELETE":
            resp = client.delete(path, headers=headers("manager-a", str(uuid4())))
        elif method == "PUT":
            resp = client.put(path, json=json_body, headers=headers("manager-a", str(uuid4())))
        elif method == "PATCH":
            resp = client.patch(path, json=json_body, headers=headers("manager-a", str(uuid4())))
        else:
            pytest.fail(f"Unsupported method {method}")

        # Must return 404 (route not found) or 405 (method not allowed)
        assert resp.status_code in (404, 405), (
            f"CRITICAL IMMUTABILITY VIOLATION: {method} {path} returned {resp.status_code}: {resp.text}"
        )


def test_immutability_event_sequence_monotonicity_and_snapshots(client: TestClient, app):
    """Verify that interaction events have strictly continuous sequence numbers,
    immutable snapshots, and cannot be overwritten.
    """
    card = create_interaction(client, user="manager-a")
    card_id = card["id"]
    rev = card["revision"]

    # Sequence of 3 mutations
    # 1. Add comment
    res_c = client.post(
        f"/api/v1/interactions/{card_id}/comments",
        json={"body": "Event seq 2 comment", "expected_revision": rev},
        headers=headers("manager-a", str(uuid4())),
    )
    assert res_c.status_code == 201
    rev = res_c.json()["revision"]

    # 2. Patch title
    res_p = client.patch(
        f"/api/v1/interactions/{card_id}",
        json={"title": "Updated Title for Seq 3", "expected_revision": rev},
        headers=headers("manager-a", str(uuid4())),
    )
    assert res_p.status_code == 200
    rev = res_p.json()["revision"]

    # 3. Transition stage
    res_t = client.post(
        f"/api/v1/interactions/{card_id}/transitions",
        json={"transition_code": "contact_search_to_needs_clarification", "expected_revision": rev, "comment": "Transition note"},
        headers=headers("manager-a", str(uuid4())),
    )
    assert res_t.status_code == 200

    # Inspect events in DB
    with app.state.session_factory() as session:
        events = session.scalars(
            select(InteractionEvent).where(InteractionEvent.interaction_id == card_id).order_by(InteractionEvent.sequence)
        ).all()

        assert len(events) >= 4  # created, comment_added, attributes_corrected, state_changed
        sequences = [e.sequence for e in events]
        assert sequences == list(range(1, len(events) + 1)), f"Sequences must be 1..N continuous: {sequences}"

        for e in events:
            assert e.actor_id == "manager-a"
            assert e.actor_name == "Анна Смирнова"
            assert e.effective_at is not None
            assert e.received_at is not None
            assert "snapshot" in e.payload
            assert e.payload["snapshot"]["id"] == card_id


# ==============================================================================
# SECTION 3: IDENTITY SPOOFING REJECTION & STRICT JWT EXTRACTION
# ==============================================================================

def test_identity_spoofing_payload_injection_rejected(client: TestClient):
    """Verify that passing client-supplied user_id, author_id, or actor_id in comment payloads
    is rejected with 422 VALIDATION_ERROR due to strict Pydantic extra='forbid' policy.
    """
    card = create_interaction(client, user="manager-a")
    card_id = card["id"]

    spoofed_payloads = [
        {"body": "Valid text", "expected_revision": card["revision"], "author_id": "manager-b"},
        {"body": "Valid text", "expected_revision": card["revision"], "user_id": "manager-b"},
        {"body": "Valid text", "expected_revision": card["revision"], "actor_id": "manager-b"},
        {"body": "Valid text", "expected_revision": card["revision"], "author_name": "Администратор"},
        {"body": "Valid text", "expected_revision": card["revision"], "role": "admin"},
    ]

    for payload in spoofed_payloads:
        resp = client.post(
            f"/api/v1/interactions/{card_id}/comments",
            json=payload,
            headers=headers("manager-a", str(uuid4())),
        )
        assert resp.status_code == 422, (
            f"Expected 422 for spoofed payload {payload}, got {resp.status_code}: {resp.text}"
        )
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_identity_spoofing_transition_payload_injection_rejected(client: TestClient):
    """Verify that passing extra user/author spoofing fields in transition payloads is rejected with 422."""
    card = create_interaction(client, user="manager-a")
    card_id = card["id"]

    spoofed_transition = {
        "transition_code": "contact_search_to_needs_clarification",
        "expected_revision": card["revision"],
        "comment": "Transition note",
        "author_id": "supervisor",
        "actor_id": "administrator",
    }
    resp = client.post(
        f"/api/v1/interactions/{card_id}/transitions",
        json=spoofed_transition,
        headers=headers("manager-a", str(uuid4())),
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


def test_comment_authorship_strictly_bound_to_authenticated_session(client: TestClient, app):
    """Verify that Comment.author_id and InteractionEvent.actor_id in DB are strictly bound
    to the verified session user and cannot be manipulated.
    """
    card = create_interaction(client, user="manager-a")
    card_id = card["id"]

    resp = client.post(
        f"/api/v1/interactions/{card_id}/comments",
        json={"body": "Authorship binding test", "expected_revision": card["revision"]},
        headers=headers("manager-a", str(uuid4())),
    )
    assert resp.status_code == 201
    comment_data = resp.json()
    comment_id = comment_data["id"]

    with app.state.session_factory() as session:
        comment_row = session.get(Comment, comment_id)
        assert comment_row is not None
        assert comment_row.author_id == "manager-a"
        assert comment_row.author_name == "Анна Смирнова"

        # Check corresponding event
        event_row = session.scalar(
            select(InteractionEvent).where(
                InteractionEvent.interaction_id == card_id,
                InteractionEvent.type == "comment_added",
                InteractionEvent.payload["comment_id"].as_string() == comment_id,
            )
        )
        assert event_row is not None
        assert event_row.actor_id == "manager-a"
        assert event_row.actor_name == "Анна Смирнова"


def test_jwt_authentication_and_claim_validation(client: TestClient, monkeypatch, app):
    """Verify that in non-demo (production OIDC) mode, JWT signatures and claims are cryptographically enforced."""
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    # Generate test RSA key pair
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    pub_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    class MockSigningKey:
        def __init__(self, key):
            self.key = key

    class MockJWKClient:
        def get_signing_key_from_jwt(self, token):
            return MockSigningKey(pub_pem)

    # Patch runtime settings to oidc mode
    test_settings = Settings(
        auth_mode="keycloak",
        oidc_issuer="https://auth.example.com/realms/crm",
        oidc_audience="crm-client",
        oidc_client_id="crm-client",
        oidc_jwks_url="https://auth.example.com/jwks",
    )
    app.state.settings = test_settings
    monkeypatch.setattr("app.auth.runtime_settings", lambda: test_settings)
    monkeypatch.setattr("app.auth.jwks_client", lambda url: MockJWKClient())

    now = datetime.now(timezone.utc)

    # 1. Valid Token for manager-a
    valid_payload = {
        "sub": "11111111-1111-4111-8111-111111111111",
        "iss": "https://auth.example.com/realms/crm",
        "aud": "crm-client",
        "exp": int((now + timedelta(hours=1)).timestamp()),
        "realm_access": {"roles": ["manager"]},
    }
    valid_token = jwt.encode(valid_payload, private_key, algorithm="RS256")
    resp_valid = client.get("/api/v1/me", headers={"Authorization": f"Bearer {valid_token}"})
    assert resp_valid.status_code == 200
    assert resp_valid.json()["id"] == "manager-a"

    # 2. Expired Token -> 401 UNAUTHENTICATED
    expired_payload = {**valid_payload, "exp": int((now - timedelta(seconds=10)).timestamp())}
    expired_token = jwt.encode(expired_payload, private_key, algorithm="RS256")
    resp_exp = client.get("/api/v1/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp_exp.status_code == 401
    assert resp_exp.json()["error"]["code"] == "UNAUTHENTICATED"

    # 3. Forged / Wrong Signature Token -> 401 UNAUTHENTICATED
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    tampered_token = jwt.encode(valid_payload, other_key, algorithm="RS256")
    resp_tampered = client.get("/api/v1/me", headers={"Authorization": f"Bearer {tampered_token}"})
    assert resp_tampered.status_code == 401
    assert resp_tampered.json()["error"]["code"] == "UNAUTHENTICATED"

    # 4. Unknown Subject -> 401 UNAUTHENTICATED
    unknown_sub_payload = {**valid_payload, "sub": "unknown-nonexistent-sub"}
    unknown_token = jwt.encode(unknown_sub_payload, private_key, algorithm="RS256")
    resp_unk = client.get("/api/v1/me", headers={"Authorization": f"Bearer {unknown_token}"})
    assert resp_unk.status_code == 401
    assert resp_unk.json()["error"]["code"] == "UNAUTHENTICATED"

    # 5. Role mismatch (claims role 'auditor', but CRM user is 'manager') -> 403 FORBIDDEN
    role_mismatch_payload = {**valid_payload, "realm_access": {"roles": ["guest"]}}
    mismatch_token = jwt.encode(role_mismatch_payload, private_key, algorithm="RS256")
    resp_mismatch = client.get("/api/v1/me", headers={"Authorization": f"Bearer {mismatch_token}"})
    assert resp_mismatch.status_code == 403
    assert resp_mismatch.json()["error"]["code"] == "FORBIDDEN"
