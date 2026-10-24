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
from app.core.llm import is_llm_available
from app.db.supabase_client import active_store

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def get_health():
    return HealthResponse(
        status="ok",
        model_version=settings.MODEL_VERSION,
        llm_available=is_llm_available(),
        store=active_store(),
    )
