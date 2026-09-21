from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class NormalizedEnvelope:
    schema_version: str = "1.0"
    source: str = ""
    entity_type: str = ""
    external_id: str = ""
    source_revision: str = "1"
    operation: str = "upsert"
    effective_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "entity_type": self.entity_type,
            "external_id": self.external_id,
            "source_revision": self.source_revision,
            "operation": self.operation,
            "effective_at": (
                self.effective_at.isoformat()
                if hasattr(self.effective_at, "isoformat")
                else str(self.effective_at)
            ),
            "received_at": (
                self.received_at.isoformat()
                if hasattr(self.received_at, "isoformat")
                else str(self.received_at)
            ),
            "payload": self.payload,
        }


class BaseIntegrationAdapter(ABC):
    @abstractmethod
    def fetch_updates(self, since: datetime | None = None) -> list[NormalizedEnvelope]:
        """Fetch normalized updates from external source optionally filtered by since."""
        pass

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Return adapter connectivity and status dictionary."""
        pass
