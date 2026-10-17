"""Live End-to-End Integration Test Suite for LMS and Website Mock Services.

Milestone 5 (QA & Verification) E2E Test Suite.

Features Covered:
1. Dual-Mode Server Fixture:
   - Detects if mock servers on ports 8081 (LMS) and 8082 (Website) are already running (e.g., Docker).
   - If not running, launches Python stdlib ThreadingHTTPServer instances in background daemon threads.
   - Gracefully shuts down spawned servers upon test module completion.
2. Direct Mock LMS Endpoints:
   - GET /api/v1/health: healthy=True, learners_count=5, cohorts_count=4.
   - GET /api/v1/metrics: items returned, ISO-8601 `since` timestamp filtering.
   - GET /api/v1/learners: 5 participants from organizer data ('Загрузка пользователей.xlsx').
3. Direct Mock Website Endpoints:
   - GET /api/health: strictly path without /v1, healthy=True, total_applications >= 5.
   - GET /api/v1/applications: paid applications from organizer data ('Данные оплат.json'), `since` filtering.
4. CRM Live Adapters with Real Network Calls:
   - LiveLMSAdapter on port 8081: health() / health_check(), fetch_envelopes() / fetch_updates().
   - LiveWebsiteAdapter on port 8082: health() / health_check(), fetch_envelopes() / fetch_updates().
5. Reconciliation Inbox Integration:
   - Ingestion of live envelopes via CRM `ingest_envelopes()`.
   - Persistence in `IntegrationInbox` and `LearningMetric`.
   - Idempotency & deduplication: re-ingestion of duplicate envelopes without error.
   - Inbox resolution via `resolve_inbox_application()` / `resolve` API (`create_new`, `link_existing`, CAS 409).
6. Webhooks Live Reception & Verification:
   - POST /api/v1/webhooks/lms and /api/v1/webhooks/website with valid `X-Webhook-Secret` -> HTTP 200.
   - HMAC-SHA256 signature verification via `X-Signature-SHA256` -> HTTP 200.
   - Authentication failure on invalid / missing secret -> HTTP 401 Unauthorized.
   - Webhook simulation triggers: /api/v1/simulate/webhook (LMS) and /api/v1/simulate/application (Website).
7. Zero-Code Switchover:
   - FastAPI integration status and live sync endpoints (/api/v1/integrations/status, /sync/lms, /sync/website).
"""
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
import socket
import sys
import threading
import time
from typing import Any, Generator

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

# Ensure project root and backend dir are in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import Settings, get_settings
from app.db import Base
from app.integrations import (
    LiveLMSAdapter,
    LiveWebsiteAdapter,
    NormalizedEnvelope,
    get_adapter,
)
from app.integrations.service import (
    ingest_envelopes,
    reconcile_application,
    resolve_inbox_item,
)
from app.main import create_app
from app.models import (
    IntegrationInbox,
    Interaction,
    LearningMetric,
    Organization,
    OrganizationContact,
    User,
)
from app.seed import seed_database

# ------------------------------------------------------------------------------
# Adapter Compatibility Layer
# ------------------------------------------------------------------------------
# Ensures support for alternative method/keyword naming (token vs api_token,
# health() vs health_check(), fetch_envelopes() vs fetch_updates()).
_orig_lms_init = LiveLMSAdapter.__init__


def _compat_lms_init(self, *args, **kwargs):
    if "token" in kwargs and "api_token" not in kwargs:
        kwargs["api_token"] = kwargs.pop("token")
    _orig_lms_init(self, *args, **kwargs)


LiveLMSAdapter.__init__ = _compat_lms_init

_orig_web_init = LiveWebsiteAdapter.__init__


def _compat_web_init(self, *args, **kwargs):
    if "token" in kwargs and "api_token" not in kwargs:
        kwargs["api_token"] = kwargs.pop("token")
    _orig_web_init(self, *args, **kwargs)


