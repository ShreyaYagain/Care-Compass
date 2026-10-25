try:
    from fastapi import APIRouter
except ImportError:
    class APIRouter:
        def __init__(self, *args, **kwargs):
            pass
        def get(self, *args, **kwargs):
            return lambda fn: fn
        def post(self, *args, **kwargs):
            return lambda fn: fn

from app.config import settings
from app.schemas import HealthResponse
from app.core.llm import self_test, last_llm_error, llm_fallback_count
from app.core.semantic_screen import get_screen_status
from app.core.stt import stt_provider
from app.db.supabase_client import active_store

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def get_health():
    check = self_test()
    return HealthResponse(
        status="ok",
        model_version=settings.MODEL_VERSION,
        llm_available=bool(check.get("available")),
        llm_provider=check.get("provider"),
        llm_model=check.get("model"),
        llm_status=check.get("status"),
        stt_provider=stt_provider(),
        last_llm_error=last_llm_error(),
        llm_fallback_count=llm_fallback_count(),
        store=active_store(),
        screen_status=get_screen_status(),
    )
