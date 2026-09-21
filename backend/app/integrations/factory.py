from __future__ import annotations

from ..config import Settings, get_settings
from .base import BaseIntegrationAdapter
from .mock_lms import MockLMSAdapter
from .mock_website import MockWebsiteAdapter


def get_adapter(source: str, settings: Settings | None = None) -> BaseIntegrationAdapter:
    cfg = settings or get_settings()
    src = (source or "").strip().lower()

    if src == "lms":
        mode = cfg.lms_integration_mode
        if mode == "mock":
            return MockLMSAdapter(base_url=cfg.lms_base_url)
        raise NotImplementedError("Live LMS adapter is not supported in this environment")
    elif src == "website":
        mode = cfg.website_integration_mode
        if mode == "mock":
            return MockWebsiteAdapter(base_url=cfg.website_base_url)
        raise NotImplementedError("Live Website adapter is not supported in this environment")
    else:
        raise ValueError(f"Unknown integration source: '{source}'. Allowed sources: 'lms', 'website'")