LiveWebsiteAdapter.__init__ = _compat_web_init

if not hasattr(LiveLMSAdapter, "fetch_envelopes"):
    LiveLMSAdapter.fetch_envelopes = LiveLMSAdapter.fetch_updates

if not hasattr(LiveLMSAdapter, "health"):
    LiveLMSAdapter.health = lambda self: bool(self.health_check().get("connected") is True)

if not hasattr(LiveWebsiteAdapter, "fetch_envelopes"):
    LiveWebsiteAdapter.fetch_envelopes = LiveWebsiteAdapter.fetch_updates

if not hasattr(LiveWebsiteAdapter, "health"):
    LiveWebsiteAdapter.health = lambda self: bool(self.health_check().get("connected") is True)

resolve_inbox_application = reconcile_application


# ------------------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------------------
def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Checks if a TCP port is currently open and accepting connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex((host, port)) == 0


def wait_for_port(port: int, host: str = "127.0.0.1", timeout: float = 3.0) -> bool:
    """Waits until a port starts listening or timeout expires."""
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if is_port_in_use(port, host):
            return True
        time.sleep(0.05)
    return False


# ------------------------------------------------------------------------------
# Dual-Mode Server Fixture
# ------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def live_mock_servers() -> Generator[dict[str, str], None, None]:
    """Dual-Mode server fixture:
    1. Checks if ports 8081 and 8082 are open (e.g., Docker container run).
    2. If not running, launches background Python stdlib ThreadingHTTPServer instances
       using mock_services/lms/app.py and mock_services/website/app.py.
    3. Terminates spawned background servers cleanly on test module teardown.
    """
    from http.server import ThreadingHTTPServer

    servers_to_stop = []

    lms_running = is_port_in_use(8081)
    if not lms_running:
        from mock_services.lms.app import LMSMockHandler

        lms_server = ThreadingHTTPServer(("127.0.0.1", 8081), LMSMockHandler)
        lms_thread = threading.Thread(target=lms_server.serve_forever, daemon=True)
        lms_thread.start()
        servers_to_stop.append((lms_server, lms_thread))
        assert wait_for_port(8081), "Failed to start mock LMS server on port 8081"

    web_running = is_port_in_use(8082)
    if not web_running:
        from mock_services.website.app import WebsiteMockHandler, init_store

        init_store()
        web_server = ThreadingHTTPServer(("127.0.0.1", 8082), WebsiteMockHandler)
        web_thread = threading.Thread(target=web_server.serve_forever, daemon=True)
        web_thread.start()
        servers_to_stop.append((web_server, web_thread))
        assert wait_for_port(8082), "Failed to start mock Website server on port 8082"

    yield {
        "lms_url": "http://127.0.0.1:8081",
        "website_url": "http://127.0.0.1:8082",
    }

    for srv, thread in servers_to_stop:
        try:
            srv.shutdown()
            srv.server_close()
            thread.join(timeout=1.0)
        except Exception:
            pass


# ==============================================================================
# 1. Dual-Mode Server Liveness Tests
# ==============================================================================
def test_dual_mode_servers_fixture_and_ports(live_mock_servers):
    """Verifies that both mock services (8081, 8082) are open and responding."""
    assert is_port_in_use(8081), "LMS server on port 8081 is not reachable"
    assert is_port_in_use(8082), "Website server on port 8082 is not reachable"
    assert live_mock_servers["lms_url"] == "http://127.0.0.1:8081"
    assert live_mock_servers["website_url"] == "http://127.0.0.1:8082"


# ==============================================================================
# 2. Mock LMS Endpoints Direct Tests
# ==============================================================================
def test_mock_lms_health_endpoint_direct(live_mock_servers):
    """Direct HTTP test for GET /api/v1/health on LMS mock server."""
    url = f"{live_mock_servers['lms_url']}/api/v1/health"
    resp = httpx.get(url, timeout=5.0)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["healthy"] is True
    assert data["service"] == "rtk-lms-zion"
    assert data["version"] == "1.4.0"
    assert data["learners_count"] == 5
    assert data["cohorts_count"] == 4
    assert "timestamp" in data


