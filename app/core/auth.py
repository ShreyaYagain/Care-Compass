"""Supabase JWT authentication.

`get_current_user` verifies a `Authorization: Bearer <token>` header and returns
the authenticated user's id (`sub`). Verification order:
  1. HS256 using SUPABASE_JWT_SECRET, or
  2. RS256/ES256 via a JWKS (SUPABASE_JWKS_URL).
The `exp` claim and the `aud == "authenticated"` claim are checked.

In dev (`ENV=dev`), a `DEV_USER_ID` env override lets local tests and the demo
run without minting a real token.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import settings

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)

JWKS_TIMEOUT_S = 3.0


def _decode_token(token: str) -> Optional[dict]:
    try:
        import jwt as pyjwt
    except ImportError:  # pragma: no cover
        logger.warning("PyJWT is not installed; token verification unavailable")
        return None

    if settings.SUPABASE_JWT_SECRET:
        try:
            return pyjwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated",
            )
        except Exception as e:
            logger.warning(f"HS256 JWT verification failed: {e}")

    if settings.SUPABASE_JWKS_URL:
        try:
            from jwt import PyJWKClient
            jwks = PyJWKClient(settings.SUPABASE_JWKS_URL, timeout=JWKS_TIMEOUT_S)
            signing_key = jwks.get_signing_key_from_jwt(token)
            return pyjwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                audience="authenticated",
            )
        except Exception as e:
            logger.warning(f"JWKS JWT verification failed: {e}")

    return None


def _dev_user_id() -> Optional[str]:
    if settings.ENV == "dev" and settings.DEV_USER_ID:
        return settings.DEV_USER_ID
    return None


def _resolve_history_key(
    credentials: Optional[HTTPAuthorizationCredentials],
    request: Optional[Request],
    required: bool,
) -> Optional[str]:
    """Single definition of the history key used by every store call.

    Priority:
      1. Dev mode: the device id header (settings.HISTORY_KEY_HEADER) sent by
         the app, so history is keyed per device.
      2. Dev mode: DEV_USER_ID override.
      3. A valid bearer JWT (`sub` claim).
    """
    # 1. Device id (dev only; the app sends its persisted device id).
    if settings.ENV == "dev" and request is not None:
        device = (request.headers.get(settings.HISTORY_KEY_HEADER) or "").strip()
        if device:
            return f"device-{device}"

    # 2. Dev user override.
    dev = _dev_user_id()
    if dev:
        return dev

    # 3. Bearer JWT.
    if credentials is not None:
        payload = _decode_token(credentials.credentials)
        if payload:
            sub = payload.get("sub")
            if sub:
                return str(sub)

    if required:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    return None


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    request: Request = None,
) -> str:
    """Required auth. Returns the history key, or 401."""
    return _resolve_history_key(credentials, request, required=True)


def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    request: Request = None,
) -> Optional[str]:
    """Optional auth for /triage and /book. Returns the history key or None."""
    return _resolve_history_key(credentials, request, required=False)
