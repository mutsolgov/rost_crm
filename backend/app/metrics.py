"""Prometheus RED-metrics collector using Python standard library.

Provides lightweight, thread-safe metrics exposition conforming to
Prometheus Exposition Format 0.0.4 (text/plain; version=0.0.4; charset=utf-8).
No external third-party dependencies required.
"""

from __future__ import annotations

import re
import threading
from collections import defaultdict
from typing import TYPE_CHECKING

from fastapi import Response

if TYPE_CHECKING:
    from fastapi import Request

# Standard histogram buckets in seconds
DEFAULT_BUCKETS: tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)


def _escape_label_value(val: str) -> str:
    """Escape special characters in Prometheus label values."""
    return val.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _format_labels(labels: dict[str, str]) -> str:
    """Format dictionary of labels into Prometheus format {k="v",...} sorted by key."""
    if not labels:
        return ""
    parts = [f'{k}="{_escape_label_value(str(v))}"' for k, v in sorted(labels.items())]
    return "{" + ",".join(parts) + "}"


class MetricsCollector:
    """In-memory, thread-safe Prometheus metrics collector."""

    def __init__(self, buckets: tuple[float, ...] = DEFAULT_BUCKETS) -> None:
        self.buckets = buckets
        self._lock = threading.Lock()
        self._http_requests_total: dict[tuple[str, str, str], int] = defaultdict(int)
        self._http_duration_sums: dict[tuple[str, str], float] = defaultdict(float)
        self._http_duration_counts: dict[tuple[str, str], int] = defaultdict(int)
        self._http_duration_buckets: dict[tuple[str, str, float], int] = defaultdict(int)
        self._active_background_jobs: int = 0
        self._webhooks_total: dict[tuple[str, str], int] = defaultdict(int)

    def record_http_request(
        self,
        method: str,
        endpoint: str,
        status_code: int | str,
        duration_seconds: float,
    ) -> None:
        """Record an observed HTTP request counter and duration."""
        m = (method or "GET").strip().upper()
        ep = (endpoint or "unknown").strip()
        sc = str(status_code)
        dur = max(0.0, float(duration_seconds))

        with self._lock:
            self._http_requests_total[(m, ep, sc)] += 1
            self._http_duration_sums[(m, ep)] += dur
            self._http_duration_counts[(m, ep)] += 1
            for b in self.buckets:
                if dur <= b:
                    self._http_duration_buckets[(m, ep, b)] += 1

    def inc_active_background_jobs(self, amount: int = 1) -> None:
        """Increment active background jobs gauge."""
        with self._lock:
            self._active_background_jobs += amount

    def dec_active_background_jobs(self, amount: int = 1) -> None:
        """Decrement active background jobs gauge."""
        with self._lock:
            self._active_background_jobs = max(0, self._active_background_jobs - amount)

    def set_active_background_jobs(self, count: int) -> None:
        """Explicitly set active background jobs gauge."""
        with self._lock:
            self._active_background_jobs = max(0, count)

    def get_active_background_jobs(self) -> int:
        """Return current count of active background jobs."""
        with self._lock:
            return self._active_background_jobs

    def record_webhook(self, source: str, status: str) -> None:
        """Record webhook counter with source and status."""
        src = (source or "unknown").strip().lower()
        st = (status or "unknown").strip().lower()
        with self._lock:
            self._webhooks_total[(src, st)] += 1

    def reset(self) -> None:
        """Reset all metrics state (useful for isolated tests)."""
        with self._lock:
            self._http_requests_total.clear()
            self._http_duration_sums.clear()
            self._http_duration_counts.clear()
            self._http_duration_buckets.clear()
            self._active_background_jobs = 0
            self._webhooks_total.clear()

    def generate_metrics_exposition(self) -> str:
        """Generate text output in Prometheus Exposition Format 0.0.4."""
        lines: list[str] = []

        with self._lock:
            # 1. http_requests_total
            lines.append("# HELP http_requests_total Total number of HTTP requests processed.")
            lines.append("# TYPE http_requests_total counter")
            for (m, ep, sc), count in sorted(self._http_requests_total.items()):
                labels_str = _format_labels({"method": m, "endpoint": ep, "status_code": sc})
                lines.append(f"http_requests_total{labels_str} {count}")

            # 2. http_request_duration_seconds
            lines.append("# HELP http_request_duration_seconds HTTP request duration in seconds.")
            lines.append("# TYPE http_request_duration_seconds histogram")
            # Distinct pairs of (method, endpoint)
            pairs = sorted(self._http_duration_counts.keys())
            for m, ep in pairs:
                for b in self.buckets:
                    b_count = self._http_duration_buckets.get((m, ep, b), 0)
                    b_str = str(b)
                    lbl = _format_labels({"method": m, "endpoint": ep, "le": b_str})
                    lines.append(f"http_request_duration_seconds_bucket{lbl} {b_count}")
                total_cnt = self._http_duration_counts.get((m, ep), 0)
                lbl_inf = _format_labels({"method": m, "endpoint": ep, "le": "+Inf"})
                lines.append(f"http_request_duration_seconds_bucket{lbl_inf} {total_cnt}")
                total_sum = self._http_duration_sums.get((m, ep), 0.0)
                lbl_base = _format_labels({"method": m, "endpoint": ep})
                lines.append(f"http_request_duration_seconds_sum{lbl_base} {total_sum:.6f}")
                lines.append(f"http_request_duration_seconds_count{lbl_base} {total_cnt}")

            # 3. active_background_jobs
            lines.append("# HELP active_background_jobs Number of active background jobs.")
            lines.append("# TYPE active_background_jobs gauge")
            lines.append(f"active_background_jobs {self._active_background_jobs}")

            # 4. webhooks_total
            lines.append("# HELP webhooks_total Total number of processed webhooks.")
            lines.append("# TYPE webhooks_total counter")
            for (src, st), count in sorted(self._webhooks_total.items()):
                lbl = _format_labels({"source": src, "status": st})
                lines.append(f"webhooks_total{lbl} {count}")

        # Trailing newline is mandatory in Prometheus 0.0.4 exposition format
        return "\n".join(lines) + "\n"


