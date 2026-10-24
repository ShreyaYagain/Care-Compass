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

from fastapi import Depends, HTTPException, status
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


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> str:
    """Required auth. Returns the user id (sub), or 401."""
    dev = _dev_user_id()
    if dev:
        return dev

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    payload = _decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing the 'sub' claim",
        )
    return str(sub)


def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> Optional[str]:
    """Optional auth for /triage and /book. Returns None if no valid token."""
    dev = _dev_user_id()
    if dev:
        return dev

    if credentials is None:
        return None

    payload = _decode_token(credentials.credentials)
    if not payload:
        return None
    sub = payload.get("sub")
    return str(sub) if sub else None
