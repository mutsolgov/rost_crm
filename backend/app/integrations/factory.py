from __future__ import annotations

import os

from ..config import Settings, get_settings
from .base import BaseIntegrationAdapter
from .live_lms import LiveLMSAdapter
from .live_website import LiveWebsiteAdapter
from .mock_lms import MockLMSAdapter
from .mock_website import MockWebsiteAdapter


def get_adapter(source: str, settings: Settings | None = None) -> BaseIntegrationAdapter:
    cfg = settings or get_settings()
    src = (source or "").strip().lower()

    if src == "lms":
        mode = (cfg.lms_integration_mode or "").strip().lower()
        if mode == "mock":
            return MockLMSAdapter(base_url=cfg.lms_base_url)
        if mode == "live":
            token = getattr(cfg, "lms_api_token", None) if settings is not None else (getattr(cfg, "lms_api_token", None) or os.getenv("LMS_API_TOKEN"))
            return LiveLMSAdapter(base_url=cfg.lms_base_url, api_token=token)
        raise NotImplementedError(f"Unsupported LMS integration mode: '{cfg.lms_integration_mode}'")
    elif src == "website":
        mode = (cfg.website_integration_mode or "").strip().lower()
        if mode == "mock":
            return MockWebsiteAdapter(base_url=cfg.website_base_url)
        if mode == "live":
            token = getattr(cfg, "website_api_token", None) if settings is not None else (getattr(cfg, "website_api_token", None) or os.getenv("WEBSITE_API_TOKEN"))
            return LiveWebsiteAdapter(base_url=cfg.website_base_url, api_token=token)
        raise NotImplementedError(f"Unsupported Website integration mode: '{cfg.website_integration_mode}'")
    else:
        raise ValueError(f"Unknown integration source: '{source}'. Allowed sources: 'lms', 'website'")
