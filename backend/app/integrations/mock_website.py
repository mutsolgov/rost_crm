from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .base import BaseIntegrationAdapter, NormalizedEnvelope


class MockWebsiteAdapter(BaseIntegrationAdapter):
    source: str = "website"

    def __init__(self, base_url: str = "https://it-school.rt.ru") -> None:
        self.base_url = base_url

    def health_check(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "mode": "mock",
            "source": self.source,
            "endpoint": self.base_url,
            "latency_ms": 18,
        }

    def fetch_updates(self, since: datetime | None = None) -> list[NormalizedEnvelope]:
        # Reference date for static mock website submissions
        effective_dt = datetime(2026, 9, 19, 14, 20, 0, tzinfo=timezone.utc)
        if since is not None and effective_dt < since:
            return []

        fixtures = [
            # 1. Known organization match (org-1: Московский технический университет)
            {
                "external_id": "web-app-001",
                "organization_name": "Московский технический университет",
                "organization_external_id": None,
                "representative_name": "Ковалев Андрей Сергеевич",
                "representative_position": "Декан факультета ИТ",
                "representative_email": "kovalev@mtu-edu.ru",
                "representative_phone": "+7 (495) 777-01-23",
                "program_name": "DevOps и облачные технологии",
                "program_id": "program-devops",
                "comments": "Заявка на расширение квоты для второго потока студентов.",
            },
            # 2. Unknown organization (Казанский национальный исследовательский технический университет)
            {
                "external_id": "web-app-002",
                "organization_name": "Казанский национальный исследовательский технический университет им. А.Н. Туполева",
                "organization_external_id": None,
                "representative_name": "Иванов Иван Иванович",
                "representative_position": "Заведующий кафедрой автоматизированных систем",
                "representative_email": "ivanov@kai.ru",
                "representative_phone": "+7 (843) 231-01-01",
                "program_name": "DevOps и облачные технологии",
                "program_id": "program-devops",
                "comments": "Просим рассмотреть возможность заключения партнерского договора.",
            },
            # 3. Unknown organization (Сибирский политехнический университет)
            {
                "external_id": "web-app-003",
                "organization_name": "Сибирский политехнический университет",
                "organization_external_id": None,
                "representative_name": "Сидоров Алексей Владимирович",
                "representative_position": "Проректор по учебной работе",
                "representative_email": "sidorov@sibpolytech.ru",
                "representative_phone": "+7 (383) 222-33-44",
                "program_name": "Инженерия качества ПО",
                "program_id": "program-qa",
                "comments": "Заявка на участие в партнерской программе ИТ-Школы.",
            },
            # 4. Known organization match (org-2: Северный университет прикладных наук)
            {
                "external_id": "web-app-004",
                "organization_name": "Северный университет прикладных наук",
                "organization_external_id": None,
                "representative_name": "Смирнова Ольга Павловна",
                "representative_position": "Руководитель учебного отдела",
                "representative_email": "smirnova@north-uni.ru",
                "representative_phone": "+7 (8182) 20-30-40",
                "program_name": "Инженерия качества ПО",
                "program_id": "program-qa",
                "comments": "Заявка на согласование нового цикла обучения.",
            },
        ]

        now = datetime.now(timezone.utc)
        envelopes: list[NormalizedEnvelope] = []
        for fix in fixtures:
            payload = {
                "organization_name": fix["organization_name"],
                "organization_external_id": fix["organization_external_id"],
                "representative_name": fix["representative_name"],
                "representative_position": fix["representative_position"],
                "representative_email": fix["representative_email"],
                "representative_phone": fix["representative_phone"],
                "program_name": fix["program_name"],
                "program_id": fix["program_id"],
                "comments": fix["comments"],
            }
            envelope = NormalizedEnvelope(
                schema_version="1.0",
                source=self.source,
                entity_type="application",
                external_id=fix["external_id"],
                source_revision="1",
                operation="upsert",
                effective_at=effective_dt,
                received_at=now,
                payload=payload,
            )
            envelopes.append(envelope)

        return envelopes