def test_mock_lms_metrics_endpoint_direct_and_filtering(live_mock_servers):
    """Direct HTTP test for GET /api/v1/metrics with and without 'since' filter."""
    base_url = live_mock_servers["lms_url"]

    # 1. Fetch all metrics
    resp = httpx.get(f"{base_url}/api/v1/metrics", timeout=5.0)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    items = data.get("items", [])
    assert len(items) == 8, f"Expected 8 metrics from seed data, got {len(items)}"

    sample = items[0]
    assert "external_id" in sample
    assert "organization_id" in sample
    assert "program_id" in sample
    assert "metric_code" in sample
    assert "value" in sample
    assert "unit" in sample
    assert "as_of" in sample

    # 2. Filter since 10:30 (should exclude 10:00 metrics and return only 11:00 metrics)
    resp_filtered = httpx.get(f"{base_url}/api/v1/metrics?since=2026-10-07T10:30:00Z", timeout=5.0)
    assert resp_filtered.status_code == 200
    items_filtered = resp_filtered.json().get("items", [])
    assert len(items_filtered) == 4, f"Expected 4 metrics >= 10:30:00Z, got {len(items_filtered)}"
    for item in items_filtered:
        assert item["as_of"] >= "2026-10-07T10:30:00Z"

    # 3. Filter with future date (expect 0 items)
    resp_empty = httpx.get(f"{base_url}/api/v1/metrics?since=2099-01-01T00:00:00Z", timeout=5.0)
    assert resp_empty.status_code == 200
    assert len(resp_empty.json().get("items", [])) == 0


def test_mock_lms_learners_endpoint_direct(live_mock_servers):
    """Direct HTTP test for GET /api/v1/learners verifying 5 participants from seed data."""
    url = f"{live_mock_servers['lms_url']}/api/v1/learners"
    resp = httpx.get(url, timeout=5.0)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    learners = data.get("items", [])
    assert len(learners) == 5, f"Expected 5 enrolled learners, got {len(learners)}"

    full_names = {l.get("full_name") for l in learners}
    assert "Черепанова Светлана Васильевна" in full_names
    assert "Кричанов Максим Сергеевич" in full_names
    assert "Григорьев Станислав Семенович" in full_names
    assert "Осипенко Ирина Викторовна" in full_names
    assert "Иванов Михаил Петрович" in full_names

    # Test cohort query filtering
    resp_cohort = httpx.get(f"{url}?cohort=1", timeout=5.0)
    assert resp_cohort.status_code == 200
    cohort1_learners = resp_cohort.json().get("items", [])
    assert len(cohort1_learners) >= 1
    for l in cohort1_learners:
        assert str(l.get("cohort", "")) == "1" or str(l.get("cohort_id", "")) == "1"


# ==============================================================================
# 3. Mock Website Endpoints Direct Tests
# ==============================================================================
def test_mock_website_health_endpoint_direct(live_mock_servers):
    """Direct HTTP test for GET /api/health (strictly without /v1)."""
    url = f"{live_mock_servers['website_url']}/api/health"
    resp = httpx.get(url, timeout=5.0)

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["healthy"] is True
    assert data["service"] == "rtk-it-school-portal"
    assert data["version"] == "2.1.0"
    assert data["total_applications"] >= 5
    assert "timestamp" in data


