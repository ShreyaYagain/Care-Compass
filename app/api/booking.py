from typing import Any, Optional

try:
    from fastapi import APIRouter, Depends, HTTPException
except ImportError:
    class APIRouter:
        def __init__(self, *args, **kwargs):
            pass
        def get(self, *args, **kwargs):
            return lambda fn: fn
        def post(self, *args, **kwargs):
            return lambda fn: fn
    def Depends(fn):
        return None
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str = ""):
            self.status_code = status_code
            self.detail = detail

from sqlalchemy.orm import Session

from app.config import settings
from app.schemas import BookingRequest, BookingResponse
from app.db.session import get_db
from app.core.auth import get_current_user
from app.db import store

router = APIRouter(tags=["Bookings"])


def _to_booking_response(booking: dict) -> BookingResponse:
    return BookingResponse(
        booking_id=booking.get("id") or "",
        id=booking.get("id"),
        status=booking.get("status", "confirmed"),
        eta=None,
        caregiver_id=booking.get("caregiver_id", ""),
        slot="",
        user_name=booking.get("patient_name", ""),
        phone=booking.get("contact_phone", ""),
        care_type=booking.get("care_type"),
        patient_name=booking.get("patient_name"),
        relation=booking.get("relation"),
        address=booking.get("address"),
        start_time=booking.get("start_time"),
        end_time=booking.get("end_time"),
        contact_phone=booking.get("contact_phone"),
    )


@router.post("/book", response_model=BookingResponse)
def create_booking(
    request: BookingRequest,
    db: Session = Depends(get_db),
    user: Optional[str] = Depends(get_current_user),
):
    user_id = user if isinstance(user, str) else None

    # Emergency results never create a booking.
    if (request.care_type or "").lower() == "emergency_112":
        raise HTTPException(status_code=400, detail="Emergency cases are routed to 112 and cannot be booked.")

    patient_name = request.patient_name or request.user_name or "Myself"
    contact_phone = request.contact_phone or request.phone

    # Legacy/direct path (no authenticated user): return an unsaved response so
    # the existing no-auth callers keep working.
    if user_id is None:
        import uuid
        return BookingResponse(
            booking_id=f"BK_{uuid.uuid4().hex[:8].upper()}",
            status="confirmed",
            caregiver_id=request.caregiver_id,
            slot=request.slot,
            user_name=patient_name,
            phone=contact_phone,
            care_type=request.care_type,
            patient_name=patient_name,
            relation=request.relation,
            address=request.address,
        )

    start_time = request.start_time
    if not start_time:
        raise HTTPException(status_code=400, detail="start_time is required for a booking.")

    from datetime import datetime, timezone, timedelta
    try:
        start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="start_time must be an ISO-8601 timestamp.")

    if start_dt <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="start_time must be in the future.")

    end_time = request.end_time
    if not end_time:
        end_time = (start_dt + timedelta(hours=1)).isoformat()

    caregiver = store.get_caregiver(request.caregiver_id)
    if caregiver:
        free_from = str(caregiver.get("free_from") or caregiver.get("free_from_time") or "09:00")
        free_until = str(caregiver.get("free_until") or caregiver.get("free_to") or "18:00")
        hm = start_dt.strftime("%H:%M")
        if hm < free_from or hm >= free_until:
            raise HTTPException(
                status_code=400,
                detail=f"Requested time is outside the caregiver's free window ({free_from}–{free_until}).",
            )

    booking_row = {
        "user_id": user_id,
        "session_id": request.session_id,
        "caregiver_id": request.caregiver_id,
        "care_type": request.care_type,
        "patient_name": patient_name,
        "relation": request.relation,
        "contact_phone": contact_phone,
        "address": request.address,
        "start_time": start_time,
        "end_time": end_time,
        "status": "confirmed",
        "reason": request.triage_summary,
    }

    try:
        booking = store.create_booking(booking_row)
    except store.BookingConflict as e:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "That time slot is already taken.",
                "next_free_slots": e.next_slots,
            },
        )

    # Mark the session booked and append a booking step.
    if request.session_id:
        try:
            store.update_session(request.session_id, status="booked")
            store.append_step(
                request.session_id,
                store.next_step_index(request.session_id),
                "booking",
                {"caregiver_id": request.caregiver_id, "start_time": start_time, "end_time": end_time},
            )
        except Exception:
            pass

    return _to_booking_response(booking)


@router.get("/bookings/{booking_id}", response_model=BookingResponse)
def get_booking(booking_id: str, db: Session = Depends(get_db), user: Optional[str] = Depends(get_current_user)):
    user_id = user if isinstance(user, str) else None
    booking = store.get_booking(booking_id, user_id) if user_id else store.get_booking(booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return _to_booking_response(booking)
