from fastapi import APIRouter, Depends, Query

from app.schemas import CaregiverProfile, MatchRequest, MatchedCaregiver
from app.core.matching import load_caregivers, rank_caregivers
from app.core.auth import get_current_user
from app.db import store

router = APIRouter(tags=["Caregivers & Matching"])


@router.get("/caregivers", response_model=list[CaregiverProfile])
def list_caregivers():
    return load_caregivers()


@router.post("/match", response_model=list[MatchedCaregiver])
def match_caregivers_endpoint(request: MatchRequest):
    return rank_caregivers(
        care_type=request.care_type,
        urgency=request.urgency,
        user_location=request.location,
        user_language=request.language,
        time_pref=request.time_pref,
        limit=5,
    )


@router.get("/caregivers/{caregiver_id}/slots")
def caregiver_slots(
    caregiver_id: str,
    date: str = Query(...),
    user: str = Depends(get_current_user),
):
    slots = store.get_caregiver_slots(caregiver_id, date)
    return {"caregiver_id": caregiver_id, "date": date, "slots": slots}