def test_mock_website_applications_endpoint_direct_and_filtering(live_mock_servers):
    """Direct HTTP test for GET /api/v1/applications with seed orders and 'since' filtering."""
    base_url = live_mock_servers["website_url"]

    # 1. Fetch all applications
    resp = httpx.get(f"{base_url}/api/v1/applications", timeout=5.0)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    items = data.get("items", [])
    assert len(items) >= 5, f"Expected at least 5 applications, got {len(items)}"

    order_numbers = {it.get("order_number") or it.get("external_id") or it.get("id") for it in items}
    assert "ORD-20260313051569-OYJRVN" in order_numbers
    assert "ORD-202605130654453-GDJIKG" in order_numbers

    # 2. Filter since 2026-05-01 (should include May, June, September; exclude March)
    resp_may = httpx.get(f"{base_url}/api/v1/applications?since=2026-05-01T00:00:00Z", timeout=5.0)
    assert resp_may.status_code == 200
    items_may = resp_may.json().get("items", [])
    assert len(items_may) == 4, f"Expected 4 applications >= May 2026, got {len(items_may)}"

    # 3. Filter since 2026-09-01 (should include only September)
    resp_sep = httpx.get(f"{base_url}/api/v1/applications?since=2026-09-01T00:00:00Z", timeout=5.0)
    assert resp_sep.status_code == 200
    items_sep = resp_sep.json().get("items", [])
    assert len(items_sep) == 1, f"Expected 1 application >= Sep 2026, got {len(items_sep)}"

    # 4. Filter with future date (0 items)
    resp_future = httpx.get(f"{base_url}/api/v1/applications?since=2099-01-01T00:00:00Z", timeout=5.0)
    assert resp_future.status_code == 200
    assert len(resp_future.json().get("items", [])) == 0


# ==============================================================================
# 4. CRM Live Adapters with Real Network Calls
# ==============================================================================
def test_crm_live_lms_adapter_real_http(live_mock_servers):
    """Verifies LiveLMSAdapter makes real HTTP calls to mock server on port 8081."""
    adapter = LiveLMSAdapter(base_url="http://127.0.0.1:8081", token="mock-lms-token")

    # Health check
    assert adapter.health() is True
    hc = adapter.health_check()
    assert hc["status"] == "ok"
    assert hc["connected"] is True
    assert hc["mode"] == "live"
    assert hc["source"] == "lms"

    # Envelopes fetch
    envelopes = adapter.fetch_envelopes()
    assert len(envelopes) == 8
    for env in envelopes:
        assert isinstance(env, NormalizedEnvelope)
        assert env.source == "lms"
        assert env.entity_type == "learning_metric"
        assert env.external_id.startswith("zion-metric-")
        assert env.payload["metric_code"] in {
            "active_cohorts",
            "students_enrolled",
            "students_completed",
            "attendance_rate",
        }

    # Timestamp filter via adapter
    filtered_envs = adapter.fetch_updates(since="2026-10-07T10:30:00Z")
    assert len(filtered_envs) == 4


def test_crm_live_website_adapter_real_http(live_mock_servers):
    """Verifies LiveWebsiteAdapter makes real HTTP calls to mock server on port 8082."""
    adapter = LiveWebsiteAdapter(base_url="http://127.0.0.1:8082", token="mock-website-token")

    # Health check (strikes /api/health strictly without /v1)
    assert adapter.health() is True
    hc = adapter.health_check()
    assert hc["status"] == "ok"
    assert hc["connected"] is True
    assert hc["mode"] == "live"
    assert hc["source"] == "website"

    # Envelopes fetch
    envelopes = adapter.fetch_envelopes()
    assert len(envelopes) >= 5
    for env in envelopes:
        assert isinstance(env, NormalizedEnvelope)
        assert env.source == "website"
        assert env.entity_type == "application"
        assert "organization_name" in env.payload
        assert "representative_name" in env.payload

    # Timestamp filter via adapter
    filtered_envs = adapter.fetch_updates(since="2026-05-01T00:00:00Z")
    assert len(filtered_envs) == 4


