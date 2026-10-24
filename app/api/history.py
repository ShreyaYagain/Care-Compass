from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import get_current_user
from app.db import store
from app.schemas import HistorySessionItem, HistoryDetailResponse, HistoryStepItem

router = APIRouter(tags=["History"])


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
            HistoryStepItem(
                step_index=st["step_index"],
                kind=st["kind"],
                payload=st.get("payload", {}),
                created_at=st.get("created_at"),
            )
            for st in session.get("steps", [])
        ],
        booking=session.get("booking"),
    )


@router.delete("/history/{session_id}", status_code=204)
def delete_history(session_id: str, user: str = Depends(get_current_user)):
    deleted = store.delete_session(session_id, user)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return None
