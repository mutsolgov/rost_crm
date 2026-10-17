"""LMS Mock Service for RTK IT School (Zion / Moodle).

Provides mock HTTP endpoints adhering to LiveLMSAdapter specification:
- GET  /api/v1/health            -> System health check and counts
- GET  /api/v1/metrics?since=... -> Training metrics with optional ISO timestamp filter
- GET  /api/v1/learners          -> Seed directory of enrolled learners
- POST /api/v1/simulate/webhook  -> Emits webhook to CRM with X-Webhook-Secret authentication

Standard library only: 0 external dependencies.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import signal
import sys
import threading
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [mock-lms] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("mock-lms")

SEED_DATA_PATH = Path(
    os.environ.get(
        "SEED_DATA_PATH",
        Path(__file__).resolve().parent / "seed_data.json",
    )
)


def load_seed_data(path: Path) -> dict[str, Any]:
    """Loads seed data from json file, falling back to empty datasets if missing."""
    if not path.exists():
        logger.warning("Seed data file not found at %s. Initializing empty seed.", path)
        return {
            "service": "rtk-lms-zion",
            "version": "1.4.0",
            "learners": [],
            "metrics": [],
            "cohorts": [],
            "webhook_simulation_templates": [],
        }
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.info(
                "Loaded seed data from %s (%d learners, %d metrics, %d cohorts)",
                path,
                len(data.get("learners", [])),
                len(data.get("metrics", [])),
                len(data.get("cohorts", [])),
            )
            return data
    except Exception as exc:
        logger.error("Failed to parse seed data from %s: %s", path, exc)
        return {
            "service": "rtk-lms-zion",
            "version": "1.4.0",
            "learners": [],
            "metrics": [],
            "cohorts": [],
            "webhook_simulation_templates": [],
        }


SEED_DATA = load_seed_data(SEED_DATA_PATH)


def parse_iso_datetime(value: str | None) -> datetime | None:
    """Parses ISO timestamp string into UTC-aware datetime."""
    if not value:
        return None
    val = value.strip()
    if not val:
        return None
    try:
        val_norm = val[:-1] + "+00:00" if val.endswith("Z") else val
        dt = datetime.fromisoformat(val_norm)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    try:
        return datetime.strptime(val, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        pass

    return None


def get_default_webhook_payload() -> dict[str, Any]:
    """Builds a default webhook payload for learner/metric simulation."""
    learners = SEED_DATA.get("learners", [])
    if learners:
        first_learner = learners[0]
        return {
            "schema_version": "1.0",
            "source": "lms",
            "entity_type": "learner",
            "external_id": first_learner.get("id", "lrn-001"),
            "source_revision": "1",
            "operation": "upsert",
            "effective_at": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "learner_id": first_learner.get("id", "lrn-001"),
                "full_name": first_learner.get("full_name", "Черепанова Светлана Васильевна"),
                "email": first_learner.get("email", "cherepanona.s@test.ru"),
                "phone": first_learner.get("phone", "79990234365"),
                "course": first_learner.get("course", "Анализ данных без программирования"),
                "program_id": first_learner.get("program_id", "program-data-analysis"),
                "cohort_id": first_learner.get("cohort_id", 1),
                "progress": first_learner.get("progress", 85.0),
                "status": first_learner.get("status", "active"),
            },
        }

    templates = SEED_DATA.get("webhook_simulation_templates", [])
    if templates:
        return templates[0]

    return {
        "schema_version": "1.0",
        "source": "lms",
        "entity_type": "learning_metric",
        "external_id": "zion-metric-org-1-devops-active_cohorts",
        "source_revision": "1",
        "operation": "upsert",
        "effective_at": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "organization_id": "org-1",
            "program_id": "program-devops",
            "metric_code": "active_cohorts",
            "value": 1.0,
            "unit": "cohort",
        },
    }


class LMSMockHandler(BaseHTTPRequestHandler):
    """HTTP request handler for LMS mock server."""

    server_version = "RTK-LMS-Zion-Mock/1.4.0"

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("%s - - [%s] %s", self.address_string(), self.log_date_time_string(), format % args)

    def send_json(self, status_code: int, data: Any) -> None:
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Webhook-Secret")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Webhook-Secret")
        self.end_headers()

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path.rstrip("/")
        query_params = urllib.parse.parse_qs(parsed_url.query)

        # Health endpoint: /api/v1/health (and aliases)
        if path in {"/api/v1/health", "/api/health", "/health"}:
            self.handle_health()
            return

        # Metrics endpoint: /api/v1/metrics
        if path in {"/api/v1/metrics", "/api/metrics"}:
            self.handle_metrics(query_params)
            return

        # Learners endpoint: /api/v1/learners
        if path in {"/api/v1/learners", "/api/learners"}:
            self.handle_learners(query_params)
            return

        # Root service metadata
        if path in {"", "/"}:
            self.send_json(200, {
                "service": "rtk-lms-zion",
                "version": "1.4.0",
                "status": "ok",
                "endpoints": [
                    "GET /api/v1/health",
                    "GET /api/v1/metrics?since=...",
                    "GET /api/v1/learners",
                    "POST /api/v1/simulate/webhook",
                ],
            })
            return

        self.send_json(404, {
            "status": "error",
            "error": f"Endpoint '{path}' not found on LMS mock service",
        })

    def do_POST(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path.rstrip("/")

        if path in {"/api/v1/simulate/webhook", "/simulate/webhook", "/api/simulate/webhook"}:
            self.handle_simulate_webhook()
            return

        self.send_json(404, {
            "status": "error",
            "error": f"Endpoint '{path}' not found for POST method",
        })

    def handle_health(self) -> None:
        learners = SEED_DATA.get("learners", [])
        cohorts = SEED_DATA.get("cohorts", [])
        timestamp_str = datetime.now(timezone.utc).isoformat()

        response = {
            "status": "ok",
            "healthy": True,
            "service": "rtk-lms-zion",
            "version": "1.4.0",
            "timestamp": timestamp_str,
            "learners_count": len(learners),
            "cohorts_count": len(cohorts),
        }
        self.send_json(200, response)

    def handle_metrics(self, query_params: dict[str, list[str]]) -> None:
        all_metrics = SEED_DATA.get("metrics", [])
        since_param = query_params.get("since", [None])[0]

        if since_param:
            since_dt = parse_iso_datetime(since_param)
            if since_dt is not None:
                filtered_metrics = []
                for item in all_metrics:
                    item_dt = parse_iso_datetime(item.get("as_of"))
                    if item_dt is not None:
                        if item_dt >= since_dt:
                            filtered_metrics.append(item)
                    else:
                        if str(item.get("as_of", "")) >= since_param:
                            filtered_metrics.append(item)
            else:
                filtered_metrics = [
                    item for item in all_metrics if str(item.get("as_of", "")) >= since_param
                ]
        else:
            filtered_metrics = list(all_metrics)

        self.send_json(200, {
            "status": "ok",
            "items": filtered_metrics,
        })

    def handle_learners(self, query_params: dict[str, list[str]]) -> None:
        learners = SEED_DATA.get("learners", [])
        cohort_filter = query_params.get("cohort", query_params.get("cohort_id", [None]))[0]

        if cohort_filter:
            try:
                cohort_num = int(cohort_filter)
                filtered = [l for l in learners if l.get("cohort") == cohort_num or l.get("cohort_id") == cohort_num]
            except ValueError:
                filtered = [l for l in learners if str(l.get("cohort")) == cohort_filter]
        else:
            filtered = list(learners)

        self.send_json(200, {
            "status": "ok",
            "items": filtered,
        })

    def handle_simulate_webhook(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        payload_data = None

        if content_length > 0:
            raw_body = self.rfile.read(content_length)
            if raw_body.strip():
                try:
                    payload_data = json.loads(raw_body.decode("utf-8"))
                except Exception as exc:
                    self.send_json(400, {
                        "status": "error",
                        "error": f"Invalid JSON payload: {exc}",
                    })
                    return

        if not payload_data or (isinstance(payload_data, dict) and not payload_data):
            payload_data = get_default_webhook_payload()

        crm_api_url = os.environ.get("CRM_API_URL", "http://localhost:8000").rstrip("/")
        webhook_target = f"{crm_api_url}/api/v1/webhooks/lms"
        secret = os.environ.get("LMS_WEBHOOK_SECRET", "rtk-lms-webhook-secret")

        body_bytes = json.dumps(payload_data, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            webhook_target,
            data=body_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Secret": secret,
                "User-Agent": "RTK-LMS-Zion-Mock/1.4.0",
            },
            method="POST",
        )

        delivered = False
        details: dict[str, Any] = {
            "target": webhook_target,
            "entity": payload_data.get("entity_type") if isinstance(payload_data, dict) else "unknown",
        }

        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                status_code = response.getcode()
                resp_text = response.read().decode("utf-8")
                try:
                    resp_json = json.loads(resp_text)
                except Exception:
                    resp_json = resp_text

                delivered = 200 <= status_code < 300
                details["status_code"] = status_code
                details["crm_response"] = resp_json
        except urllib.error.HTTPError as http_err:
            resp_text = http_err.read().decode("utf-8")
            try:
                resp_json = json.loads(resp_text)
            except Exception:
                resp_json = resp_text
            delivered = False
            details["status_code"] = http_err.code
            details["error"] = f"HTTP {http_err.code}: {http_err.reason}"
            details["crm_response"] = resp_json
        except Exception as net_err:
            delivered = False
            details["status_code"] = None
            details["error"] = str(net_err)

        self.send_json(200, {
            "status": "ok",
            "delivered": delivered,
            "details": details,
        })


def main() -> None:
    parser = argparse.ArgumentParser(description="LMS Mock Service (RTK IT School / Zion)")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8081")),
        help="Port to listen on (default: 8081)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=os.environ.get("HOST", "0.0.0.0"),
        help="Host address to bind to (default: 0.0.0.0)",
    )
    args = parser.parse_args()

    server_address = (args.host, args.port)
    server = ThreadingHTTPServer(server_address, LMSMockHandler)
    logger.info("Starting LMS mock service on http://%s:%d ...", args.host, args.port)

    def shutdown_signal_handler(signum: int, frame: Any) -> None:
        logger.info("Received termination signal (%d). Shutting down server...", signum)
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, shutdown_signal_handler)
    signal.signal(signal.SIGTERM, shutdown_signal_handler)

    try:
        server.serve_forever()
    except Exception as exc:
        logger.info("Server terminated: %s", exc)
    finally:
        server.server_close()
        logger.info("LMS mock service stopped cleanly.")


if __name__ == "__main__":
    main()
