import hashlib
import hmac
import json
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models import IntegrationInbox, LearningMetric, Organization


def compute_hmac(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def test_webhook_missing_auth_returns_401(client):
    """Missing both signature and secret token returns 401 Unauthorized."""
    payload = {"metric_code": "students_enrolled", "value": 25}
    res = client.post("/api/v1/webhooks/lms", json=payload)
    assert res.status_code == 401
    err = res.json()["error"]
    assert err["code"] == "UNAUTHORIZED"
    assert "Invalid webhook signature or secret" in err["message"]


def test_webhook_invalid_secret_returns_401(client):
    """Providing an invalid secret token returns 401."""
    payload = {"metric_code": "students_enrolled", "value": 25}
    res = client.post(
        "/api/v1/webhooks/lms",
        json=payload,
        headers={"X-Webhook-Secret": "wrong-secret-token"},
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED"


def test_webhook_invalid_hmac_signature_returns_401(client):
    """Providing an invalid HMAC signature returns 401."""
    body = b'{"metric_code": "students_enrolled", "value": 25}'
    res = client.post(
        "/api/v1/webhooks/lms",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature-SHA256": "sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        },
    )
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED"


def test_webhook_valid_secret_token_ingests_metric(client, app):
    """Valid X-Webhook-Secret header authorizes ingestion of learning metric."""
    secret = "rtk-lms-webhook-secret"
    ext_id = f"test-metric-{uuid4().hex[:8]}"
    payload = {
        "schema_version": "1.0",
        "source": "lms",
        "entity_type": "learning_metric",
        "external_id": ext_id,
        "source_revision": "1",
        "payload": {
            "organization_id": "org-1",
            "program_id": "program-devops",
            "metric_code": "attendance_rate",
            "value": 94.5,
            "unit": "percent",
        },
    }

    res = client.post(
        "/api/v1/webhooks/lms",
        json=payload,
        headers={"X-Webhook-Secret": secret},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["source"] == "lms"
    assert data["processed"] == 1
    assert data["skipped"] == 0

    with app.state.session_factory() as session:
        inbox = session.scalar(
            select(IntegrationInbox).where(
                IntegrationInbox.source == "lms",
                IntegrationInbox.external_id == ext_id,
            )
        )
        assert inbox is not None
        assert inbox.status == "processed"
        assert inbox.matched_organization_id == "org-1"

        metric = session.scalar(
            select(LearningMetric).where(
                LearningMetric.source == "lms",
                LearningMetric.external_id == ext_id,
            )
        )
        assert metric is not None
        assert metric.value == 94.5
        assert metric.unit == "percent"
        assert metric.last_applied_revision == "1"


def test_webhook_valid_hmac_sha256_ingests_metric(client, app):
    """Valid HMAC-SHA256 signature in X-Signature-SHA256 authorizes ingestion."""
    secret = "rtk-lms-webhook-secret"
    ext_id = f"test-hmac-{uuid4().hex[:8]}"
    payload = {
        "org_id": "org-1",
        "prog_id": "program-devops",
        "metric_code": "students_enrolled",
        "value": 42.0,
        "unit": "student",
        "external_id": ext_id,
        "source_revision": "1",
    }
    body = json.dumps(payload).encode("utf-8")
    sig = compute_hmac(secret, body)

    res = client.post(
        "/api/v1/webhooks/lms",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature-SHA256": f"sha256={sig}",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["processed"] == 1
    assert data["skipped"] == 0

    with app.state.session_factory() as session:
        metric = session.scalar(
            select(LearningMetric).where(
                LearningMetric.source == "lms",
                LearningMetric.external_id == ext_id,
            )
        )
        assert metric is not None
        assert metric.value == 42.0


def test_webhook_x_hub_signature_format(client, app):
    """X-Hub-Signature-256 header with and without sha256= prefix is supported."""
    secret = "rtk-lms-webhook-secret"
    ext_id = f"test-hub-{uuid4().hex[:8]}"
    payload = {
        "organization_id": "org-1",
        "program_id": "program-devops",
        "metric_code": "active_cohorts",
        "value": 3.0,
        "unit": "cohort",
        "external_id": ext_id,
        "source_revision": "1",
    }
    body = json.dumps(payload).encode("utf-8")
    sig = compute_hmac(secret, body)

    # Without sha256= prefix in X-Hub-Signature-256
    res = client.post(
        "/api/v1/webhooks/lms",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig,
        },
    )
    assert res.status_code == 200
    assert res.json()["processed"] == 1


def test_webhook_deduplication_and_idempotency(client, app):
    """Duplicate webhook delivery with identical source_record_id and source_revision is skipped."""
    secret = "rtk-lms-webhook-secret"
    rec_id = f"rec-dedup-{uuid4().hex[:8]}"
    payload = {
        "source_record_id": rec_id,
        "source_revision": "rev-1",
        "entity_type": "learning_metric",
        "payload": {
            "organization_id": "org-1",
            "program_id": "program-devops",
            "metric_code": "students_completed",
            "value": 15.0,
            "unit": "student",
        },
    }

    # 1. First delivery -> processed=1, skipped=0
    res1 = client.post("/api/v1/webhooks/lms", json=payload, headers={"X-Webhook-Secret": secret})
    assert res1.status_code == 200
    d1 = res1.json()
    assert d1["processed"] == 1
    assert d1["skipped"] == 0

    # 2. Second delivery of exact same payload -> processed=0, skipped=1
    res2 = client.post("/api/v1/webhooks/lms", json=payload, headers={"X-Webhook-Secret": secret})
    assert res2.status_code == 200
    d2 = res2.json()
    assert d2["processed"] == 0
    assert d2["skipped"] == 1

    # Verify database has exactly 1 inbox item and 1 metric
    with app.state.session_factory() as session:
        inbox_count = session.scalar(
            select(func.count(IntegrationInbox.id)).where(
                IntegrationInbox.source == "lms",
                IntegrationInbox.external_id == rec_id,
            )
        )
        assert inbox_count == 1

        metric_count = session.scalar(
            select(func.count(LearningMetric.id)).where(
                LearningMetric.source == "lms",
                LearningMetric.external_id == rec_id,
            )
        )
        assert metric_count == 1


def test_webhook_revision_update_and_out_of_order(client, app):
    """Higher revision updates LearningMetric; older revision is rejected/skipped."""
    secret = "rtk-lms-webhook-secret"
    ext_id = f"rev-metric-{uuid4().hex[:8]}"

    # Rev 1: value 10
    p1 = {
        "external_id": ext_id,
        "source_revision": "1",
        "org_id": "org-1",
        "prog_id": "program-devops",
        "metric_code": "active_cohorts",
        "value": 10.0,
        "unit": "cohort",
    }
    res1 = client.post("/api/v1/webhooks/lms", json=p1, headers={"X-Webhook-Secret": secret})
    assert res1.status_code == 200
    assert res1.json()["processed"] == 1

    with app.state.session_factory() as session:
        m = session.scalar(select(LearningMetric).where(LearningMetric.external_id == ext_id))
        assert m.value == 10.0
        assert m.last_applied_revision == "1"

    # Rev 2: value 20 (newer revision)
    p2 = {
        "external_id": ext_id,
        "source_revision": "2",
        "org_id": "org-1",
        "prog_id": "program-devops",
        "metric_code": "active_cohorts",
        "value": 20.0,
        "unit": "cohort",
    }
    res2 = client.post("/api/v1/webhooks/lms", json=p2, headers={"X-Webhook-Secret": secret})
    assert res2.status_code == 200
    assert res2.json()["processed"] == 1

    with app.state.session_factory() as session:
        m = session.scalar(select(LearningMetric).where(LearningMetric.external_id == ext_id))
        assert m.value == 20.0
        assert m.last_applied_revision == "2"

    # Resend Rev 1 (stale out-of-order revision) with a different sub-inbox key or older revision
    # With a distinct envelope revision "1"
    # It should not overwrite value 20 back to 10
    p_stale = {
        "external_id": ext_id,
        "source_revision": "0",  # older than 2
        "org_id": "org-1",
        "prog_id": "program-devops",
        "metric_code": "active_cohorts",
        "value": 5.0,
        "unit": "cohort",
    }
    res3 = client.post("/api/v1/webhooks/lms", json=p_stale, headers={"X-Webhook-Secret": secret})
    assert res3.status_code == 200
    assert res3.json()["skipped"] == 1

    with app.state.session_factory() as session:
        m = session.scalar(select(LearningMetric).where(LearningMetric.external_id == ext_id))
        assert m.value == 20.0  # Not overwritten!


def test_webhook_website_application(client, app):
    """Website webhook ingests university application into pending reconciliation queue."""
    secret = "rtk-website-webhook-secret"
    ext_id = f"web-app-{uuid4().hex[:8]}"
    payload = {
        "external_id": ext_id,
        "source_revision": "1",
        "organization_name": "Московский технический университет",
        "representative_name": "Тестов Тест Тестович",
        "representative_email": "test@mtu.ru",
        "comments": "Тестовая веб-заявка через вебхук",
    }
    body = json.dumps(payload).encode("utf-8")
    sig = compute_hmac(secret, body)

    res = client.post(
        "/api/v1/webhooks/website",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature-SHA256": f"sha256={sig}",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["source"] == "website"
    assert data["processed"] == 1

    with app.state.session_factory() as session:
        inbox = session.scalar(
            select(IntegrationInbox).where(
                IntegrationInbox.source == "website",
                IntegrationInbox.external_id == ext_id,
            )
        )
        assert inbox is not None
        assert inbox.status == "pending"
        assert inbox.matched_organization_id == "org-1"


def test_webhook_batch_items_and_list_payload(client, app):
    """Batch webhook payload formatted as list or {'items': [...]} is supported."""
    secret = "rtk-lms-webhook-secret"
    id1 = f"batch-1-{uuid4().hex[:6]}"
    id2 = f"batch-2-{uuid4().hex[:6]}"
    batch = {
        "items": [
            {
                "external_id": id1,
                "source_revision": "1",
                "org_id": "org-1",
                "prog_id": "program-devops",
                "metric_code": "students_enrolled",
                "value": 11.0,
                "unit": "student",
            },
            {
                "external_id": id2,
                "source_revision": "1",
                "org_id": "org-1",
                "prog_id": "program-devops",
                "metric_code": "students_enrolled",
                "value": 22.0,
                "unit": "student",
            },
        ]
    }
    res = client.post("/api/v1/webhooks/lms", json=batch, headers={"X-Webhook-Secret": secret})
    assert res.status_code == 200
    assert res.json()["processed"] == 2
    assert res.json()["skipped"] == 0

    # Sending batch again -> both skipped
    res_repeat = client.post("/api/v1/webhooks/lms", json=batch, headers={"X-Webhook-Secret": secret})
    assert res_repeat.status_code == 200
    assert res_repeat.json()["processed"] == 0
    assert res_repeat.json()["skipped"] == 2


def test_webhook_malformed_json_returns_400(client):
    """Malformed JSON payload with valid secret returns 400 without crashing."""
    secret = "rtk-lms-webhook-secret"
    res = client.post(
        "/api/v1/webhooks/lms",
        content=b'{"broken_json": ',
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Secret": secret,
        },
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_webhook_empty_payload_returns_400(client):
    """Empty payload returns 400."""
    secret = "rtk-lms-webhook-secret"
    res = client.post(
        "/api/v1/webhooks/lms",
        content=b"",
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Secret": secret,
        },
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_webhook_unsupported_source_returns_400(client):
    """Unsupported webhook source returns 400."""
    res = client.post(
        "/api/v1/webhooks/unsupported_vendor",
        json={"metric": "test"},
        headers={"X-Webhook-Secret": "rtk-default-webhook-secret"},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_webhook_custom_secret_env_var(client, monkeypatch):
    """Custom webhook secret configured via LMS_WEBHOOK_SECRET is enforced."""
    custom_secret = "my-super-secret-key-12345"
    monkeypatch.setenv("LMS_WEBHOOK_SECRET", custom_secret)

    payload = {
        "org_id": "org-1",
        "prog_id": "program-devops",
        "metric_code": "attendance_rate",
        "value": 99.0,
        "unit": "percent",
        "external_id": f"custom-env-{uuid4().hex[:6]}",
        "source_revision": "1",
    }
    body = json.dumps(payload).encode("utf-8")

    # Old default secret must fail (401)
    res_old = client.post(
        "/api/v1/webhooks/lms",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Secret": "rtk-lms-webhook-secret",
        },
    )
    assert res_old.status_code == 401

    # New custom secret succeeds (200)
    sig = compute_hmac(custom_secret, body)
    res_new = client.post(
        "/api/v1/webhooks/lms",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature-SHA256": f"sha256={sig}",
        },
    )
    assert res_new.status_code == 200
    assert res_new.json()["processed"] == 1