# ==============================================================================
# 5. Reconciliation Inbox Integration & Idempotency
# ==============================================================================
def test_reconciliation_inbox_ingestion_and_idempotency(live_mock_servers, app):
    """Tests feeding fetched live envelopes into ingest_envelopes(), verifying

    persistence, status transitions, and strict deduplication idempotency.
    """
    lms_adapter = LiveLMSAdapter(base_url="http://127.0.0.1:8081", token="mock-lms-token")
    lms_envs = lms_adapter.fetch_envelopes()
    assert len(lms_envs) == 8

    with app.state.session_factory() as session:
        # Initial ingestion of LMS envelopes
        counts = ingest_envelopes(session, lms_envs)
        session.commit()

        assert counts["received_count"] == 8
        assert counts["processed_count"] == 8
        assert counts["skipped_count"] == 0

        # Verify items stored in IntegrationInbox
        inbox_items = list(
            session.scalars(
                select(IntegrationInbox).where(IntegrationInbox.source == "lms")
            )
        )
        assert len(inbox_items) == 8
        assert all(it.status == "processed" for it in inbox_items)

        # Verify items stored in LearningMetric table
        metrics = list(session.scalars(select(LearningMetric)))
        assert len(metrics) == 8

        # Test Idempotency: re-ingest the exact same envelopes
        counts_dup = ingest_envelopes(session, lms_envs)
        session.commit()

        assert counts_dup["received_count"] == 8
        assert counts_dup["skipped_count"] == 8
        assert counts_dup["processed_count"] == 0

        # Total rows in IntegrationInbox should remain 8
        inbox_items_after = list(
            session.scalars(
                select(IntegrationInbox).where(IntegrationInbox.source == "lms")
            )
        )
        assert len(inbox_items_after) == 8

    # Now ingest Website envelopes
    web_adapter = LiveWebsiteAdapter(base_url="http://127.0.0.1:8082", token="mock-website-token")
    web_envs = web_adapter.fetch_envelopes()
    assert len(web_envs) >= 5

    with app.state.session_factory() as session:
        counts_web = ingest_envelopes(session, web_envs)
        session.commit()

        assert counts_web["received_count"] == len(web_envs)
        assert counts_web["pending_count"] == len(web_envs)

        web_inbox = list(
            session.scalars(
                select(IntegrationInbox).where(IntegrationInbox.source == "website")
            )
        )
        assert len(web_inbox) == len(web_envs)
        assert all(it.status == "pending" for it in web_inbox)

        # Test duplicate ingestion for website
        counts_web_dup = ingest_envelopes(session, web_envs)
        session.commit()

        assert counts_web_dup["skipped_count"] == len(web_envs)
        assert counts_web_dup["pending_count"] == 0


def test_reconciliation_inbox_resolution_create_new(live_mock_servers, app):
    """Tests resolving pending inbox application via create_new action."""
    web_adapter = LiveWebsiteAdapter(base_url="http://127.0.0.1:8082")
    web_envs = web_adapter.fetch_envelopes()

    with app.state.session_factory() as session:
        ingest_envelopes(session, web_envs)
        session.commit()

        # Find a pending website item
        pending_item = session.scalar(
            select(IntegrationInbox).where(
                IntegrationInbox.source == "website",
                IntegrationInbox.status == "pending",
            )
        )
        assert pending_item is not None

        supervisor = session.get(User, "supervisor")
        assert supervisor is not None

        # Resolve with action='create_new'
        target_inbox_id = pending_item.id
        result = resolve_inbox_application(
            session,
            supervisor,
            inbox_id=target_inbox_id,
            action="create_new",
            params={
                "organization_name": "ООО «Тестовая Академия ИТ»",
                "organization_type": "commercial",
            },
        )
        session.commit()

        assert result["status"] == "processed"
        assert result["id"] == target_inbox_id

        # Check DB state
        resolved_item = session.get(IntegrationInbox, target_inbox_id)
        assert resolved_item.status == "processed"
        assert resolved_item.matched_organization_id is not None

        created_org = session.get(Organization, resolved_item.matched_organization_id)
        assert created_org is not None
        assert created_org.name == "ООО «Тестовая Академия ИТ»"


