"""Comprehensive test suite for Live LMS and Website integration adapters (TASK-P02).

Covers:
1. Factory get_adapter instantiation for mock and live modes.
2. LiveLMSAdapter:
   - Health check: 200 OK, HTTP 500, ConnectError, TimeoutException.
   - Fetch updates: payload structure, envelope fields, ISO-8601 since query param & filter.
   - Authorization Bearer header sending.
   - Graceful degradation on network errors and HTTP 5xx.
   - Timeout configuration (connect=5.0s, read=30.0s).
3. LiveWebsiteAdapter:
   - Health check at /api/health: 200 OK, HTTP 500, ConnectError, TimeoutException.
   - Fetch updates at /api/v1/applications: NormalizedEnvelope(source="website", entity_type="application").
   - Authorization Bearer header sending.
   - Graceful degradation on network anomalies.
4. End-to-end integration via FastAPI client with live adapters configured:
   - Ingestion into IntegrationInbox and LearningMetric under live mode.
   - Graceful handling of network failures during sync without 500 errors.
   - Integrations status reporting live adapter health.
"""
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import func, select

from app.config import Settings
from app.integrations import (
    BaseIntegrationAdapter,
    LiveLMSAdapter,
    LiveWebsiteAdapter,
    MockLMSAdapter,
    MockWebsiteAdapter,
    NormalizedEnvelope,
    get_adapter,
)
from app.models import IntegrationInbox, LearningMetric


# ==============================================================================
# 1. Factory get_adapter tests
# ==============================================================================

def test_factory_returns_mock_adapters_by_default():
    cfg = Settings(lms_integration_mode="mock", website_integration_mode="mock")
    lms = get_adapter("lms", cfg)
    web = get_adapter("website", cfg)

    assert isinstance(lms, MockLMSAdapter)
    assert isinstance(web, MockWebsiteAdapter)
    assert lms.base_url == cfg.lms_base_url
    assert web.base_url == cfg.website_base_url


def test_factory_returns_live_adapters_when_configured():
    cfg = Settings(
        lms_integration_mode="live",
        website_integration_mode="live",
        lms_base_url="https://live-lms.example.com",
        website_base_url="https://live-website.example.com",
    )
    lms = get_adapter("lms", cfg)
    web = get_adapter("website", cfg)

    assert isinstance(lms, LiveLMSAdapter)
    assert isinstance(web, LiveWebsiteAdapter)
    assert isinstance(lms, BaseIntegrationAdapter)
    assert isinstance(web, BaseIntegrationAdapter)
    assert lms.base_url == "https://live-lms.example.com"
    assert web.base_url == "https://live-website.example.com"


def test_factory_case_insensitivity_and_whitespace():
    cfg = Settings(lms_integration_mode="live", website_integration_mode="live")
    assert isinstance(get_adapter("  LMS  ", cfg), LiveLMSAdapter)
    assert isinstance(get_adapter("Website", cfg), LiveWebsiteAdapter)


def test_factory_invalid_source_raises_value_error():
    with pytest.raises(ValueError, match="Unknown integration source"):
        get_adapter("crm_invalid")


def test_factory_unsupported_mode_raises_not_implemented():
    cfg_lms = Settings(lms_integration_mode="unsupported_mode")
    with pytest.raises(NotImplementedError, match="Unsupported LMS integration mode"):
        get_adapter("lms", cfg_lms)

    cfg_web = Settings(website_integration_mode="unsupported_mode")
    with pytest.raises(NotImplementedError, match="Unsupported Website integration mode"):
        get_adapter("website", cfg_web)


# ==============================================================================
# 2. Timeout configuration
# ==============================================================================

def test_adapters_timeout_configuration():
    lms = LiveLMSAdapter(base_url="https://lms.test", timeout=15.0)
    web = LiveWebsiteAdapter(base_url="https://web.test", timeout=12.0)

    assert isinstance(lms.timeout, httpx.Timeout)
    assert lms.timeout.connect == 5.0
    assert lms.timeout.read == 30.0

    assert isinstance(web.timeout, httpx.Timeout)
    assert web.timeout.connect == 5.0
    assert web.timeout.read == 30.0


# ==============================================================================
# 3. LiveLMSAdapter Health Check
# ==============================================================================

def test_live_lms_health_check_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/health"
        assert request.method == "GET"
        return httpx.Response(200, json={"status": "UP", "version": "2.4.0"})

    transport = httpx.MockTransport(handler)
    adapter = LiveLMSAdapter(base_url="https://rtkb.zion-lms.ru", transport=transport)
    res = adapter.health_check()

    assert res["status"] == "ok"
    assert res["connected"] is True
    assert res["mode"] == "live"
    assert res["source"] == "lms"
    assert res["endpoint"] == "https://rtkb.zion-lms.ru"
    assert isinstance(res["latency_ms"], float)
    assert res["latency_ms"] >= 0.0


