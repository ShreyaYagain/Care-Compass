"""Shared test fixtures.

Forces the SQLite fallback (no Supabase) for every test and binds the store to a
fresh, per-test SQLite database so history/booking tests are isolated and
deterministic.

The semantic red-flag screen is neutralised by default (gemini_ok, no flags) so
tests of other layers are not hijacked by the combined failsafe question; tests
that exercise the screen patch app.core.pipeline.screen_red_flags (or
semantic_screen internals) themselves — the inner patch wins.
"""
import pytest


@pytest.fixture(autouse=True)
def _isolated_sqlite(tmp_path):
    from app.config import settings
    settings.SUPABASE_URL = ""
    settings.SUPABASE_SERVICE_ROLE_KEY = ""
    settings.GEMINI_API_KEY = ""

    import app.db.session as sess
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    sess.engine = engine
    sess.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    sess.Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def _neutral_semantic_screen():
    from unittest.mock import patch
    with patch(
        "app.core.pipeline.screen_red_flags",
        return_value={"status": "gemini_ok", "flags": [], "combined": False},
    ):
        yield
