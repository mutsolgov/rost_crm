import sys
from pathlib import Path
from uuid import uuid4

backend_dir = Path(__file__).resolve().parents[2]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))


def auth_headers(user="manager-a", idempotency_key=None):
    res = {"X-Demo-User": user}
    if idempotency_key:
        res["Idempotency-Key"] = idempotency_key
    return res


def admin_headers(idempotency_key=None):
    return auth_headers("administrator", idempotency_key)


def supervisor_headers(idempotency_key=None):
    return auth_headers("supervisor", idempotency_key)


def manager_headers(user="manager-a", idempotency_key=None):
    return auth_headers(user, idempotency_key)


def route_exists(app, path_prefix: str, method: str = "GET") -> bool:
    for route in app.routes:
        if getattr(route, "path", "").startswith(path_prefix):
            methods = getattr(route, "methods", set())
            if method.upper() in methods:
                return True
    return False


def create_e2e_interaction(client, user="manager-a", **overrides):
    payload = {
        "title": "E2E Взаимодействие ВУЗ",
        "organization_id": "org-1",
        "program_id": "program-devops",
        "product_id": "product-cloud",
        "cycle_label": "2026/27",
        "owner_id": user,
    }
    payload.update(overrides)
    key = str(uuid4())
    resp = client.post("/api/v1/interactions", json=payload, headers=auth_headers(user, key))
    assert resp.status_code == 201, f"Failed to create interaction: {resp.text}"
    return resp.json()


def transition_e2e(client, ix_id, transition_code, expected_revision=1, comment=None, user="manager-a"):
    payload = {
        "transition_code": transition_code,
        "expected_revision": expected_revision,
        "comment": comment,
    }
    key = str(uuid4())
    return client.post(
        f"/api/v1/interactions/{ix_id}/transitions",
        json=payload,
        headers=manager_headers(user, key),
    )


def comment_e2e(client, ix_id, comment_text, expected_revision=1, user="manager-a"):
    payload = {
        "body": comment_text,
        "expected_revision": expected_revision,
    }
    key = str(uuid4())
    return client.post(
        f"/api/v1/interactions/{ix_id}/comments",
        json=payload,
        headers=manager_headers(user, key),
    )
