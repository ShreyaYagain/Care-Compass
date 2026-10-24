"""Supabase booking tests (via the SQLite fallback)."""
import unittest
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.schemas import BookingRequest
from app.api.booking import create_booking
from app.api.bookings import list_bookings, cancel_booking
from app.db import store


def _future_start(hour: int = 14) -> str:
    d = datetime.now(timezone.utc) + timedelta(days=1)
    return d.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


class TestSupabaseBookings(unittest.TestCase):

    def test_create_and_list_booking(self):
        start = _future_start(14)
        req = BookingRequest(
            caregiver_id="CG_001",
            care_type="teleconsultation",
            start_time=start,
            patient_name="Rohan Gupta",
            contact_phone="+919876543210",
        )
        resp = create_booking(req, db=None, user="user-1")
        self.assertEqual(resp.status, "confirmed")
        self.assertTrue(resp.booking_id)

        bookings = list_bookings(status="upcoming", user="user-1")
        self.assertEqual(len(bookings), 1)
        self.assertEqual(bookings[0].patient_name, "Rohan Gupta")
        self.assertEqual(bookings[0].caregiver["name"], "Mohit Gupta")

    def test_double_booking_returns_409(self):
        start = _future_start(15)
        req = BookingRequest(caregiver_id="CG_001", care_type="teleconsultation", start_time=start, patient_name="A")
        create_booking(req, db=None, user="user-1")

        req2 = BookingRequest(caregiver_id="CG_001", care_type="teleconsultation", start_time=start, patient_name="B")
        with self.assertRaises(HTTPException) as ctx:
            create_booking(req2, db=None, user="user-1")
        self.assertEqual(ctx.exception.status_code, 409)

    def test_emergency_booking_rejected(self):
        req = BookingRequest(caregiver_id="CG_001", care_type="emergency_112", start_time=_future_start(14))
        with self.assertRaises(HTTPException) as ctx:
            create_booking(req, db=None, user="user-1")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_past_booking_rejected(self):
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        req = BookingRequest(caregiver_id="CG_001", care_type="teleconsultation", start_time=past)
        with self.assertRaises(HTTPException) as ctx:
            create_booking(req, db=None, user="user-1")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_cancel_owner_only(self):
        start = _future_start(16)
        req = BookingRequest(caregiver_id="CG_001", care_type="teleconsultation", start_time=start, patient_name="A")
        resp = create_booking(req, db=None, user="user-1")

        with self.assertRaises(HTTPException) as ctx:
            cancel_booking(resp.booking_id, user="user-2")
        self.assertEqual(ctx.exception.status_code, 404)

        result = cancel_booking(resp.booking_id, user="user-1")
        self.assertEqual(result["status"], "cancelled")

    def test_default_patient_name_myself(self):
        req = BookingRequest(caregiver_id="CG_001", care_type="teleconsultation", start_time=_future_start(14))
        resp = create_booking(req, db=None, user="user-1")
        self.assertEqual(resp.patient_name, "Myself")

    def test_post_book_endpoint_roundtrip(self):
        """End-to-end: POST /book, then GET /bookings returns the booking."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        start = _future_start(14)
        post = client.post(
            "/book",
            json={
                "caregiver_id": "CG_021",
                "care_type": "teleconsultation",
                "patient_name": "Rohan",
                "user_name": "Rohan",
                "phone": "9876543210",
                "start_time": start,
            },
            headers={"X-Device-Id": "test-device-booking"},
        )
        self.assertEqual(post.status_code, 200, post.text)
        booking_id = post.json().get("booking_id")
        self.assertIsNotNone(booking_id)

        bookings = client.get("/bookings?status=all", headers={"X-Device-Id": "test-device-booking"}).json()
        self.assertTrue(any(b["id"] == booking_id for b in bookings), "POST /book must appear in GET /bookings")
        self.assertTrue(any(b["service"] for b in bookings if b["id"] == booking_id))


if __name__ == "__main__":
    unittest.main()
