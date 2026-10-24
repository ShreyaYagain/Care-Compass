from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.auth import get_current_user
from app.db import store
from app.schemas import BookingItem

router = APIRouter(tags=["Bookings"])


class RescheduleRequest(BaseModel):
    start_time: str
    end_time: Optional[str] = None


def _with_caregiver(booking: dict) -> dict:
    cg = store.get_caregiver(booking.get("caregiver_id", ""))
    booking["caregiver"] = {
        "name": cg.get("name") if cg else None,
        "role": cg.get("role") if cg else None,
        "qualification": cg.get("qualification") if cg else None,
        "phone": cg.get("phone") if cg else None,
    }
    return booking


@router.get("/bookings", response_model=list[BookingItem])
def list_bookings(
    status: str = Query(default="upcoming"),
    user: str = Depends(get_current_user),
):
    if status not in ("upcoming", "past", "all"):
        raise HTTPException(status_code=400, detail="status must be 'upcoming', 'past' or 'all'")
    bookings = store.list_bookings(user, status=status)
    items = []
    for b in bookings:
        b = _with_caregiver(b)
        items.append(BookingItem(
            id=b.get("id"),
            care_type=b.get("care_type"),
            patient_name=b.get("patient_name"),
            relation=b.get("relation"),
            caregiver=b.get("caregiver"),
            start_time=b.get("start_time"),
            end_time=b.get("end_time"),
            address=b.get("address"),
            status=b.get("status"),
            reason=b.get("reason"),
        ))
    return items


@router.post("/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: str, user: str = Depends(get_current_user)):
    booking = store.cancel_booking(booking_id, user)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found or cannot be cancelled")
    return _with_caregiver(booking)


@router.post("/bookings/{booking_id}/reschedule")
def reschedule_booking(booking_id: str, payload: RescheduleRequest, user: str = Depends(get_current_user)):
    from datetime import datetime, timezone, timedelta
    try:
        start_dt = datetime.fromisoformat(payload.start_time.replace("Z", "+00:00"))
    except Exception:
        raise HTTPException(status_code=400, detail="start_time must be an ISO-8601 timestamp.")

    if start_dt <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="start_time must be in the future.")

    end_time = payload.end_time or (start_dt + timedelta(hours=1)).isoformat()

    existing = store.get_booking(booking_id, user)
    if not existing:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Double-booking check (same caregiver, same start).
    if existing.get("start_time") != payload.start_time:
        taken = store._booked_start_times(existing.get("caregiver_id", ""))
        new_start_iso = store._iso(start_dt)
        if new_start_iso in taken:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "That time slot is already taken.",
                    "next_free_slots": store.get_caregiver_slots(
                        existing.get("caregiver_id", ""), start_dt.date().isoformat()
                    ),
                },
            )

    booking = store.reschedule_booking(booking_id, user, payload.start_time, end_time)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return _with_caregiver(booking)