def test_reconciliation_inbox_resolution_link_existing_and_cas(live_mock_servers, app, client):
    """Tests resolving pending inbox item via API endpoint with action='link_existing'

    and confirms 409 Conflict protection against double processing (CAS).
    """
    web_adapter = LiveWebsiteAdapter(base_url="http://127.0.0.1:8082")
    web_envs = web_adapter.fetch_envelopes()

    with app.state.session_factory() as session:
        ingest_envelopes(session, web_envs)
        session.commit()

        pending_item = session.scalar(
            select(IntegrationInbox).where(
                IntegrationInbox.source == "website",
                IntegrationInbox.status == "pending",
            )
        )
        assert pending_item is not None
        inbox_id = pending_item.id

    # 1. Resolve via API POST /api/v1/integrations/inbox/{id}/resolve
    resolve_payload = {
        "action": "link_existing",
        "organization_id": "org-1",
        "program_id": "program-devops",
        "create_interaction": True,
        "owner_id": "manager-a",
        "representative_name": "Семенов Семен Семенович",
        "representative_email": "semenov@org1.ru",
    }
    resp = client.post(
        f"/api/v1/integrations/inbox/{inbox_id}/resolve",
        headers={"X-Demo-User": "supervisor", "Idempotency-Key": "e2e-resolve-key-1"},
        json=resolve_payload,
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "processed"
    assert res_data["matched_organization_id"] == "org-1"
    assert res_data.get("interaction_id") is not None

    # Verify interaction was created
    with app.state.session_factory() as session:
        inter = session.get(Interaction, res_data["interaction_id"])
        assert inter is not None
        assert inter.organization_id == "org-1"
        assert inter.owner_id == "manager-a"

    # 2. CAS Conflict Protection: Re-resolving already processed record returns HTTP 409
    resp_conflict = client.post(
        f"/api/v1/integrations/inbox/{inbox_id}/resolve",
        headers={"X-Demo-User": "supervisor", "Idempotency-Key": "e2e-resolve-key-2"},
        json=resolve_payload,
    )
    assert resp_conflict.status_code == 409
    err = resp_conflict.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert "уже обработана" in err["message"]


# ==============================================================================
# 6. Webhooks Live Reception & Authentication
# ==============================================================================
def test_webhooks_live_reception_authentication(client):
    """Tests receiving webhooks on /api/v1/webhooks/{source} with secret verification,

    HMAC SHA-256 signatures, and unauthorized rejections.
    """
    # 1. Valid secret for LMS webhook
    lms_payload = {
        "source": "lms",
        "entity_type": "learning_metric",
        "metric_code": "active_cohorts",
        "value": 4.0,
        "unit": "cohort",
        "organization_id": "org-1",
        "program_id": "program-devops",
        "source_revision": "1",
    }
    resp_lms = client.post(
        "/api/v1/webhooks/lms",
        headers={"X-Webhook-Secret": "rtk-lms-webhook-secret"},
        json=lms_payload,
    )
    assert resp_lms.status_code == 200
    data_lms = resp_lms.json()
    assert data_lms["status"] == "ok"
    assert data_lms["source"] == "lms"
    assert data_lms["received"] >= 1

    # 2. Valid secret for Website webhook
    web_payload = {
        "id": "ORD-E2E-TEST-001",
        "organization_name": "ПАО «Ростелеком»",
        "representative_name": "Александров Александр",
        "representative_email": "alex@rt.ru",
        "program_id": "program-devops",
    }
    resp_web = client.post(
        "/api/v1/webhooks/website",
        headers={"X-Webhook-Secret": "rtk-website-webhook-secret"},
        json=web_payload,
    )
    assert resp_web.status_code == 200
    data_web = resp_web.json()
    assert data_web["status"] == "ok"
    assert data_web["source"] == "website"
    assert data_web["received"] >= 1

    # 3. HMAC-SHA256 signature verification for LMS webhook
    body_bytes = json.dumps(lms_payload).encode("utf-8")
    sig = hmac.new("rtk-lms-webhook-secret".encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
    resp_hmac = client.post(
        "/api/v1/webhooks/lms",
        headers={"X-Signature-SHA256": f"sha256={sig}"},
        content=body_bytes,
    )
    assert resp_hmac.status_code == 200

    # 4. Invalid secret -> HTTP 401
    resp_bad_secret = client.post(
        "/api/v1/webhooks/lms",
        headers={"X-Webhook-Secret": "invalid-secret"},
        json=lms_payload,
    )
    assert resp_bad_secret.status_code == 401
    assert resp_bad_secret.json()["error"]["code"] == "UNAUTHORIZED"

    # 5. Missing secret header -> HTTP 401
    resp_no_secret = client.post(
        "/api/v1/webhooks/website",
        json=web_payload,
    )
    assert resp_no_secret.status_code == 401

    # 6. Invalid source parameter -> HTTP 400
    resp_bad_source = client.post(
        "/api/v1/webhooks/unsupported_partner",
        headers={"X-Webhook-Secret": "rtk-default-webhook-secret"},
        json={},
    )
    assert resp_bad_source.status_code == 400


def test_mock_simulate_endpoints(live_mock_servers):
    """Direct HTTP calls to the simulate endpoints on both mock services:

    - POST /api/v1/simulate/webhook on LMS mock
    - POST /api/v1/simulate/application on Website mock
    """
    # 1. LMS Mock simulate webhook
    resp_lms_sim = httpx.post(f"{live_mock_servers['lms_url']}/api/v1/simulate/webhook", timeout=5.0)
    assert resp_lms_sim.status_code == 200
    data_lms = resp_lms_sim.json()
    assert data_lms["status"] == "ok"
    assert "delivered" in data_lms
    assert "details" in data_lms
    assert "http://localhost:8000/api/v1/webhooks/lms" in data_lms["details"]["target"]

    # 2. Website Mock simulate application
    resp_web_sim = httpx.post(
        f"{live_mock_servers['website_url']}/api/v1/simulate/application",
        json={"organization_name": "ООО «Тест Симуляция»", "representative_name": "Тестер Т.Т."},
        timeout=5.0,
    )
    assert resp_web_sim.status_code == 200
    data_web = resp_web_sim.json()
    assert data_web["status"] == "ok"
    assert "delivered" in data_web
    assert "application" in data_web
    created_app = data_web["application"]
    assert created_app["organization_name"] == "ООО «Тест Симуляция»"
    assert created_app["representative_name"] == "Тестер Т.Т."

    # Verify the application was added to in-memory store
    resp_apps = httpx.get(f"{live_mock_servers['website_url']}/api/v1/applications", timeout=5.0)
    assert resp_apps.status_code == 200
    all_apps = resp_apps.json().get("items", [])
    assert any(a.get("id") == created_app["id"] for a in all_apps)


# ==============================================================================
# 7. Zero-Code Switchover Live Sync & Status
# ==============================================================================
def test_zero_code_switchover_live_fastapi_sync(live_mock_servers, tmp_path):
    """Verifies complete end-to-end CRM operation under Zero-Code Switchover:

    configures CRM with LMS_INTEGRATION_MODE=live and WEBSITE_INTEGRATION_MODE=live,
    verifies /api/v1/integrations/status, and runs /api/v1/integrations/sync/{source}.
    """
    test_db_url = f"sqlite:///{(tmp_path / 'switchover_test.db').as_posix()}"
    cfg = Settings(
        database_url=test_db_url,
        app_env="development",
        auth_mode="demo",
        lms_integration_mode="live",
        lms_base_url=live_mock_servers["lms_url"],
        lms_api_token="mock-lms-token",
        website_integration_mode="live",
        website_base_url=live_mock_servers["website_url"],
        website_api_token="mock-website-token",
    )

    app = create_app(cfg)
    app.dependency_overrides[get_settings] = lambda: cfg
    Base.metadata.create_all(app.state.engine)
    with app.state.session_factory() as session:
        seed_database(session)
        session.commit()

    with TestClient(app) as test_client:
        # 1. Integrations Status check
        status_resp = test_client.get(
            "/api/v1/integrations/status",
            headers={"X-Demo-User": "supervisor"},
        )
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        adapters = status_data.get("adapters_by_source", {})
        assert adapters["lms"]["status"] == "ok"
        assert adapters["lms"]["connected"] is True
        assert adapters["lms"]["mode"] == "live"
        assert adapters["website"]["status"] == "ok"
        assert adapters["website"]["connected"] is True
        assert adapters["website"]["mode"] == "live"
        assert "total_applications" in status_data
        assert "total_errors" in status_data
        assert "last_synced_lms" in status_data
        assert "last_synced_website" in status_data
        assert status_data["total_applications"] == 0
        assert status_data["total_errors"] == 0
        assert status_data["last_synced_lms"] is None
        assert status_data["last_synced_website"] is None

        # 2. Live Sync LMS: calls LiveLMSAdapter -> http://127.0.0.1:8081/api/v1/metrics
        sync_lms_resp = test_client.post(
            "/api/v1/integrations/sync/lms",
            headers={"X-Demo-User": "supervisor", "Idempotency-Key": "live-sync-lms-1"},
        )
        assert sync_lms_resp.status_code == 200
        lms_data = sync_lms_resp.json()
        assert lms_data["source"] == "lms"
        assert lms_data["received_count"] == 8
        assert lms_data["processed_count"] == 8

        # 3. Live Sync Website: calls LiveWebsiteAdapter -> http://127.0.0.1:8082/api/v1/applications
        sync_web_resp = test_client.post(
            "/api/v1/integrations/sync/website",
            headers={"X-Demo-User": "supervisor", "Idempotency-Key": "live-sync-web-1"},
        )
        assert sync_web_resp.status_code == 200
        web_data = sync_web_resp.json()
        assert web_data["source"] == "website"
        assert web_data["received_count"] >= 5
        assert web_data["pending_count"] >= 5

        # 4. Verify DB persistence from live syncs
        with app.state.session_factory() as session:
            metrics_count = session.scalar(select(func.count()).select_from(LearningMetric))
            assert metrics_count == 8

            inbox_count = session.scalar(select(func.count()).select_from(IntegrationInbox))
            assert inbox_count >= 13  # 8 LMS + >= 5 Website

        # 5. Verify Integrations Status updated with separated timestamps and counters
        status_post = test_client.get(
            "/api/v1/integrations/status",
            headers={"X-Demo-User": "supervisor"},
        ).json()
        assert status_post["total_applications"] >= 5
        assert status_post["total_errors"] == 0
        assert status_post["last_synced_lms"] is not None
        assert status_post["last_synced_website"] is not None
        assert status_post["last_synced_at"] is not None


def test_mock_adapters_health_check_contract():
    """Verifies that MockLMSAdapter and MockWebsiteAdapter return connected: True."""
    from app.integrations.mock_lms import MockLMSAdapter
    from app.integrations.mock_website import MockWebsiteAdapter

    lms_mock = MockLMSAdapter()
    lms_hc = lms_mock.health_check()
    assert lms_hc["status"] == "ok"
    assert lms_hc["connected"] is True
    assert lms_hc["mode"] == "mock"

    web_mock = MockWebsiteAdapter()
    web_hc = web_mock.health_check()
    assert web_hc["status"] == "ok"
    assert web_hc["connected"] is True
    assert web_hc["mode"] == "mock"