def test_live_lms_health_check_http_500():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(handler)
    adapter = LiveLMSAdapter(base_url="https://rtkb.zion-lms.ru", transport=transport)
    res = adapter.health_check()

    assert res["status"] == "error"
    assert res["connected"] is False
    assert res["mode"] == "live"
    assert res["source"] == "lms"
    assert "HTTP 500" in res["error"]


def test_live_lms_health_check_connect_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused by peer")

    transport = httpx.MockTransport(handler)
    adapter = LiveLMSAdapter(base_url="https://rtkb.zion-lms.ru", transport=transport)
    res = adapter.health_check()

    assert res["status"] == "error"
    assert res["connected"] is False
    assert "Connection refused" in res["error"]


def test_live_lms_health_check_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Read timed out after 30.0 seconds")

    transport = httpx.MockTransport(handler)
    adapter = LiveLMSAdapter(base_url="https://rtkb.zion-lms.ru", transport=transport)
    res = adapter.health_check()

    assert res["status"] == "error"
    assert res["connected"] is False
    assert "timed out" in res["error"].lower()


# ==============================================================================
# 4. LiveLMSAdapter Fetch Updates & Normalization
# ==============================================================================

def test_live_lms_fetch_updates_success_and_normalization():
    fixture_metrics = [
        {
            "organization_id": "org-1",
            "program_id": "program-devops",
            "metric_code": "active_cohorts",
            "value": 4.0,
            "unit": "cohort",
            "as_of": "2026-09-20T10:00:00Z",
        },
        {
            "org_id": "org-2",
            "prog_id": "program-qa",
            "prog_slug": "qa",
            "metric_code": "students_enrolled",
            "value": 35.0,
            "unit": "student",
            "as_of": "2026-09-20T11:00:00+00:00",
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/metrics"
        return httpx.Response(200, json={"items": fixture_metrics})

    transport = httpx.MockTransport(handler)
    adapter = LiveLMSAdapter(base_url="https://rtkb.zion-lms.ru", transport=transport)
    envelopes = adapter.fetch_updates()

    assert len(envelopes) == 2
    for env in envelopes:
        assert isinstance(env, NormalizedEnvelope)
        assert env.source == "lms"
        assert env.entity_type == "learning_metric"
        assert env.schema_version == "1.0"
        assert env.operation == "upsert"

    # Verify first envelope
    env0 = envelopes[0]
    assert env0.external_id == "zion-metric-org-1-devops-active_cohorts"
    assert env0.payload["organization_id"] == "org-1"
    assert env0.payload["program_id"] == "program-devops"
    assert env0.payload["metric_code"] == "active_cohorts"
    assert env0.payload["value"] == 4.0
    assert env0.payload["unit"] == "cohort"

    # Verify second envelope with alias keys
    env1 = envelopes[1]
    assert env1.external_id == "zion-metric-org-2-qa-students_enrolled"
    assert env1.payload["organization_id"] == "org-2"
    assert env1.payload["program_id"] == "program-qa"
    assert env1.payload["value"] == 35.0


def test_live_lms_fetch_updates_with_authorization_token():
    captured_auth = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_auth.append(request.headers.get("authorization"))
        return httpx.Response(200, json=[])

    # Case 1: Token provided
    t1 = httpx.MockTransport(handler)
    a1 = LiveLMSAdapter(base_url="https://rtkb.zion-lms.ru", api_token="secret-lms-token-123", transport=t1)
    a1.fetch_updates()
    assert captured_auth[-1] == "Bearer secret-lms-token-123"

    # Case 2: No token
    t2 = httpx.MockTransport(handler)
    a2 = LiveLMSAdapter(base_url="https://rtkb.zion-lms.ru", api_token=None, transport=t2)
    a2.fetch_updates()
    assert captured_auth[-1] is None


def test_live_lms_fetch_updates_since_filtering():
    recorded_params = []
    fixtures = [
        {"organization_id": "org-1", "program_id": "program-devops", "metric_code": "m1", "value": 1, "as_of": "2026-09-15T00:00:00Z"},
        {"organization_id": "org-1", "program_id": "program-devops", "metric_code": "m2", "value": 2, "as_of": "2026-09-22T00:00:00Z"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        recorded_params.append(str(request.url.query))
        return httpx.Response(200, json=fixtures)

    transport = httpx.MockTransport(handler)
    adapter = LiveLMSAdapter(base_url="https://rtkb.zion-lms.ru", transport=transport)

    cutoff = datetime(2026, 9, 20, 0, 0, 0, tzinfo=timezone.utc)
    envelopes = adapter.fetch_updates(since=cutoff)

    # Param passed to remote service
    assert "since=" in recorded_params[0]
    # Older record filtered out
    assert len(envelopes) == 1
    assert envelopes[0].payload["metric_code"] == "m2"


def test_live_lms_fetch_updates_graceful_degradation_on_network_errors():
    # 1. HTTP 503 Service Unavailable
    t503 = httpx.MockTransport(lambda req: httpx.Response(503, text="Service Unavailable"))
    a503 = LiveLMSAdapter(base_url="https://rtkb.zion-lms.ru", transport=t503)
    assert a503.fetch_updates() == []

    # 2. Connection error
    def raise_connect(req: httpx.Request):
        raise httpx.ConnectError("Failed to establish new connection")
    t_conn = httpx.MockTransport(raise_connect)
    a_conn = LiveLMSAdapter(base_url="https://rtkb.zion-lms.ru", transport=t_conn)
    assert a_conn.fetch_updates() == []

    # 3. Timeout error
    def raise_timeout(req: httpx.Request):
        raise httpx.ReadTimeout("Gateway read timeout")
    t_to = httpx.MockTransport(raise_timeout)
    a_to = LiveLMSAdapter(base_url="https://rtkb.zion-lms.ru", transport=t_to)
    assert a_to.fetch_updates() == []


# ==============================================================================
# 5. LiveWebsiteAdapter Health Check
# ==============================================================================

def test_live_website_health_check_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/health"
        return httpx.Response(200, json={"status": "ok", "app": "Laravel Portal"})

    transport = httpx.MockTransport(handler)
    adapter = LiveWebsiteAdapter(base_url="https://it-school.rt.ru", transport=transport)
    res = adapter.health_check()

    assert res["status"] == "ok"
    assert res["connected"] is True
    assert res["mode"] == "live"
    assert res["source"] == "website"
    assert res["endpoint"] == "https://it-school.rt.ru"
    assert isinstance(res["latency_ms"], float)
    assert res["latency_ms"] >= 0.0


def test_live_website_health_check_errors():
    # 500 error
    t500 = httpx.MockTransport(lambda req: httpx.Response(500, text="Laravel Fatal Error"))
    a500 = LiveWebsiteAdapter(base_url="https://it-school.rt.ru", transport=t500)
    res500 = a500.health_check()
    assert res500["status"] == "error"
    assert res500["connected"] is False
    assert "HTTP 500" in res500["error"]

    # Connect error
    def raise_conn(req: httpx.Request):
        raise httpx.ConnectError("Host unreachable")
    t_conn = httpx.MockTransport(raise_conn)
    a_conn = LiveWebsiteAdapter(base_url="https://it-school.rt.ru", transport=t_conn)
    res_conn = a_conn.health_check()
    assert res_conn["status"] == "error"
    assert res_conn["connected"] is False


# ==============================================================================
# 6. LiveWebsiteAdapter Fetch Updates & Normalization
# ==============================================================================

def test_live_website_fetch_updates_success_and_normalization():
    fixture_apps = [
        {
            "external_id": "laravel-app-901",
            "organization_name": "Томский государственный университет",
            "representative_name": "Петров Петр Петрович",
            "representative_email": "petrov@tsu.ru",
            "representative_phone": "+7 (3822) 52-98-52",
            "program_name": "Инженерия качества ПО",
            "program_id": "program-qa",
            "comments": "Заявка на партнерство от ТГУ",
            "created_at": "2026-09-21T12:00:00Z",
        }
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/applications"
        return httpx.Response(200, json={"applications": fixture_apps})

    transport = httpx.MockTransport(handler)
    adapter = LiveWebsiteAdapter(base_url="https://it-school.rt.ru", transport=transport)
    envelopes = adapter.fetch_updates()

    assert len(envelopes) == 1
    env = envelopes[0]
    assert env.source == "website"
    assert env.entity_type == "application"
    assert env.external_id == "laravel-app-901"
    assert env.payload["organization_name"] == "Томский государственный университет"
    assert env.payload["representative_name"] == "Петров Петр Петрович"
    assert env.payload["representative_email"] == "petrov@tsu.ru"
    assert env.payload["program_name"] == "Инженерия качества ПО"
    assert env.payload["program_id"] == "program-qa"
    assert env.payload["comments"] == "Заявка на партнерство от ТГУ"


def test_live_website_fetch_updates_auth_and_since():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        captured["query"] = str(request.url.query)
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    adapter = LiveWebsiteAdapter(
        base_url="https://it-school.rt.ru",
        api_token="portal-api-key-999",
        transport=transport,
    )
    dt = datetime(2026, 9, 21, 15, 30, tzinfo=timezone.utc)
    adapter.fetch_updates(since=dt)

    assert captured["auth"] == "Bearer portal-api-key-999"
    assert "since=2026-09-21" in captured["query"]


def test_live_website_graceful_degradation():
    t_err = httpx.MockTransport(lambda req: httpx.Response(502, text="Bad Gateway"))
    adapter = LiveWebsiteAdapter(base_url="https://it-school.rt.ru", transport=t_err)
    assert adapter.fetch_updates() == []


# ==============================================================================
# 7. End-to-End System Integration via FastAPI client
# ==============================================================================

def test_e2e_live_sync_lms_integration(client, app):
    """Verifies that switching config to live LMS ingests live metrics into database."""
    test_metrics = [
        {
            "organization_id": "org-1",
            "program_id": "program-devops",
            "metric_code": "live_cohorts",
            "value": 5.0,
            "unit": "cohort",
            "as_of": "2026-09-22T08:00:00Z",
        }
    ]

    mock_transport = httpx.MockTransport(lambda req: httpx.Response(200, json=test_metrics))
    live_adapter = LiveLMSAdapter(base_url="https://live-zion.test", transport=mock_transport)

    with patch("app.integrations.service.get_adapter") as mock_get_adapter:
        mock_get_adapter.side_effect = lambda src, cfg: live_adapter if src == "lms" else MockWebsiteAdapter()

        res = client.post("/api/v1/integrations/sync/lms", headers={"X-Demo-User": "supervisor"})
        assert res.status_code == 200
        data = res.json()
        assert data["source"] == "lms"
        assert data["received_count"] == 1
        assert data["processed_count"] == 1

        with app.state.session_factory() as session:
            metric = session.scalar(
                select(LearningMetric).where(LearningMetric.metric_code == "live_cohorts")
            )
            assert metric is not None
            assert metric.value == 5.0
            assert metric.organization_id == "org-1"


def test_e2e_live_sync_network_failure_graceful_degradation(client):
    """When remote live service is down, sync returns 200 with 0 received without 500 crash."""
    def fail_transport(req: httpx.Request):
        raise httpx.ConnectError("Network is unreachable")

    mock_transport = httpx.MockTransport(fail_transport)
    live_adapter = LiveLMSAdapter(base_url="https://unreachable.test", transport=mock_transport)

    with patch("app.integrations.service.get_adapter") as mock_get_adapter:
        mock_get_adapter.side_effect = lambda src, cfg: live_adapter if src == "lms" else MockWebsiteAdapter()

        res = client.post("/api/v1/integrations/sync/lms", headers={"X-Demo-User": "supervisor"})
        assert res.status_code == 200
        data = res.json()
        assert data["source"] == "lms"
        assert data["received_count"] == 0
        assert data["processed_count"] == 0


def test_e2e_live_adapter_status_endpoint(client):
    """Status endpoint correctly queries health_check on live adapters."""
    def lms_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"})

    def web_handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Site offline")

    live_lms = LiveLMSAdapter(base_url="https://lms.test", transport=httpx.MockTransport(lms_handler))
    live_web = LiveWebsiteAdapter(base_url="https://web.test", transport=httpx.MockTransport(web_handler))

    with patch("app.integrations.service.get_adapter") as mock_get_adapter:
        def fake_get_adapter(src, cfg):
            if src == "lms":
                return live_lms
            return live_web

        mock_get_adapter.side_effect = fake_get_adapter

        res = client.get("/api/v1/integrations/status", headers={"X-Demo-User": "supervisor"})
        assert res.status_code == 200
        status_data = res.json()

        lms_status = status_data["adapters_by_source"]["lms"]
        assert lms_status["status"] == "ok"
        assert lms_status["connected"] is True
        assert lms_status["mode"] == "live"

        web_status = status_data["adapters_by_source"]["website"]
        assert web_status["status"] == "error"
        assert web_status["connected"] is False
        assert web_status["mode"] == "live"


# ==============================================================================
# 8. Adversarial Edge Cases & Robustness
# ==============================================================================

def test_adapters_timeout_none_and_base_url_default():
    """Live adapters handle timeout=None and empty base_url without TypeError/ValueError."""
    lms = LiveLMSAdapter(base_url="", timeout=None)
    web = LiveWebsiteAdapter(base_url=None, timeout=None)

    assert lms.base_url == "https://rtkb.zion-lms.ru"
    assert web.base_url == "https://it-school.rt.ru"
    assert isinstance(lms.timeout, httpx.Timeout)
    assert lms.timeout.connect == 5.0
    assert lms.timeout.read == 30.0
    assert isinstance(web.timeout, httpx.Timeout)
    assert web.timeout.connect == 5.0
    assert web.timeout.read == 30.0


def test_adapters_follow_redirects():
    """HTTP 301/302 redirects are followed automatically rather than failing."""
    def lms_handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/v1/health":
            return httpx.Response(301, headers={"Location": "/api/v1/health/"})
        elif req.url.path == "/api/v1/health/":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404)

    adapter = LiveLMSAdapter(transport=httpx.MockTransport(lms_handler))
    res = adapter.health_check()
    assert res["status"] == "ok"
    assert res["connected"] is True


def test_health_check_detects_down_status_in_200_body():
    """Health check recognizes explicit DOWN or unhealthy payload status even with HTTP 200."""
    def down_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "DOWN", "error": "Database link lost"})

    lms = LiveLMSAdapter(transport=httpx.MockTransport(down_handler))
    web = LiveWebsiteAdapter(transport=httpx.MockTransport(down_handler))

    res_lms = lms.health_check()
    assert res_lms["status"] == "error"
    assert res_lms["connected"] is False
    assert "Database link lost" in res_lms["error"]

    res_web = web.health_check()
    assert res_web["status"] == "error"
    assert res_web["connected"] is False
    assert "Database link lost" in res_web["error"]


def test_live_lms_sanitizes_nan_inf_and_negative_metrics():
    """Non-finite floats (NaN, Inf) and negative counts are sanitized to 0.0."""
    raw_metrics = [
        {"organization_id": "org-1", "program_id": "program-devops", "metric_code": "active_cohorts", "value": "NaN"},
        {"organization_id": "org-1", "program_id": "program-devops", "metric_code": "students_enrolled", "value": "Infinity"},
        {"organization_id": "org-1", "program_id": "program-devops", "metric_code": "students_completed", "value": -10},
    ]
    t = httpx.MockTransport(lambda req: httpx.Response(200, json=raw_metrics))
    adapter = LiveLMSAdapter(transport=t)
    envelopes = adapter.fetch_updates()

    assert len(envelopes) == 3
    assert envelopes[0].payload["value"] == 0.0
    assert envelopes[1].payload["value"] == 0.0
    assert envelopes[2].payload["value"] == 0.0


def test_live_lms_timestamp_formats():
    """Supports unix numeric timestamps as well as ISO-8601 strings."""
    raw_metrics = [
        {"organization_id": "org-1", "program_id": "program-devops", "metric_code": "m1", "value": 1.0, "as_of": 1726830000},
        {"organization_id": "org-1", "program_id": "program-devops", "metric_code": "m2", "value": 2.0, "as_of": "2026-09-20T10:00:00Z"},
    ]
    t = httpx.MockTransport(lambda req: httpx.Response(200, json=raw_metrics))
    adapter = LiveLMSAdapter(transport=t)
    envelopes = adapter.fetch_updates()

    assert len(envelopes) == 2
    assert envelopes[0].effective_at.tzinfo is not None
    assert envelopes[1].effective_at.tzinfo is not None


def test_nested_items_and_collections_extraction():
    """Extracts records from standard Laravel / API envelopes like {'data': {'items': [...]}}."""
    lms_data = {"data": {"items": [{"org_id": "org-1", "prog_id": "devops", "metric_code": "m1", "value": 5.0}]}}
    web_data = {"data": [{"id": 401, "organization_name": "Тестовый ВУЗ"}]}

    lms = LiveLMSAdapter(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=lms_data)))
    web = LiveWebsiteAdapter(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=web_data)))

    lms_envs = lms.fetch_updates()
    assert len(lms_envs) == 1
    assert lms_envs[0].payload["program_id"] == "program-devops"

    web_envs = web.fetch_updates()
    assert len(web_envs) == 1
    assert web_envs[0].external_id == "web-app-401"
    assert web_envs[0].payload["organization_name"] == "Тестовый ВУЗ"


