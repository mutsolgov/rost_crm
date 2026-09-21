from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .base import BaseIntegrationAdapter, NormalizedEnvelope


class MockLMSAdapter(BaseIntegrationAdapter):
    source: str = "lms"

    def __init__(self, base_url: str = "https://rtkb.zion-lms.ru") -> None:
        self.base_url = base_url

    def health_check(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "mode": "mock",
            "source": self.source,
            "endpoint": self.base_url,
            "latency_ms": 14,
        }

    def fetch_updates(self, since: datetime | None = None) -> list[NormalizedEnvelope]:
        # Reference date for static mock fixtures
        effective_dt = datetime(2026, 9, 18, 0, 0, 0, tzinfo=timezone.utc)
        if since is not None and effective_dt < since:
            return []

        fixtures = [
            # org-1 (МТУ) × program-devops
            {
                "org_id": "org-1",
                "prog_id": "program-devops",
                "prog_slug": "devops",
                "metric_code": "active_cohorts",
                "value": 2.0,
                "unit": "cohort",
            },
            {
                "org_id": "org-1",
                "prog_id": "program-devops",
                "prog_slug": "devops",
                "metric_code": "students_enrolled",
                "value": 45.0,
                "unit": "student",
            },
            {
                "org_id": "org-1",
                "prog_id": "program-devops",
                "prog_slug": "devops",
                "metric_code": "students_completed",
                "value": 38.0,
                "unit": "student",
            },
            {
                "org_id": "org-1",
                "prog_id": "program-devops",
                "prog_slug": "devops",
                "metric_code": "attendance_rate",
                "value": 91.5,
                "unit": "percent",
            },
            # org-2 (Северный университет) × program-qa
            {
                "org_id": "org-2",
                "prog_id": "program-qa",
                "prog_slug": "qa",
                "metric_code": "active_cohorts",
                "value": 1.0,
                "unit": "cohort",
            },
            {
                "org_id": "org-2",
                "prog_id": "program-qa",
                "prog_slug": "qa",
                "metric_code": "students_enrolled",
                "value": 30.0,
                "unit": "student",
            },
            {
                "org_id": "org-2",
                "prog_id": "program-qa",
                "prog_slug": "qa",
                "metric_code": "students_completed",
                "value": 26.0,
                "unit": "student",
            },
            {
                "org_id": "org-2",
                "prog_id": "program-qa",
                "prog_slug": "qa",
                "metric_code": "attendance_rate",
                "value": 88.0,
                "unit": "percent",
            },
            # org-3 (Поволжский ГУТИ) × program-devops
            {
                "org_id": "org-3",
                "prog_id": "program-devops",
                "prog_slug": "devops",
                "metric_code": "active_cohorts",
                "value": 3.0,
                "unit": "cohort",
            },
            {
                "org_id": "org-3",
                "prog_id": "program-devops",
                "prog_slug": "devops",
                "metric_code": "students_enrolled",
                "value": 60.0,
                "unit": "student",
            },
            {
                "org_id": "org-3",
                "prog_id": "program-devops",
                "prog_slug": "devops",
                "metric_code": "students_completed",
                "value": 51.0,
                "unit": "student",
            },
            {
                "org_id": "org-3",
                "prog_id": "program-devops",
                "prog_slug": "devops",
                "metric_code": "attendance_rate",
                "value": 93.2,
                "unit": "percent",
            },
        ]

        now = datetime.now(timezone.utc)
        envelopes: list[NormalizedEnvelope] = []
        for fix in fixtures:
            ext_id = f"zion-metric-{fix['org_id']}-{fix['prog_slug']}-{fix['metric_code']}"
            payload = {
                "organization_id": fix["org_id"],
                "organization_external_id": fix["org_id"],
                "program_id": fix["prog_id"],
                "program_external_id": fix["prog_id"],
                "metric_code": fix["metric_code"],
                "value": fix["value"],
                "unit": fix["unit"],
                "as_of": effective_dt.isoformat(),
                "definition_version": "proposal-1",
            }
            envelope = NormalizedEnvelope(
                schema_version="1.0",
                source=self.source,
                entity_type="learning_metric",
                external_id=ext_id,
                source_revision="1",
                operation="upsert",
                effective_at=effective_dt,
                received_at=now,
                payload=payload,
            )
            envelopes.append(envelope)

        return envelopes
