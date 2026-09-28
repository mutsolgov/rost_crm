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


class LiveWebsiteAdapter(BaseIntegrationAdapter):
    source: str = "website"

    def __init__(
        self,
        base_url: str = "https://it-school.rt.ru",
        api_token: str | None = None,
        timeout: float | httpx.Timeout | None = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        raw_url = str(base_url or "").strip().rstrip("/")
        if not raw_url:
            raw_url = "https://it-school.rt.ru"
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
                resp = client.get(f"{self.base_url}/api/health", headers=self._headers())
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
                        logger.warning("Website health check reported error from %s: %s", self.base_url, remote_error)
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
                    "Website health check returned HTTP %s from %s",
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
            logger.warning("Website health check failed for %s: %s", self.base_url, exc)
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
                    f"{self.base_url}/api/v1/applications",
                    headers=self._headers(),
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()
                self.last_error = None
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("Website fetch_updates failed from %s: %s", self.base_url, exc)
            return []

        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = (
                data.get("items")
                or data.get("applications")
                or data.get("data")
                or data.get("result")
                or data.get("results")
                or data.get("records")
                or data.get("rows")
            )
            if items is None:
                if (
                    "organization_name" in data
                    or "representative_email" in data
                    or "contact" in data
                    or "program_id" in data
                    or "university" in data
                ):
                    items = [data]
                else:
                    items = []
            elif isinstance(items, dict):
                items = (
                    items.get("items")
                    or items.get("applications")
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

            raw_ext_id = str(item.get("external_id") or raw_payload.get("external_id") or "").strip()
            raw_item_id = str(
                item.get("id")
                or item.get("application_id")
                or item.get("app_id")
                or item.get("number")
                or raw_payload.get("id")
                or raw_payload.get("application_id")
                or raw_payload.get("app_id")
                or raw_payload.get("number")
                or ""
            ).strip()
            if raw_ext_id:
                ext_id = raw_ext_id
            elif raw_item_id:
                ext_id = raw_item_id if raw_item_id.startswith("web-app-") else f"web-app-{raw_item_id}"
            else:
                ext_id = f"web-app-{uuid4()}"
            ext_id = ext_id[:128]

            raw_dt = (
                item.get("effective_at")
                or item.get("created_at")
                or item.get("submitted_at")
                or item.get("as_of")
                or item.get("timestamp")
                or item.get("date")
                or raw_payload.get("effective_at")
                or raw_payload.get("created_at")
                or raw_payload.get("submitted_at")
                or raw_payload.get("as_of")
                or raw_payload.get("timestamp")
                or raw_payload.get("date")
            )
            if isinstance(raw_dt, datetime):
                effective_dt = raw_dt
            elif isinstance(raw_dt, (int, float)) and not isinstance(raw_dt, bool):
                try:
                    effective_dt = datetime.fromtimestamp(raw_dt, tz=timezone.utc)
                except Exception:
                    effective_dt = now
            elif isinstance(raw_dt, str):
                try:
                    effective_dt = datetime.fromisoformat(raw_dt)
                except Exception:
                    effective_dt = now
            else:
                effective_dt = now

            if effective_dt.tzinfo is None:
                effective_dt = effective_dt.replace(tzinfo=timezone.utc)

            if since_aware is not None and effective_dt < since_aware:
                continue

            contact_obj = item.get("contact") if isinstance(item.get("contact"), dict) else (raw_payload.get("contact") if isinstance(raw_payload.get("contact"), dict) else {})
            rep_name = str(
                item.get("representative_name")
                or item.get("contact_name")
                or item.get("full_name")
                or item.get("fio")
                or item.get("name")
                or contact_obj.get("full_name")
                or contact_obj.get("name")
                or raw_payload.get("representative_name")
                or raw_payload.get("contact_name")
                or raw_payload.get("full_name")
                or raw_payload.get("fio")
                or raw_payload.get("name")
                or ""
            ).strip()
            rep_pos = str(
                item.get("representative_position")
                or item.get("position")
                or item.get("role")
                or contact_obj.get("position")
                or raw_payload.get("representative_position")
                or raw_payload.get("position")
                or raw_payload.get("role")
                or ""
            ).strip()
            rep_email = str(
                item.get("representative_email")
                or item.get("email")
                or contact_obj.get("email")
                or raw_payload.get("representative_email")
                or raw_payload.get("email")
                or ""
            ).strip()
            rep_phone = str(
                item.get("representative_phone")
                or item.get("phone")
                or item.get("phone_number")
                or item.get("telephone")
                or contact_obj.get("phone")
                or contact_obj.get("phone_number")
                or raw_payload.get("representative_phone")
                or raw_payload.get("phone")
                or raw_payload.get("phone_number")
                or ""
            ).strip()

            prog_raw = str(item.get("program_id") or item.get("prog_id") or raw_payload.get("program_id") or raw_payload.get("prog_id") or "").strip()
            prog_id = prog_raw if prog_raw.startswith("program-") or not prog_raw else f"program-{prog_raw}"
            prog_name = str(item.get("program_name") or item.get("prog_name") or raw_payload.get("program_name") or raw_payload.get("prog_name") or "").strip()

            org_name = str(
                item.get("organization_name")
                or item.get("university_name")
                or item.get("university")
                or item.get("organization")
                or item.get("org_name")
                or item.get("institution_name")
                or raw_payload.get("organization_name")
                or raw_payload.get("university_name")
                or raw_payload.get("university")
                or raw_payload.get("organization")
                or raw_payload.get("org_name")
                or ""
            ).strip()
            org_ext_id = item.get("organization_external_id") or item.get("org_id") or raw_payload.get("organization_external_id") or raw_payload.get("org_id")

            comments = str(
                item.get("comments")
                or item.get("comment")
                or item.get("message")
                or item.get("notes")
                or item.get("note")
                or raw_payload.get("comments")
                or raw_payload.get("comment")
                or raw_payload.get("message")
                or raw_payload.get("notes")
                or raw_payload.get("note")
                or ""
            ).strip()

            payload = {**raw_payload} if raw_payload else {}
            payload["organization_name"] = org_name[:250]
            payload["organization_external_id"] = (str(org_ext_id).strip()[:128] or None) if org_ext_id is not None else None
            payload["representative_name"] = rep_name[:250]
            payload["representative_position"] = rep_pos[:200]
            payload["representative_email"] = rep_email[:200]
            payload["representative_phone"] = rep_phone[:100]
            payload["program_name"] = prog_name[:200]
            payload["program_id"] = prog_id
            payload["comments"] = comments

            rev = item.get("source_revision") if item.get("source_revision") is not None else (item.get("revision") or raw_payload.get("source_revision") or raw_payload.get("revision"))
            source_revision = str(rev)[:64] if rev is not None else "1"

            envelope = NormalizedEnvelope(
                schema_version=str(item.get("schema_version") or raw_payload.get("schema_version") or "1.0"),
                source=self.source,
                entity_type="application",
                external_id=ext_id,
                source_revision=source_revision,
                operation=str(item.get("operation") or raw_payload.get("operation") or "upsert"),
                effective_at=effective_dt,
                received_at=now,
                payload=payload,
            )
            envelopes.append(envelope)

        return envelopes