def test_external_id_and_revision_truncation_limits():
    """Safeguards DB length limits (128 for external_id, 64 for revision) against overly long upstream values."""
    huge_id = "A" * 250
    huge_rev = "R" * 100
    huge_metric = "M" * 100

    raw = [{"external_id": huge_id, "revision": huge_rev, "metric_code": huge_metric, "value": 1.0}]
    lms = LiveLMSAdapter(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=raw)))
    envs = lms.fetch_updates()

    assert len(envs) == 1
    assert len(envs[0].external_id) == 128
    assert len(envs[0].source_revision) == 64
    assert len(envs[0].payload["metric_code"]) == 64


def test_live_website_nested_contact_and_program_prefixing():
    """Handles nested contact dictionary and normalizes program_id prefix."""
    raw_app = {
        "id": "app-777",
        "program_id": "qa",
        "contact": {
            "name": "Анна Сидорова",
            "position": "Декан",
            "email": "anna@test.ru",
            "phone": "+79991234567",
        },
    }
    web = LiveWebsiteAdapter(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[raw_app])))
    envs = web.fetch_updates()

    assert len(envs) == 1
    assert envs[0].payload["program_id"] == "program-qa"
    assert envs[0].payload["representative_name"] == "Анна Сидорова"
    assert envs[0].payload["representative_email"] == "anna@test.ru"


