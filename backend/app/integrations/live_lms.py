from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx

from .base import BaseIntegrationAdapter, NormalizedEnvelope

logger = logging.getLogger(__name__)


class LiveLMSAdapter(BaseIntegrationAdapter):
    source: str = "lms"

    def __init__(
        self,
        base_url: str = "https://rtkb.zion-lms.ru",
        api_token: str | None = None,
        timeout: float | httpx.Timeout | None = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        raw_url = str(base_url or "").strip().rstrip("/")
        if not raw_url:
            raw_url = "https://rtkb.zion-lms.ru"
        elif not (raw_url.startswith("http://") or raw_url.startswith("https://")):
            raw_url = f"https://{raw_url}"
        self.base_url = raw_url

        clean_token = str(api_token).strip() if api_token is not None else None
        if clean_token:
            if clean_token.lower().startswith("bearer "):
                clean_token = clean_token[7:].strip()
            clean_token = clean_token.strip("'\"")
        self.api_token = clean_token or None

        if timeout is None:
            self.timeout = httpx.Timeout(10.0, connect=5.0, read=30.0)
        elif isinstance(timeout, httpx.Timeout):
            self.timeout = timeout
        else:
            try:
                t_val = float(timeout)
                if not math.isfinite(t_val) or t_val <= 0.0:
                    t_val = 10.0
            except (ValueError, TypeError):
                t_val = 10.0
            self.timeout = httpx.Timeout(t_val, connect=5.0, read=30.0)
        self.transport = transport
        self.last_error: str | None = None

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self.timeout, transport=self.transport, follow_redirects=True)

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def health_check(self) -> dict[str, Any]:
        start = time.perf_counter()
        try:
            with self._client() as client:
                resp = client.get(f"{self.base_url}/api/v1/health", headers=self._headers())
                latency_ms = (time.perf_counter() - start) * 1000
                if resp.is_success:
                    remote_error = None
                    ct = resp.headers.get("content-type", "").lower()
                    if "text/html" in ct:
                        remote_error = "Remote service returned HTML instead of JSON"
                    else:
                        try:
                            body = resp.json()
                        except Exception as json_err:
                            remote_error = f"Invalid JSON response: {json_err}"
                            body = None

                        if remote_error is None:
                            if isinstance(body, dict):
                                if (
                                    body.get("healthy") is False
                                    or body.get("ok") is False
                                    or body.get("success") is False
                                    or body.get("status") is False
                                ):
                                    remote_error = (
                                        body.get("message")
                                        or body.get("error")
                                        or body.get("reason")
                                        or "Service reported unhealthy status"
                                    )
                                elif body.get("error") and not body.get("status"):
                                    remote_error = str(body["error"])
                                else:
                                    st = str(body.get("status", "")).strip().lower()
                                    if st in {
                                        "down",
                                        "error",
                                        "degraded",
                                        "unhealthy",
                                        "failing",
                                        "failed",
                                        "fail",
                                        "false",
                                        "0",
                                        "critical",
                                        "outage",
                                        "emergency",
                                    }:
                                        remote_error = (
                                            body.get("message")
                                            or body.get("error")
                                            or f"Service status is {st}"
                                        )
                            elif body is not None:
                                remote_error = f"Expected JSON object in health response, got {type(body).__name__}"

                    if remote_error:
                        logger.warning("LMS health check reported error from %s: %s", self.base_url, remote_error)
                        return {
                            "status": "error",
                            "connected": False,
                            "latency_ms": round(latency_ms, 2),
                            "mode": "live",
                            "source": self.source,
                            "endpoint": self.base_url,
                            "error": remote_error,
                        }

                    return {
                        "status": "ok",
                        "connected": True,
                        "latency_ms": round(latency_ms, 2),
                        "mode": "live",
                        "source": self.source,
                        "endpoint": self.base_url,
                    }
                logger.warning(
                    "LMS health check returned HTTP %s from %s",
                    resp.status_code,
                    self.base_url,
                )
                return {
                    "status": "error",
                    "connected": False,
                    "latency_ms": round(latency_ms, 2),
                    "mode": "live",
                    "source": self.source,
                    "endpoint": self.base_url,
                    "error": f"HTTP {resp.status_code}",
                }
        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.warning("LMS health check failed for %s: %s", self.base_url, exc)
            return {
                "status": "error",
                "connected": False,
                "latency_ms": round(latency_ms, 2),
                "mode": "live",
                "source": self.source,
                "endpoint": self.base_url,
                "error": str(exc),
            }

    def fetch_updates(self, since: datetime | str | None = None) -> list[NormalizedEnvelope]:
        params: dict[str, str] = {}
        since_aware = None
        if since is not None:
            if isinstance(since, str):
                try:
                    since = datetime.fromisoformat(since)
                except Exception:
                    since = None
            if since is not None:
                since_aware = since if since.tzinfo is not None else since.replace(tzinfo=timezone.utc)
                params["since"] = since_aware.isoformat()

        try:
            with self._client() as client:
                resp = client.get(
                    f"{self.base_url}/api/v1/metrics",
                    headers=self._headers(),
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()
                self.last_error = None
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("LMS fetch_updates failed from %s: %s", self.base_url, exc)
            return []

        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = (
                data.get("items")
                or data.get("metrics")
                or data.get("data")
                or data.get("result")
                or data.get("results")
                or data.get("records")
                or data.get("rows")
            )
            if items is None:
                if "metric_code" in data or "code" in data or "metric" in data or "value" in data:
                    items = [data]
                else:
                    items = []
            elif isinstance(items, dict):
                items = (
                    items.get("items")
                    or items.get("metrics")
                    or items.get("data")
                    or items.get("results")
                    or items.get("records")
                    or [items]
                )
        else:
            items = []

        if not isinstance(items, list):
            return []

        now = datetime.now(timezone.utc)
        envelopes: list[NormalizedEnvelope] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            raw_payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}

            org_id = str(item.get("organization_id") or item.get("org_id") or raw_payload.get("organization_id") or raw_payload.get("org_id") or "").strip()
            prog_raw = str(item.get("program_id") or item.get("prog_id") or raw_payload.get("program_id") or raw_payload.get("prog_id") or "").strip()
            prog_id = prog_raw if prog_raw.startswith("program-") or not prog_raw else f"program-{prog_raw}"
            prog_slug = str(item.get("prog_slug") or raw_payload.get("prog_slug") or (prog_raw.replace("program-", "") if prog_raw else "")).strip()
            metric_code = str(
                item.get("metric_code")
                or item.get("code")
                or item.get("metric")
                or item.get("metric_name")
                or raw_payload.get("metric_code")
                or raw_payload.get("code")
                or raw_payload.get("metric")
                or raw_payload.get("metric_name")
                or ""
            ).strip().lower().replace("-", "_")
            metric_code = metric_code[:64]

            raw_ext_id = str(item.get("external_id") or raw_payload.get("external_id") or "").strip()
            raw_item_id = str(
                item.get("id")
                or item.get("metric_id")
                or raw_payload.get("id")
                or raw_payload.get("metric_id")
                or ""
            ).strip()
            if raw_ext_id:
                ext_id = raw_ext_id
            elif raw_item_id:
                ext_id = raw_item_id if raw_item_id.startswith("zion-") else f"zion-metric-{raw_item_id}"
            elif org_id and metric_code:
                ext_id = f"zion-metric-{org_id}-{prog_slug}-{metric_code}"
            else:
                ext_id = f"zion-metric-{uuid4()}"
            ext_id = ext_id[:128]

            raw_as_of = (
                item.get("as_of")
                or item.get("effective_at")
                or item.get("timestamp")
                or item.get("date")
                or item.get("created_at")
                or raw_payload.get("as_of")
                or raw_payload.get("effective_at")
                or raw_payload.get("timestamp")
                or raw_payload.get("date")
                or raw_payload.get("created_at")
            )
            if isinstance(raw_as_of, datetime):
                effective_dt = raw_as_of
            elif isinstance(raw_as_of, (int, float)) and not isinstance(raw_as_of, bool):
                try:
                    effective_dt = datetime.fromtimestamp(raw_as_of, tz=timezone.utc)
                except Exception:
                    effective_dt = now
            elif isinstance(raw_as_of, str):
                try:
                    effective_dt = datetime.fromisoformat(raw_as_of)
                except Exception:
                    effective_dt = now
            else:
                effective_dt = now

            if effective_dt.tzinfo is None:
                effective_dt = effective_dt.replace(tzinfo=timezone.utc)

            if since_aware is not None and effective_dt < since_aware:
                continue

            raw_val = item.get("value") if item.get("value") is not None else raw_payload.get("value", 0.0)
            try:
                val = float(raw_val)
                if not math.isfinite(val):
                    val = 0.0
            except (ValueError, TypeError):
                val = 0.0

            if metric_code in {"active_cohorts", "students_enrolled", "students_completed"} and val < 0.0:
                val = 0.0
            elif metric_code == "attendance_rate":
                val = max(0.0, min(100.0, val))

            unit = str(item.get("unit") or raw_payload.get("unit") or "").strip()
            if not unit:
                if "cohort" in metric_code:
                    unit = "cohort"
                elif "student" in metric_code:
                    unit = "student"
                elif "attendance" in metric_code or "rate" in metric_code:
                    unit = "percent"
            unit = unit[:32]

            payload = {**raw_payload} if raw_payload else {}
            payload["organization_id"] = org_id
            payload["organization_external_id"] = str(item.get("organization_external_id") or payload.get("organization_external_id") or org_id)[:128]
            payload["program_id"] = prog_id
            payload["program_external_id"] = str(item.get("program_external_id") or payload.get("program_external_id") or prog_id)[:128]
            payload["metric_code"] = metric_code
            payload["value"] = val
            payload["unit"] = unit
            payload["as_of"] = effective_dt.isoformat()
            payload.setdefault("definition_version", str(item.get("definition_version") or payload.get("definition_version") or "proposal-1"))

            org_name = str(item.get("organization_name") or item.get("org_name") or payload.get("organization_name") or "").strip()
            if org_name:
                payload["organization_name"] = org_name[:250]
            prog_name = str(item.get("program_name") or item.get("prog_name") or payload.get("program_name") or "").strip()
            if prog_name:
                payload["program_name"] = prog_name[:200]

            rev = item.get("source_revision") if item.get("source_revision") is not None else (item.get("revision") or raw_payload.get("source_revision") or raw_payload.get("revision"))
            source_revision = str(rev)[:64] if rev is not None else "1"

            envelope = NormalizedEnvelope(
                schema_version=str(item.get("schema_version") or raw_payload.get("schema_version") or "1.0"),
                source=self.source,
                entity_type="learning_metric",
                external_id=ext_id,
                source_revision=source_revision,
                operation=str(item.get("operation") or raw_payload.get("operation") or "upsert"),
                effective_at=effective_dt,
                received_at=now,
                payload=payload,
            )
            envelopes.append(envelope)

        return envelopes