# Singleton instance
collector = MetricsCollector()


def record_http_request(
    method: str,
    endpoint: str,
    status_code: int | str,
    duration_seconds: float,
) -> None:
    """Record HTTP request in global collector."""
    collector.record_http_request(method, endpoint, status_code, duration_seconds)


def inc_active_background_jobs(amount: int = 1) -> None:
    """Increment active background jobs in global collector."""
    collector.inc_active_background_jobs(amount)


def dec_active_background_jobs(amount: int = 1) -> None:
    """Decrement active background jobs in global collector."""
    collector.dec_active_background_jobs(amount)


def set_active_background_jobs(count: int) -> None:
    """Set active background jobs in global collector."""
    collector.set_active_background_jobs(count)


def get_active_background_jobs() -> int:
    """Get active background jobs from global collector."""
    return collector.get_active_background_jobs()


def record_webhook(source: str, status: str) -> None:
    """Record webhook in global collector."""
    collector.record_webhook(source, status)


def resolve_endpoint(request: Request) -> str:
    """Resolve matched route path template or sanitize raw URL path to prevent label explosion."""
    route = request.scope.get("route")
    if route and hasattr(route, "path") and route.path:
        return str(route.path)

    raw_path = request.url.path
    # 1. Normalize UUIDs: /[0-9a-fA-F-]{32,36} -> /{uuid}
    cleaned = re.sub(
        r"/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        "/{uuid}",
        raw_path,
    )
    # 2. Normalize interaction IDs: /ix-... -> /{interaction_id}
    cleaned = re.sub(r"/ix-[a-zA-Z0-9_-]+", "/{interaction_id}", cleaned)
    # 3. Normalize numeric IDs: /123 -> /{id}
    cleaned = re.sub(r"/\d+", "/{id}", cleaned)
    return cleaned or "unknown"


def generate_metrics_response() -> Response:
    """Generate FastAPI/Starlette Response with Prometheus Exposition Format 0.0.4."""
    content = collector.generate_metrics_exposition()
    return Response(
        content=content,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
