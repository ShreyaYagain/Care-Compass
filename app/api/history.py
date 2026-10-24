from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import get_current_user
from app.db import store
from app.schemas import HistorySessionItem, HistoryDetailResponse, HistoryStepItem

router = APIRouter(tags=["History"])

_CARE_TYPE_SERVICE = {
    "home_nursing": "Home nursing",
    "paramedic_home_visit": "Medic home visit",
    "lab_test_home": "Lab test at home",
    "teleconsultation": "Teleconsultation",
    "emergency_112": "Emergency (112)",
}


def _outcome(session: dict) -> str:
    if session.get("emergency"):
        return "emergency"
    if session.get("status") == "needs_info":
        return "needs_info"
    if session.get("urgency") == "same_day":
        return "same_day"
    return "scheduled"


def _android_steps(steps: list[dict], input_mode: str | None) -> list[dict]:
    """Flatten stored (kind, payload) steps into the Android-friendly shape."""
    result: list[dict] = []
    for s in steps:
        kind = s.get("kind", "")
        payload = s.get("payload") or {}
        base = {
            "step_index": s.get("step_index"),
            "kind": kind,
            "payload": payload,
            "created_at": s.get("created_at"),
        }

        if kind == "follow_up_question":
            result.append(dict(base, type="follow_up", title=payload.get("question", "")))
        elif kind in ("user_message", "user_answer"):
            result.append(dict(base, type="user_said", subtitle=payload.get("text", ""),
                               is_voice=input_mode == "voice"))
        elif kind == "result":
            result.append(dict(base, type="result",
                               care_type=payload.get("care_type"),
                               urgency=payload.get("urgency"),
                               reasoning=payload.get("reasoning")))
        elif kind == "emergency":
            steps_list = payload.get("steps") or []
            result.append(dict(base, type="emergency_alert",
                               emergency_text="\n".join(steps_list) if steps_list else payload.get("text", "")))
        elif kind == "caregivers":
            cgs = payload.get("caregivers") or []
            names = [c.get("name") for c in cgs if c.get("name")]
            result.append(dict(base, type="caregivers",
                               suggested_caregivers=names,
                               chosen_caregiver=names[0] if names else None))
        else:
            result.append(dict(base, type="user_said", subtitle=str(payload) if payload else ""))
    return result


@router.get("/history", response_model=list[HistorySessionItem])
def list_history(
    limit: int = Query(default=5, ge=1, le=20),
    user: str = Depends(get_current_user),
):
    sessions = store.list_sessions(user, limit=limit)
    return [
        HistorySessionItem(
            id=s["id"],
            first_message=s.get("first_message"),
            care_type=s.get("care_type"),
            urgency=s.get("urgency"),
            emergency=bool(s.get("emergency", False)),
            status=s.get("status"),
            created_at=s.get("created_at"),
            outcome=_outcome(s),
            via_voice=s.get("input_mode") == "voice",
        )
        for s in sessions
    ]


@router.get("/history/{session_id}", response_model=HistoryDetailResponse)
def get_history(session_id: str, user: str = Depends(get_current_user)):
    session = store.get_session(session_id, user)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return HistoryDetailResponse(
        id=session["id"],
        first_message=session.get("first_message"),
        language=session.get("language"),
        input_mode=session.get("input_mode"),
        care_type=session.get("care_type"),
        urgency=session.get("urgency"),
        emergency=bool(session.get("emergency", False)),
        red_flags=session.get("red_flags", []),
        reasoning=session.get("reasoning"),
        status=session.get("status"),
        created_at=session.get("created_at"),
        updated_at=session.get("updated_at"),
        steps=[
            HistoryStepItem(**st)
            for st in _android_steps(session.get("steps", []), session.get("input_mode"))
        ],
        booking=session.get("booking"),
    )


@router.delete("/history/{session_id}", status_code=204)
def delete_history(session_id: str, user: str = Depends(get_current_user)):
    deleted = store.delete_session(session_id, user)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return None
