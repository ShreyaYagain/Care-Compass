"""Supabase client (server-side, service role).

The backend uses the service-role key so it bypasses Row Level Security; every
query must therefore filter by user_id itself. If the Supabase env vars are
missing, `supabase_available()` returns False and callers fall back to SQLite.
"""
from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

_client: Any = None
_available: bool | None = None


def supabase_available() -> bool:
    """True only when both URL and service-role key are configured."""
    return bool(settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY)


def get_supabase() -> Any:
    """Returns the shared server-side Supabase client, or None if unavailable."""
    global _client
    if not supabase_available():
        return None
    if _client is None:
        try:
            from supabase import create_client
            _client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        except Exception as e:  # pragma: no cover - init failure
            logger.warning(f"Could not initialise Supabase client: {e}")
            _client = None
    return _client


def active_store() -> str:
    """Name of the store currently in use ('supabase' or 'sqlite')."""
    return "supabase" if (supabase_available() and get_supabase() is not None) else "sqlite"