def test_settings_token_propagation_to_factory():
    """Settings dataclass supports lms_api_token / website_api_token and factory injects them."""
    cfg = Settings(
        lms_integration_mode="live",
        website_integration_mode="live",
        lms_api_token="cfg-lms-token",
        website_api_token="cfg-web-token",
    )
    lms = get_adapter("lms", cfg)
    web = get_adapter("website", cfg)

    assert isinstance(lms, LiveLMSAdapter)
    assert isinstance(web, LiveWebsiteAdapter)
    assert lms.api_token == "cfg-lms-token"
    assert web.api_token == "cfg-web-token"


def test_http_429_too_many_requests_graceful_handling():
    """429 Too Many Requests response is handled gracefully without crashing."""
    t = httpx.MockTransport(lambda r: httpx.Response(429, headers={"Retry-After": "60"}, text="Rate limited"))
    lms = LiveLMSAdapter(transport=t)
    web = LiveWebsiteAdapter(transport=t)

    assert lms.fetch_updates() == []
    assert web.fetch_updates() == []

    lms_health = lms.health_check()
    assert lms_health["status"] == "error"
    assert lms_health["connected"] is False
    assert "429" in lms_health["error"]


def test_bearer_prefix_stripping_prevents_duplicate_header():
    """Token with 'Bearer ' prefix does not result in 'Bearer Bearer <token>' header."""
    captured = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.headers.get("authorization"))
        return httpx.Response(200, json=[])

    t = httpx.MockTransport(handler)
    lms = LiveLMSAdapter(api_token="Bearer my-secret-lms-token", transport=t)
    web = LiveWebsiteAdapter(api_token="bearer my-secret-web-token", transport=t)

    lms.fetch_updates()
    assert captured[-1] == "Bearer my-secret-lms-token"

    web.fetch_updates()
    assert captured[-1] == "Bearer my-secret-web-token"


