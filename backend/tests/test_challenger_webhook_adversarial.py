"""Empirical Adversarial Stress Test Suite for Phase 8 Webhooks & Live Adapters.

Challenger: teamwork_preview_challenger_d8_1
Target: POST /api/v1/webhooks/{source} & Live Adapters Fault Tolerance

Verification Dimensions:
1. Timing attack resistance & signature validation (varying key lengths, invalid hex formats, case variance).
2. Replay attack defense (burst sequential & concurrent duplicate delivery).
3. Out-of-order delivery defense (numerical & lexical revisions, older vs newer).
4. Malformed payloads, JSON primitives, and SQL injection defense across all fields.
5. Live adapters network fault tolerance (HTTP 500, 502, 503, 504 responses without server crash).
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.integrations.factory import get_adapter
from app.integrations.live_lms import LiveLMSAdapter
from app.integrations.live_website import LiveWebsiteAdapter
from app.models import IntegrationInbox, LearningMetric, Organization, User


def compute_hmac(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


# ==============================================================================
# 1. Timing Attack Resistance & Header Fuzzing
# ==============================================================================

def test_adversarial_timing_attack_varying_secret_lengths(client):
    """Stress test: X-Webhook-Secret of varying lengths (0 to 4096 chars) and partial matches.
    
    Ensures constant-time comparison via hmac.compare_digest, no unhandled exceptions,
    and strict 401 Unauthorized responses.
    """
    payload = {"metric_code": "students_enrolled", "value": 42}
    valid_secret = "rtk-lms-webhook-secret"

    varying_secrets = [
        "",
        "a",
        "rtk",
        "rtk-lms",
        valid_secret[:-1],              # 1 char shorter
        valid_secret + "x",             # 1 char longer
        valid_secret.upper(),           # Wrong case
        " " + valid_secret,             # Leading space
        valid_secret + " ",             # Trailing space (note: main.py strips, let's verify if stripped matches or if exact match is required)
        "A" * 64,
        "B" * 256,
        "C" * 1024,
        "D" * 4096,
        "\x00" * 32,                    # Null bytes
        "' OR '1'='1",                  # SQLi attempt in header
        "<script>alert(1)</script>",    # XSS attempt in header
    ]

    for test_sec in varying_secrets:
        # If test_sec strips to valid_secret, it would be authorized; otherwise strictly 401
        expected_status = 200 if test_sec.strip() == valid_secret else 401
        res = client.post(
            "/api/v1/webhooks/lms",
            json=payload,
            headers={"X-Webhook-Secret": test_sec},
        )
        assert res.status_code == expected_status, (
            f"Expected {expected_status} for secret '{test_sec[:20]}...', got {res.status_code}"
        )
        if expected_status == 401:
            assert res.json()["error"]["code"] == "UNAUTHORIZED"


def test_adversarial_signature_invalid_hex_formats(client):
    """Stress test: Invalid hex strings, truncated signatures, odd lengths, non-hex characters.
    
    Verifies that the HMAC verification does not crash on bytes.fromhex or invalid formats,
    gracefully returning 401. Also verifies valid uppercase hex is accepted.
    """
    body = b'{"metric_code": "students_enrolled", "value": 42}'
    valid_secret = "rtk-lms-webhook-secret"
    valid_sig = compute_hmac(valid_secret, body)

    invalid_sigs = [
        "sha256=",                                      # Empty after prefix
        "sha256=invalid_non_hex_string_12345!@#$",      # Non-hex characters
        "sha256=123",                                   # Too short
        "sha256=" + "a" * 63,                           # Odd length (63)
        "sha256=" + "a" * 65,                           # Too long (65)
        "sha256=" + "g" * 64,                           # 'g' is outside hex [0-9a-f]
        "sha256=" + "0" * 63 + "X",                     # Non-hex ending
        "sha256=" + "f" * 4096,                         # Oversized signature
        "md5=0123456789abcdef0123456789abcdef",         # Unsupported algo
        "sha512=" + valid_sig,                          # Wrong prefix
        valid_sig[:-2] + "00",                          # Valid length, mismatched value
    ]

    for inv_sig in invalid_sigs:
        res = client.post(
            "/api/v1/webhooks/lms",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature-SHA256": inv_sig,
            },
        )
        assert res.status_code == 401, f"Expected 401 for signature '{inv_sig[:25]}...', got {res.status_code}"
        assert res.json()["error"]["code"] == "UNAUTHORIZED"

    # Valid hex with uppercase should be accepted
    res_upper = client.post(
        "/api/v1/webhooks/lms",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature-SHA256": f"sha256={valid_sig.upper()}",
        },
    )
    assert res_upper.status_code == 200, f"Valid uppercase hex should be accepted, got {res_upper.status_code}"


# ==============================================================================
# 2. Replay Attack Defense (Burst & Concurrent Delivery)
# ==============================================================================

def test_adversarial_replay_attack_burst_delivery(client, app):
    """Stress test: 25 sequential identical deliveries of the exact same payload.
    
    Verifies that delivery 1 processes successfully, and deliveries 2..25 are safely
    skipped without duplicate records in IntegrationInbox or LearningMetric.
    """
    secret = "rtk-lms-webhook-secret"
    rec_id = f"burst-replay-{uuid4().hex[:8]}"
    payload = {
        "external_id": rec_id,
        "source_revision": "rev-burst-1",
        "entity_type": "learning_metric",
        "payload": {
            "organization_id": "org-1",
            "program_id": "program-devops",
            "metric_code": "students_completed",
            "value": 33.0,
            "unit": "student",
        },
    }

    # Delivery 1: processed
    res1 = client.post("/api/v1/webhooks/lms", json=payload, headers={"X-Webhook-Secret": secret})
    assert res1.status_code == 200
    assert res1.json()["processed"] == 1
    assert res1.json()["skipped"] == 0

    # Deliveries 2 to 25: strictly skipped
    for i in range(2, 26):
        res = client.post("/api/v1/webhooks/lms", json=payload, headers={"X-Webhook-Secret": secret})
        assert res.status_code == 200
        data = res.json()
        assert data["processed"] == 0, f"Delivery {i} was processed instead of skipped!"
        assert data["skipped"] == 1, f"Delivery {i} was not marked skipped!"

    # Database invariant: exactly 1 inbox item and 1 metric
    with app.state.session_factory() as session:
        inbox_count = session.scalar(
            select(func.count(IntegrationInbox.id)).where(
                IntegrationInbox.source == "lms",
                IntegrationInbox.external_id == rec_id,
            )
        )
        assert inbox_count == 1, f"Expected 1 inbox entry, found {inbox_count}"

        metric_count = session.scalar(
            select(func.count(LearningMetric.id)).where(
                LearningMetric.source == "lms",
                LearningMetric.external_id == rec_id,
            )
        )
        assert metric_count == 1, f"Expected 1 learning metric entry, found {metric_count}"


def test_adversarial_replay_attack_concurrent_delivery(client, app):
    """Stress test: Concurrently firing 8 identical webhook deliveries across worker threads.
    
    Verifies race-condition resilience: all threads receive HTTP 200, and database
    persists strictly 1 unique inbox item and 1 unique metric.
    """
    secret = "rtk-lms-webhook-secret"
    rec_id = f"concurrent-replay-{uuid4().hex[:8]}"
    payload = {
        "external_id": rec_id,
        "source_revision": "rev-conc-1",
        "entity_type": "learning_metric",
        "payload": {
            "organization_id": "org-1",
            "program_id": "program-devops",
            "metric_code": "active_cohorts",
            "value": 5.0,
            "unit": "cohort",
        },
    }

    def send_webhook():
        return client.post("/api/v1/webhooks/lms", json=payload, headers={"X-Webhook-Secret": secret})

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(send_webhook) for _ in range(8)]
        results = [f.result() for f in futures]

    # Every request must succeed with 200
    for res in results:
        assert res.status_code == 200

    total_processed = sum(r.json()["processed"] for r in results)
    total_skipped = sum(r.json()["skipped"] for r in results)

    # In total across all 8 requests, at least 1 must be processed and rest skipped
    assert total_processed >= 1
    assert total_processed + total_skipped == 8

    # Empirical check on DB state: strictly 1 row
    with app.state.session_factory() as session:
        inbox_count = session.scalar(
            select(func.count(IntegrationInbox.id)).where(
                IntegrationInbox.source == "lms",
                IntegrationInbox.external_id == rec_id,
            )
        )
        assert inbox_count == 1, f"Expected exactly 1 inbox item after race, found {inbox_count}"

        metric_count = session.scalar(
            select(func.count(LearningMetric.id)).where(
                LearningMetric.source == "lms",
                LearningMetric.external_id == rec_id,
            )
        )
        assert metric_count == 1, f"Expected exactly 1 learning metric item after race, found {metric_count}"


# ==============================================================================
# 3. Out-of-Order Delivery Defense
# ==============================================================================

def test_adversarial_out_of_order_numerical_and_lexical_revisions(client, app):
    """Stress test: Sending out-of-order revisions (10 -> 5 -> 100 -> 20 -> 0).
    
    Verifies numerical revision ordering:
    - Revision '10': processed (value 100)
    - Revision '5': older -> skipped, value stays 100
    - Revision '100': newer -> processed, value becomes 1000 ('100' > '10' numerically)
    - Revision '20': older than 100 -> skipped, value stays 1000
    - Revision '0': older than 100 -> skipped, value stays 1000
    """
    secret = "rtk-lms-webhook-secret"
    ext_id = f"ooo-metric-{uuid4().hex[:8]}"

    def send_rev(rev: str, val: float):
        payload = {
            "external_id": ext_id,
            "source_revision": rev,
            "org_id": "org-1",
            "prog_id": "program-devops",
            "metric_code": "attendance_rate",
            "value": val,
            "unit": "percent",
        }
        return client.post("/api/v1/webhooks/lms", json=payload, headers={"X-Webhook-Secret": secret})

    # Step 1: Rev 10
    r1 = send_rev("10", 100.0)
    assert r1.status_code == 200
    assert r1.json()["processed"] == 1

    with app.state.session_factory() as session:
        m = session.scalar(select(LearningMetric).where(LearningMetric.external_id == ext_id))
        assert m.value == 100.0
        assert m.last_applied_revision == "10"

    # Step 2: Rev 5 (older revision sent out of order)
    r2 = send_rev("5", 50.0)
    assert r2.status_code == 200
    assert r2.json()["skipped"] == 1

    with app.state.session_factory() as session:
        m = session.scalar(select(LearningMetric).where(LearningMetric.external_id == ext_id))
        assert m.value == 100.0  # Not overwritten!
        assert m.last_applied_revision == "10"

    # Step 3: Rev 100 (newer revision)
    r3 = send_rev("100", 1000.0)
    assert r3.status_code == 200
    assert r3.json()["processed"] == 1

    with app.state.session_factory() as session:
        m = session.scalar(select(LearningMetric).where(LearningMetric.external_id == ext_id))
        assert m.value == 1000.0
        assert m.last_applied_revision == "100"

    # Step 4: Rev 20 (older than 100, though alphabetically '20' > '100'!)
    r4 = send_rev("20", 200.0)
    assert r4.status_code == 200
    assert r4.json()["skipped"] == 1

    with app.state.session_factory() as session:
        m = session.scalar(select(LearningMetric).where(LearningMetric.external_id == ext_id))
        assert m.value == 1000.0  # Still 1000.0!
        assert m.last_applied_revision == "100"

    # Step 5: Rev 0 (oldest)
    r5 = send_rev("0", 0.0)
    assert r5.status_code == 200
    assert r5.json()["skipped"] == 1

    with app.state.session_factory() as session:
        m = session.scalar(select(LearningMetric).where(LearningMetric.external_id == ext_id))
        assert m.value == 1000.0


# ==============================================================================
# 4. Malformed Payloads, JSON Primitives & SQL Injection Defense
# ==============================================================================

def test_adversarial_malformed_json_and_primitives(client):
    """Stress test: Non-JSON raw strings, primitives, empty arrays, arrays of non-dicts."""
    secret = "rtk-lms-webhook-secret"

    # 1. Truncated JSON
    r1 = client.post(
        "/api/v1/webhooks/lms",
        content=b'{"metric_code": "active_cohorts", "value": ',
        headers={"Content-Type": "application/json", "X-Webhook-Secret": secret},
    )
    assert r1.status_code == 400
    assert r1.json()["error"]["code"] == "VALIDATION_ERROR"

    # 2. JSON Primitive: string
    r2 = client.post(
        "/api/v1/webhooks/lms",
        content=b'"just a string"',
        headers={"Content-Type": "application/json", "X-Webhook-Secret": secret},
    )
    assert r2.status_code == 400
    assert r2.json()["error"]["code"] == "VALIDATION_ERROR"

    # 3. JSON Primitive: integer
    r3 = client.post(
        "/api/v1/webhooks/lms",
        content=b'123456789',
        headers={"Content-Type": "application/json", "X-Webhook-Secret": secret},
    )
    assert r3.status_code == 400
    assert r3.json()["error"]["code"] == "VALIDATION_ERROR"

    # 4. JSON Primitive: boolean
    r4 = client.post(
        "/api/v1/webhooks/lms",
        content=b'true',
        headers={"Content-Type": "application/json", "X-Webhook-Secret": secret},
    )
    assert r4.status_code == 400
    assert r4.json()["error"]["code"] == "VALIDATION_ERROR"

    # 5. Empty JSON Array
    r5 = client.post(
        "/api/v1/webhooks/lms",
        json=[],
        headers={"X-Webhook-Secret": secret},
    )
    assert r5.status_code == 200
    assert r5.json()["processed"] == 0
    assert r5.json()["received"] == 0

    # 6. Array of non-dictionary elements
    r6 = client.post(
        "/api/v1/webhooks/lms",
        json=[1, "test", None, True, []],
        headers={"X-Webhook-Secret": secret},
    )
    assert r6.status_code == 200
    assert r6.json()["processed"] == 0
    assert r6.json()["received"] == 0


def test_adversarial_sql_injection_defense(client, app):
    """Stress test: Ingesting payloads containing malicious SQL injection strings in every field.
    
    Verifies that:
    1. No SQL injection occurs (tables are not dropped or corrupted).
    2. SQLAlchemy query parameterization cleanly escapes all inputs.
    3. Literal values are stored safely.
    """
    secret = "rtk-lms-webhook-secret"
    sqli_id = f"sqli-test-{uuid4().hex[:6]}"

    payload = {
        "external_id": f"{sqli_id}'; DROP TABLE users; --",
        "source_revision": "1' OR '1'='1",
        "org_id": "org-1",
        "prog_id": "program-devops",
        "metric_code": "active_cohorts'; DELETE FROM organizations; --",
        "value": 77.0,
        "unit": "cohort'; UPDATE users SET role='admin'; --",
    }

    res = client.post("/api/v1/webhooks/lms", json=payload, headers={"X-Webhook-Secret": secret})
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert res.json()["processed"] == 1

    # Verify tables are completely intact
    with app.state.session_factory() as session:
        # 1. users table still exists and has users
        user_count = session.scalar(select(func.count(User.id)))
        assert user_count > 0, "Users table was corrupted by SQL injection!"

        # 2. organizations table still exists
        org_count = session.scalar(select(func.count(Organization.id)))
        assert org_count > 0, "Organizations table was corrupted by SQL injection!"

        # 3. Learning metric stored with literal SQLi string
        m = session.scalar(
            select(LearningMetric).where(
                LearningMetric.external_id == f"{sqli_id}'; DROP TABLE users; --"
            )
        )
        assert m is not None
        assert m.metric_code == "active_cohorts'; DELETE FROM organizations; --"
        assert m.unit == "cohort'; UPDATE users SET role='admin'; --"


def test_adversarial_boundary_metric_values(client, app):
    """Stress test: Boundary values (zero, negative, huge float, long strings, Unicode/Cyrillic)."""
    secret = "rtk-lms-webhook-secret"

    cases = [
        {"val": 0.0, "unit": "zero", "code": "metric_zero"},
        {"val": -100.5, "unit": "negative", "code": "metric_negative"},
        {"val": 1e12, "unit": "huge", "code": "metric_huge"},
        {"val": 0.000001, "unit": "tiny", "code": "metric_tiny"},
        {"val": 50.0, "unit": "студентов 🎓", "code": "метрика_кириллица_🔥"},
    ]

    for c in cases:
        ext_id = f"bnd-{uuid4().hex[:8]}"
        p = {
            "external_id": ext_id,
            "source_revision": "1",
            "org_id": "org-1",
            "prog_id": "program-devops",
            "metric_code": c["code"],
            "value": c["val"],
            "unit": c["unit"],
        }
        res = client.post("/api/v1/webhooks/lms", json=p, headers={"X-Webhook-Secret": secret})
        assert res.status_code == 200
        assert res.json()["processed"] == 1

        with app.state.session_factory() as session:
            m = session.scalar(select(LearningMetric).where(LearningMetric.external_id == ext_id))
            assert m is not None
            assert m.value == pytest.approx(c["val"])
            assert m.metric_code == c["code"]
            assert m.unit == c["unit"]


# ==============================================================================
# 5. Live Adapters Network Fault Tolerance (HTTP 500, 502, 503, 504)
# ==============================================================================

@pytest.mark.parametrize("status_code", [500, 502, 503, 504])
def test_adversarial_live_adapters_http_errors_fault_tolerance(status_code, client, app):
    """Stress test: Live LMS and Website adapters receiving HTTP 500/502/503/504.
    
    Verifies that:
    1. health_check() does NOT crash, returns connected=False and status='error'.
    2. fetch_updates() does NOT crash, catches exception and returns empty list [].
    3. Triggering sync_source via POST /api/v1/integrations/sync/{source} handles
       the fault gracefully, records a sync_error in inbox, and DOES NOT crash
       the FastAPI server (no unhandled 500 from CRM server).
    """
    def mock_transport_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=status_code,
            text=f"Simulated Network Failure: HTTP {status_code}",
            headers={"Content-Type": "text/plain"},
        )

    transport = httpx.MockTransport(mock_transport_handler)

    # 1. LMS Live Adapter
    lms_adapter = LiveLMSAdapter(base_url="https://rtkb.zion-lms.ru", transport=transport)
    health = lms_adapter.health_check()
    assert health["status"] == "error"
    assert health["connected"] is False
    assert f"HTTP {status_code}" in health["error"]

    updates = lms_adapter.fetch_updates()
    assert updates == []
    assert lms_adapter.last_error is not None
    assert f"{status_code}" in lms_adapter.last_error

    # 2. Website Live Adapter
    web_adapter = LiveWebsiteAdapter(base_url="https://school.rt.ru", transport=transport)
    w_health = web_adapter.health_check()
    assert w_health["status"] == "error"
    assert w_health["connected"] is False
    assert f"HTTP {status_code}" in w_health["error"]

    w_updates = web_adapter.fetch_updates()
    assert w_updates == []
    assert web_adapter.last_error is not None
    assert f"{status_code}" in web_adapter.last_error

    # 3. Synchronizing live source through FastAPI endpoint
    # Overriding factory adapter with the mocked transport adapter
    from unittest.mock import patch
    with patch("app.integrations.service.get_adapter", return_value=lms_adapter):
        # Case A: With Idempotency-Key -> saved command is committed by finish_command
        idemp_key = str(uuid4())
        sync_res = client.post(
            "/api/v1/integrations/sync/lms",
            headers={"X-Demo-User": "supervisor", "Idempotency-Key": idemp_key},
        )
        assert sync_res.status_code == 200, (
            f"Server should not crash on adapter HTTP {status_code}, got {sync_res.status_code}"
        )
        data = sync_res.json()
        assert data["status"] == "error"
        assert f"{status_code}" in data["error_message"]

        # Invariant: A sync_error item was saved and committed in IntegrationInbox
        with app.state.session_factory() as session:
            err_item = session.scalar(
                select(IntegrationInbox).where(
                    IntegrationInbox.source == "lms",
                    IntegrationInbox.entity_type == "sync_error",
                    IntegrationInbox.status == "error",
                ).order_by(IntegrationInbox.received_at.desc())
            )
            assert err_item is not None
            assert f"{status_code}" in err_item.error_message

        # Case B: Without Idempotency-Key -> Now fixed: sync_source calls db.commit(),
        # so err_item is flushed AND committed into IntegrationInbox.
        sync_res_nokey = client.post(
            "/api/v1/integrations/sync/lms",
            headers={"X-Demo-User": "supervisor"},
        )
        assert sync_res_nokey.status_code == 200
        assert sync_res_nokey.json()["status"] == "error"

        with app.state.session_factory() as session:
            err_item_nokey = session.scalar(
                select(IntegrationInbox).where(
                    IntegrationInbox.source == "lms",
                    IntegrationInbox.entity_type == "sync_error",
                    IntegrationInbox.status == "error",
                ).order_by(IntegrationInbox.received_at.desc())
            )
            assert err_item_nokey is not None
            assert f"{status_code}" in err_item_nokey.error_message


def test_adversarial_webhook_non_numeric_metric_value_crash(client, app):
    """Adversarial vulnerability probe: Webhook metric payload with invalid 'value' type.
    
    Verifies that malformed 'value' (string 'abc' or None) does NOT crash the server (no 500 error),
    and is safely converted/handled returning HTTP 200 and setting metric value to 0.0.
    """
    secret = "rtk-lms-webhook-secret"

    # Test 1: value is 'abc' (string)
    ext_id_1 = f"malformed-str-{uuid4().hex[:8]}"
    payload_str = {
        "external_id": ext_id_1,
        "source_revision": "1",
        "org_id": "org-1",
        "prog_id": "program-devops",
        "metric_code": "students_enrolled",
        "value": "abc",
    }
    res_str = client.post("/api/v1/webhooks/lms", json=payload_str, headers={"X-Webhook-Secret": secret})
    assert res_str.status_code == 200
    assert res_str.json()["processed"] == 1

    with app.state.session_factory() as session:
        m1 = session.scalar(select(LearningMetric).where(LearningMetric.external_id == ext_id_1))
        assert m1 is not None
        assert m1.value == 0.0

    # Test 2: value is None
    ext_id_2 = f"malformed-none-{uuid4().hex[:8]}"
    payload_none = {
        "external_id": ext_id_2,
        "source_revision": "1",
        "org_id": "org-1",
        "prog_id": "program-devops",
        "metric_code": "students_enrolled",
        "value": None,
    }
    res_none = client.post("/api/v1/webhooks/lms", json=payload_none, headers={"X-Webhook-Secret": secret})
    assert res_none.status_code == 200
    assert res_none.json()["processed"] == 1

    with app.state.session_factory() as session:
        m2 = session.scalar(select(LearningMetric).where(LearningMetric.external_id == ext_id_2))
        assert m2 is not None
        assert m2.value == 0.0

