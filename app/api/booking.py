from typing import Any

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

try:
    from sqlalchemy.orm import Session
except ImportError:
    Session = Any

from app.schemas import BookingRequest, BookingResponse
from app.db.session import get_db
from app.db.models import Booking

router = APIRouter(tags=["Bookings"])


@router.post("/book", response_model=BookingResponse)
def create_booking(request: BookingRequest, db: Session = Depends(get_db)):
    booking = Booking(
        caregiver_id=request.caregiver_id,
        slot=request.slot,
        user_name=request.user_name,
        phone=request.phone,
        triage_summary=request.triage_summary,
        status="confirmed",
        eta="30-45 mins",
    )
    if db:
        try:
            db.add(booking)
            db.commit()
            db.refresh(booking)
        except Exception:
            pass

    return BookingResponse(
        booking_id=booking.id,
        status=booking.status,
        eta=booking.eta,
        caregiver_id=booking.caregiver_id,
        slot=booking.slot,
        user_name=booking.user_name,
        phone=booking.phone,
    )


@router.get("/bookings/{booking_id}", response_model=BookingResponse)
def get_booking(booking_id: str, db: Session = Depends(get_db)):
    if not db:
        raise HTTPException(status_code=404, detail="Database not available")
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    return BookingResponse(
        booking_id=booking.id,
        status=booking.status,
        eta=booking.eta,
        caregiver_id=booking.caregiver_id,
        slot=booking.slot,
        user_name=booking.user_name,
        phone=booking.phone,
    )