def test_health_check_detects_boolean_unhealthy_flags():
    """Health check fails when body contains healthy: False, ok: False, or success: False."""
    payloads = [
        {"healthy": False, "message": "Disk array degraded"},
        {"ok": False, "error": "Redis broker unreachable"},
        {"success": False, "reason": "Cluster split-brain"},
    ]

    for p in payloads:
        t = httpx.MockTransport(lambda r, p=p: httpx.Response(200, json=p))
        lms = LiveLMSAdapter(transport=t)
        web = LiveWebsiteAdapter(transport=t)

        res_lms = lms.health_check()
        assert res_lms["status"] == "error"
        assert res_lms["connected"] is False

        res_web = web.health_check()
        assert res_web["status"] == "error"
        assert res_web["connected"] is False


def test_health_check_detects_html_content_type():
    """Health check detects HTML content-type as remote error rather than healthy service."""
    t = httpx.MockTransport(
        lambda r: httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text="<html><body>502 Bad Gateway</body></html>",
        )
    )
    lms = LiveLMSAdapter(transport=t)
    web = LiveWebsiteAdapter(transport=t)

    res_lms = lms.health_check()
    assert res_lms["status"] == "error"
    assert res_lms["connected"] is False
    assert "HTML" in res_lms["error"]

    res_web = web.health_check()
    assert res_web["status"] == "error"
    assert res_web["connected"] is False
    assert "HTML" in res_web["error"]


