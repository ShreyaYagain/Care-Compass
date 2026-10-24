"""Supabase auth tests (JWT verification + optional/required auth)."""
import datetime
import unittest

import jwt as pyjwt
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.config import settings
from app.core.auth import get_current_user, get_current_user_optional, _decode_token

TEST_SECRET = "test-secret-for-unit-tests-only"


def _make_token(secret: str, sub: str, aud: str = "authenticated", exp_delta: int = 3600):
    now = datetime.datetime.now(datetime.timezone.utc)
    return pyjwt.encode(
        {"sub": sub, "aud": aud, "iss": "supabase", "exp": now + datetime.timedelta(seconds=exp_delta)},
        secret,
        algorithm="HS256",
    )


class TestSupabaseAuth(unittest.TestCase):

    def setUp(self):
        self._orig_secret = settings.SUPABASE_JWT_SECRET
        self._orig_env = settings.ENV
        self._orig_dev = settings.DEV_USER_ID
        settings.ENV = "prod"
        settings.DEV_USER_ID = ""

    def tearDown(self):
        settings.SUPABASE_JWT_SECRET = self._orig_secret
        settings.ENV = self._orig_env
        settings.DEV_USER_ID = self._orig_dev

    def test_missing_token_returns_401(self):
        with self.assertRaises(HTTPException) as ctx:
            get_current_user(credentials=None)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_invalid_token_returns_401(self):
        settings.SUPABASE_JWT_SECRET = TEST_SECRET
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not.a.jwt")
        with self.assertRaises(HTTPException) as ctx:
            get_current_user(credentials=creds)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_expired_token_returns_401(self):
        settings.SUPABASE_JWT_SECRET = TEST_SECRET
        token = _make_token(TEST_SECRET, "user-1", exp_delta=-10)
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        with self.assertRaises(HTTPException) as ctx:
            get_current_user(credentials=creds)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_valid_token_returns_sub(self):
        settings.SUPABASE_JWT_SECRET = TEST_SECRET
        token = _make_token(TEST_SECRET, "user-123")
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        self.assertEqual(get_current_user(credentials=creds), "user-123")

    def test_optional_auth_returns_none_without_token(self):
        self.assertIsNone(get_current_user_optional(credentials=None))

    def test_optional_auth_returns_user_with_valid_token(self):
        settings.SUPABASE_JWT_SECRET = TEST_SECRET
        token = _make_token(TEST_SECRET, "user-abc")
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        self.assertEqual(get_current_user_optional(credentials=creds), "user-abc")

    def test_dev_user_id_override(self):
        settings.ENV = "dev"
        settings.DEV_USER_ID = "dev-user-1"
        self.assertEqual(get_current_user(credentials=None), "dev-user-1")


if __name__ == "__main__":
    unittest.main()
