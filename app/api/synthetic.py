from typing import Optional
from fastapi import APIRouter, Query

from app.core.synthetic import synthetic_caregivers

router = APIRouter(tags=["Synthetic caregivers (demo)"])


@router.get("/synthetic-caregivers")
def list_synthetic_caregivers(
    department: Optional[str] = Query(default=None),
    venue: Optional[str] = Query(default=None),
    language: Optional[str] = Query(default=None),
):
    """Returns demo 'other ways to see a doctor' rows (empty unless the
    USE_SYNTHETIC_CAREGIVERS flag is on)."""
    return synthetic_caregivers(department=department, venue=venue, language=language)