def test_invalid_and_negative_timeout_fallbacks():
    """Invalid timeout strings or negative/nan values safely fall back to 10s default."""
    for bad_to in ["invalid_to", -5.0, float("nan"), 0.0]:
        lms = LiveLMSAdapter(timeout=bad_to)
        web = LiveWebsiteAdapter(timeout=bad_to)
        assert lms.timeout.connect == 5.0
        assert lms.timeout.read == 30.0
        assert web.timeout.connect == 5.0
        assert web.timeout.read == 30.0


def test_lms_derives_deterministic_external_id_from_id():
    """LMS adapter derives deterministic external_id from 'id' to enable inbox deduplication."""
    raw = [{"id": "item-999", "metric_code": "active_cohorts", "value": 3.0}]
    t = httpx.MockTransport(lambda r: httpx.Response(200, json=raw))
    adapter = LiveLMSAdapter(transport=t)

    envs1 = adapter.fetch_updates()
    envs2 = adapter.fetch_updates()

    assert envs1[0].external_id == "zion-metric-item-999"
    assert envs2[0].external_id == "zion-metric-item-999"


def test_nested_payload_sanitization_overrides_dirty_values():
    """Sanitizes value, metric_code, and unit even when supplied within a nested payload dict."""
    dirty_metric = {
        "id": "item-101",
        "payload": {
            "metric_code": "ACTIVE-COHORTS",
            "value": "NaN",
            "unit": "cohort" * 20,
        },
    }
    t = httpx.MockTransport(lambda r: httpx.Response(200, json=[dirty_metric]))
    adapter = LiveLMSAdapter(transport=t)
    envs = adapter.fetch_updates()

    assert len(envs) == 1
    env = envs[0]
    assert env.payload["value"] == 0.0
    assert env.payload["metric_code"] == "active_cohorts"
    assert len(env.payload["unit"]) <= 32


