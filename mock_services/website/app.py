#!/usr/bin/env python3
"""Website Mock Service for RTK IT School Educational Portal.

This standalone microservice emulates the external Website service (RTK IT School Portal)
on port 8082 using only Python standard library modules (0 external dependencies).

Endpoints:
- GET  /api/health                     - Health check returning service status and application count (Strictly /api/health)
- GET  /api/v1/health                  - Alias for health check
- GET  /api/v1/applications?since=...  - List paid applications, optionally filtered by created_at >= since
- POST /api/v1/simulate/application    - Ingest simulated application & emit webhook to CRM
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [mock-website] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("mock_website")

# Environment configuration
PORT = int(os.environ.get("PORT", "8082"))
HOST = os.environ.get("HOST", "0.0.0.0")
CRM_API_URL = os.environ.get("CRM_API_URL", "http://localhost:8000").rstrip("/")
WEBSITE_WEBHOOK_SECRET = os.environ.get("WEBSITE_WEBHOOK_SECRET", "rtk-website-webhook-secret")
SERVICE_NAME = "rtk-it-school-portal"
SERVICE_VERSION = "2.1.0"

# In-memory store and concurrency lock
STORE_LOCK = threading.Lock()
APPLICATIONS: list[dict[str, Any]] = []


def parse_iso_datetime(val: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp string into a timezone-aware UTC datetime."""
    if not val or not isinstance(val, str):
        return None
    val = val.strip()
    if not val:
        return None
    if val.endswith("Z") or val.endswith("z"):
        val = val[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass
    try:
        dt = datetime.strptime(val, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        pass
    return None


def load_seed_data() -> list[dict[str, Any]]:
    """Load initial applications from seed_data.json."""
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_data.json"),
        os.path.abspath("seed_data.json"),
        os.path.abspath("mock_services/website/seed_data.json"),
    ]
    for seed_path in candidates:
        if os.path.exists(seed_path):
            try:
                with open(seed_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    apps = data.get("applications", [])
                    if isinstance(apps, list) and apps:
                        logger.info("Loaded %d applications from %s", len(apps), seed_path)
                        return list(apps)
            except Exception as exc:
                logger.warning("Error reading seed file %s: %s", seed_path, exc)
    logger.warning("No seed_data.json found in candidate paths. Initializing with empty list.")
    return []


def init_store() -> None:
    """Initialize in-memory application store."""
    global APPLICATIONS
    with STORE_LOCK:
        APPLICATIONS = load_seed_data()


class WebsiteMockHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for Website Mock Service."""

    server_version = f"RTK-Website-Mock/{SERVICE_VERSION}"

    def log_message(self, format: str, *args: Any) -> None:
        """Forward access logs to Python logging."""
        logger.info("%s - %s", self.address_string(), format % args)

    def _send_json(self, status_code: int, data: Any) -> None:
        """Helper to serialize and transmit JSON responses."""
        payload_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Webhook-Secret")
        self.end_headers()
        self.wfile.write(payload_bytes)

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Webhook-Secret")
        self.end_headers()

    def do_GET(self) -> None:
        """Handle GET requests."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")
        if not path:
            path = "/"

        # 1. Health check endpoints: strictly /api/health (and /api/v1/health alias)
        if path in ("/api/health", "/api/v1/health", "/health"):
            with STORE_LOCK:
                total_apps = len(APPLICATIONS)
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            self._send_json(200, {
                "status": "ok",
                "healthy": True,
                "service": SERVICE_NAME,
                "version": SERVICE_VERSION,
                "timestamp": now_iso,
                "total_applications": total_apps,
            })
            return

        # 2. Inbound applications endpoint: /api/v1/applications
        if path == "/api/v1/applications":
            query_params = urllib.parse.parse_qs(parsed.query)
            since_raw = query_params.get("since", [None])[0]
            since_dt = parse_iso_datetime(since_raw)

            with STORE_LOCK:
                apps_snapshot = [dict(a) for a in APPLICATIONS]

            if since_dt is not None:
                filtered: list[dict[str, Any]] = []
                for app in apps_snapshot:
                    created_raw = app.get("created_at") or app.get("effective_at") or app.get("as_of")
                    app_dt = parse_iso_datetime(created_raw)
                    if app_dt is not None and app_dt >= since_dt:
                        filtered.append(app)
                items = filtered
            else:
                items = apps_snapshot

            self._send_json(200, {
                "status": "ok",
                "items": items,
            })
            return

        # 3. Root info endpoint
        if path == "/":
            with STORE_LOCK:
                total_apps = len(APPLICATIONS)
            self._send_json(200, {
                "service": SERVICE_NAME,
                "version": SERVICE_VERSION,
                "status": "ok",
                "total_applications": total_apps,
                "endpoints": [
                    "GET  /api/health",
                    "GET  /api/v1/applications?since=...",
                    "POST /api/v1/simulate/application",
                ],
            })
            return

        # 4. Unknown endpoint 404
        self._send_json(404, {
            "status": "error",
            "error": "Not Found",
            "path": parsed.path,
        })

    def do_POST(self) -> None:
        """Handle POST requests."""
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/api/v1/simulate/application":
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length) if content_length > 0 else b""

            incoming: dict[str, Any] = {}
            if raw_body.strip():
                try:
                    parsed_json = json.loads(raw_body.decode("utf-8"))
                    if isinstance(parsed_json, dict):
                        if "application" in parsed_json and isinstance(parsed_json["application"], dict):
                            incoming = parsed_json["application"]
                        elif "payload" in parsed_json and isinstance(parsed_json["payload"], dict):
                            incoming = parsed_json["payload"]
                        else:
                            incoming = parsed_json
                except Exception as exc:
                    self._send_json(400, {
                        "status": "error",
                        "error": f"Invalid JSON body: {exc}",
                    })
                    return

            # Construct application record
            now_utc = datetime.now(timezone.utc)
            now_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            date_code = now_utc.strftime("%Y%m%d%H%M%S")
            token = secrets.token_hex(3).upper()
            default_ord = f"ORD-{date_code}-{token}"

            order_id = str(
                incoming.get("id")
                or incoming.get("external_id")
                or incoming.get("order_number")
                or default_ord
            ).strip()

            rep_name = str(
                incoming.get("representative_name")
                or incoming.get("contact_name")
                or incoming.get("full_name")
                or incoming.get("name")
                or "Новый Заявитель"
            ).strip()

            rep_email = str(
                incoming.get("representative_email")
                or incoming.get("contact_email")
                or incoming.get("email")
                or "applicant@example.com"
            ).strip()

            rep_phone = str(
                incoming.get("representative_phone")
                or incoming.get("contact_phone")
                or incoming.get("phone")
                or "+7 (999) 777-88-99"
            ).strip()

            rep_pos = str(
                incoming.get("representative_position")
                or incoming.get("position")
                or incoming.get("role")
                or "Куратор направления"
            ).strip()

            org_name = str(
                incoming.get("organization_name")
                or incoming.get("university_name")
                or incoming.get("university")
                or incoming.get("organization")
                or incoming.get("company")
                or "ПАО «Ростелеком»"
            ).strip()

            prog_name = str(
                incoming.get("program_name")
                or "DevOps и облачные технологии"
            ).strip()

            prog_id = str(
                incoming.get("program_id")
                or "program-devops"
            ).strip()

            comments = str(
                incoming.get("comments")
                or incoming.get("comment")
                or "Симуляция заявки через образовательный портал."
            ).strip()

            created_at = str(
                incoming.get("created_at")
                or incoming.get("effective_at")
                or now_iso
            ).strip()

            cohort = incoming.get("cohort", 1)
            cohort_id = incoming.get("cohort_id", cohort)
            amount = float(incoming.get("amount", 50000.0))
            status = str(incoming.get("status", "paid")).strip()
            payment_status = str(incoming.get("payment_status", "paid")).strip()
            source_revision = str(incoming.get("source_revision", "1")).strip()

            app_record: dict[str, Any] = {
                "id": order_id,
                "external_id": order_id,
                "order_number": order_id,
                "created_at": created_at,
                "organization_name": org_name,
                "contact_name": rep_name,
                "representative_name": rep_name,
                "contact_email": rep_email,
                "representative_email": rep_email,
                "contact_phone": rep_phone,
                "representative_phone": rep_phone,
                "representative_position": rep_pos,
                "program_name": prog_name,
                "program_id": prog_id,
                "cohort": cohort,
                "cohort_id": cohort_id,
                "amount": amount,
                "payment_status": payment_status,
                "status": status,
                "comments": comments,
                "source_revision": source_revision,
            }

            # Add to in-memory list so subsequent GET /api/v1/applications includes it
            with STORE_LOCK:
                APPLICATIONS.append(app_record)
            logger.info("New application stored: %s (%s, %s)", order_id, org_name, rep_name)

            # Webhook payload with envelope metadata
            webhook_payload: dict[str, Any] = {
                "schema_version": "1.0",
                "source": "website",
                "entity_type": "application",
                "external_id": order_id,
                "source_revision": source_revision,
                "operation": "upsert",
                "effective_at": created_at,
                "organization_name": org_name,
                "representative_name": rep_name,
                "representative_email": rep_email,
                "representative_phone": rep_phone,
                "representative_position": rep_pos,
                "program_name": prog_name,
                "program_id": prog_id,
                "comments": comments,
                "payload": app_record,
            }

            # Attempt webhook delivery to CRM
            delivered = False
            webhook_target = f"{CRM_API_URL}/api/v1/webhooks/website"
            try:
                data_bytes = json.dumps(webhook_payload, ensure_ascii=False).encode("utf-8")
                req = urllib.request.Request(
                    webhook_target,
                    data=data_bytes,
                    headers={
                        "Content-Type": "application/json",
                        "X-Webhook-Secret": WEBSITE_WEBHOOK_SECRET,
                        "User-Agent": f"RTK-Website-Mock/{SERVICE_VERSION}",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    if 200 <= resp.status < 300:
                        delivered = True
                        logger.info("Webhook successfully delivered to %s (HTTP %s)", webhook_target, resp.status)
                    else:
                        logger.warning("CRM returned non-2xx status for webhook: %s", resp.status)
            except urllib.error.HTTPError as http_err:
                delivered = False
                logger.warning("CRM webhook rejected with HTTP %s: %s", http_err.code, http_err.reason)
            except Exception as conn_err:
                delivered = False
                logger.info("CRM offline or unreachable at %s (%s). Webhook delivery skipped gracefully.", webhook_target, conn_err)

            # Return HTTP 200 response
            self._send_json(200, {
                "status": "ok",
                "delivered": delivered,
                "application": app_record,
            })
            return

        # Unknown POST endpoint
        self._send_json(404, {
            "status": "error",
            "error": "Not Found",
            "path": parsed.path,
        })


def run_server(host: str = HOST, port: int = PORT) -> None:
    """Run the Website Mock Server."""
    init_store()
    server_class = ThreadingHTTPServer if hasattr(sys.modules["http.server"], "ThreadingHTTPServer") else HTTPServer
    server = server_class((host, port), WebsiteMockHandler)
    logger.info("Starting Website Mock Service on %s:%d (PID %d)...", host, port, os.getpid())
    logger.info("CRM Webhook URL: %s/api/v1/webhooks/website", CRM_API_URL)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down Website Mock Service...")
    finally:
        server.server_close()
        logger.info("Server terminated.")


if __name__ == "__main__":
    run_server()
