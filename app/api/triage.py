import logging
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.schemas import TriageRequest, TriageResponse
from app.db.session import get_db
from app.core.pipeline import run_triage_pipeline
from app.core.auth import get_current_user_optional
from app.db import store

router = APIRouter(tags=["Triage"])
logger = logging.getLogger(__name__)


def _log_history(request: TriageRequest, resp: TriageResponse, user_id: str) -> Optional[str]:
    """Appends chat history for an authenticated user. Never breaks triage."""
    try:
        session_id = request.session_id
        if session_id and not store.get_session(session_id, user_id):
            session_id = None
        if not session_id:
            created = store.create_session(
                user_id,
                language=request.language,
                input_mode=request.input_mode or "text",
                first_message=request.user_input,
            )
            session_id = created["id"] if created else None
        if not session_id:
            return None

        # The current input is an answer if the previous message was a question.
        kind = "user_message"
        if request.conversation_history:
            last = request.conversation_history[-1]
            if getattr(last, "role", None) == "assistant":
                kind = "user_answer"
        store.append_step(session_id, store.next_step_index(session_id), kind, {"text": request.user_input})

        if resp.follow_up_question:
            store.append_step(
                session_id,
                store.next_step_index(session_id),
                "follow_up_question",
                {"question": resp.follow_up_question, "options": resp.follow_up_options},
            )
            store.update_session(session_id, status="needs_info")
            return session_id

        if resp.care_type:
            store.append_step(session_id, store.next_step_index(session_id), "result", {
                "care_type": resp.care_type,
                "urgency": resp.urgency,
                "reasoning": resp.reasoning,
                "confidence": resp.confidence,
            })
            if resp.care_type == "emergency_112":
                store.append_step(session_id, store.next_step_index(session_id), "emergency", {
                    "red_flags": resp.red_flags,
                    "steps": resp.emergency_steps,
                })
                store.update_session(session_id, care_type=resp.care_type, urgency=resp.urgency,
                                     emergency=True, red_flags=resp.red_flags,
                                     reasoning=resp.reasoning, status="emergency")
            else:
                if resp.matched_caregivers:
                    store.append_step(session_id, store.next_step_index(session_id), "caregivers", {
                        "caregivers": [
                            {"id": c.caregiver_id, "name": c.name, "reason": c.reason}
                            for c in resp.matched_caregivers
                        ],
                    })
                store.update_session(session_id, care_type=resp.care_type, urgency=resp.urgency,
                                     emergency=False, red_flags=resp.red_flags,
                                     reasoning=resp.reasoning, status="resolved")
        return session_id
    except Exception as e:
        logger.warning(f"History logging failed (triage unaffected): {e}")
        return None


@router.post("/triage", response_model=TriageResponse)
def triage_endpoint(
    request: TriageRequest,
    debug: bool = False,
    db: Session = Depends(get_db),
    user: Optional[str] = Depends(get_current_user_optional),
):
    resp = run_triage_pipeline(request, db=db, debug=debug)

    user_id = user if isinstance(user, str) else None
    if user_id:
        session_id = _log_history(request, resp, user_id)
        if session_id:
            resp.session_id = session_id

    return resp