def test_nested_payload_website_normalizes_program_and_contacts():
    """Normalizes program_id prefix and contact fields present in nested website payload."""
    dirty_app = {
        "id": "app-888",
        "payload": {
            "program_id": "devops",
            "organization_name": "Тестовый Университет",
            "contact": {
                "name": "Иван Реп",
                "email": "ivan@rep.ru",
                "phone": "+79998887766",
            },
        },
    }
    t = httpx.MockTransport(lambda r: httpx.Response(200, json=[dirty_app]))
    adapter = LiveWebsiteAdapter(transport=t)
    envs = adapter.fetch_updates()

    assert len(envs) == 1
    env = envs[0]
    assert env.payload["program_id"] == "program-devops"
    assert env.payload["representative_name"] == "Иван Реп"
    assert env.payload["representative_email"] == "ivan@rep.ru"


def test_single_dictionary_response_handling():
    """Accepts single dictionary object without wrapping list."""
    lms_single = {"id": "single-1", "metric_code": "students_enrolled", "value": 12.0}
    web_single = {"id": "single-web-1", "organization_name": "ВУЗ 1", "representative_email": "a@b.ru"}

    lms = LiveLMSAdapter(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=lms_single)))
    web = LiveWebsiteAdapter(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=web_single)))

    lms_envs = lms.fetch_updates()
    web_envs = web.fetch_updates()

    assert len(lms_envs) == 1
    assert lms_envs[0].external_id == "zion-metric-single-1"
    assert len(web_envs) == 1
    assert web_envs[0].external_id == "web-app-single-web-1"


def test_boolean_timestamp_does_not_become_1970_epoch():
    """Boolean True/False in as_of or created_at does not parse to 1970-01-01."""
    raw = [{"id": "m1", "metric_code": "active_cohorts", "value": 1.0, "as_of": True}]
    t = httpx.MockTransport(lambda r: httpx.Response(200, json=raw))
    adapter = LiveLMSAdapter(transport=t)
    envs = adapter.fetch_updates()

    assert envs[0].effective_at.year >= 2026


def test_health_check_detects_malformed_json_and_plain_text():
    """Health check detects broken JSON or plain text errors despite HTTP 200."""
    t_broken = httpx.MockTransport(lambda r: httpx.Response(200, text="{broken-json", headers={"content-type": "application/json"}))
    lms_broken = LiveLMSAdapter(transport=t_broken)
    web_broken = LiveWebsiteAdapter(transport=t_broken)

    res_lms = lms_broken.health_check()
    assert res_lms["status"] == "error"
    assert res_lms["connected"] is False
    assert "Invalid JSON response" in res_lms["error"]

    res_web = web_broken.health_check()
    assert res_web["status"] == "error"
    assert res_web["connected"] is False
    assert "Invalid JSON response" in res_web["error"]

    t_text = httpx.MockTransport(lambda r: httpx.Response(200, text="Stack trace: internal failure", headers={"content-type": "text/plain"}))
    lms_text = LiveLMSAdapter(transport=t_text)
    assert lms_text.health_check()["status"] == "error"


