from fastapi import APIRouter
from app.schemas import CaregiverProfile, MatchRequest, MatchedCaregiver
from app.core.matching import load_caregivers, rank_caregivers

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