def test_health_check_detects_unhealthy_statuses_and_error_keys():
    """Health check catches FAILED, critical, false boolean status, and error keys without status."""
    error_payloads = [
        {"status": "FAILED"},
        {"status": "critical"},
        {"status": False},
        {"error": "Redis cluster unreachable"},
    ]

    for p in error_payloads:
        t = httpx.MockTransport(lambda r, p=p: httpx.Response(200, json=p))
        lms = LiveLMSAdapter(transport=t)
        web = LiveWebsiteAdapter(transport=t)

        assert lms.health_check()["status"] == "error"
        assert web.health_check()["status"] == "error"


def test_health_check_detects_non_dict_json():
    """Health check detects non-dict JSON responses (e.g. array) as errors."""
    t = httpx.MockTransport(lambda r: httpx.Response(200, json=["unexpected", "array"]))
    lms = LiveLMSAdapter(transport=t)
    assert lms.health_check()["status"] == "error"
    assert "Expected JSON object" in lms.health_check()["error"]


def test_factory_handles_case_and_whitespace_in_mode():
    """Factory handles '  LIVE  ' and 'Live' mode strings without failing."""
    cfg = Settings(lms_integration_mode="  LIVE  ", website_integration_mode=" Live ")
    lms = get_adapter("lms", cfg)
    web = get_adapter("website", cfg)

    assert isinstance(lms, LiveLMSAdapter)
    assert isinstance(web, LiveWebsiteAdapter)


def test_adapter_url_without_scheme_auto_prepends_https():
    """Base URLs provided without scheme (e.g. 'rtkb.zion-lms.ru') automatically get https:// prefix."""
    lms = LiveLMSAdapter(base_url="rtkb.zion-lms.ru")
    web = LiveWebsiteAdapter(base_url="it-school.rt.ru/")

    assert lms.base_url == "https://rtkb.zion-lms.ru"
    assert web.base_url == "https://it-school.rt.ru"


def test_adapter_token_quotes_and_non_string():
    """Tokens enclosed in quotes are cleanly unquoted, and integer tokens do not crash."""
    lms = LiveLMSAdapter(api_token='"secret-token-in-quotes"')
    assert lms.api_token == "secret-token-in-quotes"

    web = LiveWebsiteAdapter(api_token=12345)
    assert web.api_token == "12345"


def test_attendance_rate_clamping():
    """Attendance rate is clamped between 0.0% and 100.0%."""
    raw = [
        {"id": "m1", "metric_code": "attendance_rate", "value": -15.0},
        {"id": "m2", "metric_code": "attendance_rate", "value": 150.0},
    ]
    t = httpx.MockTransport(lambda r: httpx.Response(200, json=raw))
    adapter = LiveLMSAdapter(transport=t)
    envs = adapter.fetch_updates()

    assert envs[0].payload["value"] == 0.0
    assert envs[1].payload["value"] == 100.0


def test_website_derives_deterministic_external_id_from_application_id_and_number():
    """Derives deterministic external_id from application_id or number."""
    apps = [
        {"application_id": 505, "organization_name": "ВУЗ 1"},
        {"number": "APP-999", "organization_name": "ВУЗ 2"},
    ]
    t = httpx.MockTransport(lambda r: httpx.Response(200, json=apps))
    adapter = LiveWebsiteAdapter(transport=t)
    envs = adapter.fetch_updates()

    assert envs[0].external_id == "web-app-505"
    assert envs[1].external_id == "web-app-APP-999"


def test_website_nested_full_name_and_phone_number():
    """Extracts contact full_name and phone_number from nested contact dict."""
    app = {
        "id": "1",
        "contact": {
            "full_name": "Николай Сергеев",
            "phone_number": "+7 (999) 000-11-22",
            "email": "nikolay@test.ru",
        },
    }
    t = httpx.MockTransport(lambda r: httpx.Response(200, json=[app]))
    adapter = LiveWebsiteAdapter(transport=t)
    envs = adapter.fetch_updates()

    assert envs[0].payload["representative_name"] == "Николай Сергеев"
    assert envs[0].payload["representative_phone"] == "+7 (999) 000-11-22"


def test_fetch_updates_accepts_iso_string_since():
    """fetch_updates safely accepts ISO-8601 string for since parameter."""
    recorded = []
    t = httpx.MockTransport(lambda r: recorded.append(str(r.url.query)) or httpx.Response(200, json=[]))
    lms = LiveLMSAdapter(transport=t)
    lms.fetch_updates(since="2026-09-20T12:00:00Z")

    assert len(recorded) == 1
    assert "since=2026-09-20" in recorded[0]



