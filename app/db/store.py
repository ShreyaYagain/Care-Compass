"""Storage abstraction for chat history and bookings.

Backends:
  - Supabase (Postgres + Auth) when SUPABASE_URL + service-role key are set.
  - SQLite (existing SQLAlchemy store) otherwise, so tests and the no-key demo run.

Every user-scoped query filters by user_id itself (the service role bypasses RLS).
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.config import settings
from app.db.supabase_client import get_supabase, supabase_available

logger = logging.getLogger(__name__)


class BookingConflict(Exception):
    def __init__(self, next_slots: list[str]):
        self.next_slots = next_slots
        super().__init__("Slot already taken")


# ---------------------------------------------------------------------------
# PII masking for stored free text
# ---------------------------------------------------------------------------

_PHONE_RE = re.compile(r"(?:\+?91[\s-]?)?[6-9]\d{9}\b|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def mask_pii(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    t = _PHONE_RE.sub("[PHONE]", text)
    t = _EMAIL_RE.sub("[EMAIL]", t)
    return t


def _iso(dt: Any) -> Optional[str]:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return str(dt)


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        s = value.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _naive_utc(dt: Any) -> Optional[datetime]:
    """Convert to a naive UTC datetime for SQLite storage/comparison."""
    dt = _parse_dt(dt) if isinstance(dt, str) else dt
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


# ---------------------------------------------------------------------------
# Supabase backend
# ---------------------------------------------------------------------------

def _sb() -> Any:
    return get_supabase()


def _sb_exec(coro_fn, *args, **kwargs):
    return coro_fn(*args, **kwargs).execute()


def _sb_data(resp: Any) -> list[dict]:
    try:
        data = getattr(resp, "data", None) or []
        return list(data) if isinstance(data, list) else [data]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Chat sessions
# ---------------------------------------------------------------------------

def create_session(user_id: str, language: Optional[str] = None,
                   input_mode: Optional[str] = None,
                   first_message: Optional[str] = None) -> Optional[dict]:
    row = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "language": language,
        "input_mode": input_mode or "text",
        "first_message": mask_pii(first_message),
        "status": "needs_info",
    }
    if supabase_available():
        try:
            resp = _sb().table("chat_sessions").insert(row).execute()
            return _sb_data(resp)[0] if _sb_data(resp) else row
        except Exception as e:
            logger.warning(f"Supabase create_session failed: {e}")
    return _sqlite_create_session(row)


def _sqlite_create_session(row: dict) -> Optional[dict]:
    try:
        from app.db.session import SessionLocal
        from app.db.models import ChatSession
        s = ChatSession(**row)
        db = SessionLocal()
        try:
            db.add(s)
            db.commit()
            return _sqlite_session_dict(s)
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"SQLite create_session failed: {e}")
    return None


def _sqlite_session_dict(s) -> dict:
    return {
        "id": s.id,
        "user_id": s.user_id,
        "language": s.language,
        "first_message": s.first_message,
        "input_mode": s.input_mode,
        "care_type": s.care_type,
        "urgency": s.urgency,
        "emergency": bool(s.emergency),
        "red_flags": s.red_flags or [],
        "reasoning": s.reasoning,
        "status": s.status,
        "created_at": _iso(s.created_at),
        "updated_at": _iso(s.updated_at),
    }


def update_session(session_id: str, **fields: Any) -> None:
    allowed = {"language", "first_message", "input_mode", "care_type", "urgency",
               "emergency", "red_flags", "reasoning", "status"}
    fields = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not fields:
        return
    if supabase_available():
        try:
            _sb().table("chat_sessions").update(fields).eq("id", session_id).execute()
        except Exception as e:
            logger.warning(f"Supabase update_session failed: {e}")
        return
    try:
        from app.db.session import SessionLocal
        from app.db.models import ChatSession
        db = SessionLocal()
        try:
            db.query(ChatSession).filter(ChatSession.id == session_id).update(fields)
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"SQLite update_session failed: {e}")


def append_step(session_id: str, step_index: int, kind: str, payload: dict) -> None:
    payload = _mask_payload(payload)
    row = {"id": str(uuid.uuid4()), "session_id": session_id,
           "step_index": step_index, "kind": kind, "payload": payload}
    if supabase_available():
        try:
            _sb().table("chat_steps").insert(row).execute()
        except Exception as e:
            logger.warning(f"Supabase append_step failed: {e}")
        return
    try:
        from app.db.session import SessionLocal
        from app.db.models import ChatStep
        db = SessionLocal()
        try:
            db.add(ChatStep(**row))
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"SQLite append_step failed: {e}")


def _mask_payload(payload: dict) -> dict:
    """Mask PII in stored step payloads (never mutate the original)."""
    masked: dict = {}
    for k, v in (payload or {}).items():
        if isinstance(v, str) and k not in ("care_type", "urgency", "kind", "step_index"):
            masked[k] = mask_pii(v)
        elif isinstance(v, list):
            masked[k] = [mask_pii(x) if isinstance(x, str) else x for x in v]
        else:
            masked[k] = v
    return masked


def next_step_index(session_id: str) -> int:
    if supabase_available():
        try:
            resp = _sb().table("chat_steps").select("step_index") \
                .eq("session_id", session_id).order("step_index", desc=True).limit(1).execute()
            rows = _sb_data(resp)
            return int(rows[0]["step_index"]) + 1 if rows else 0
        except Exception:
            return 0
    try:
        from app.db.session import SessionLocal
        from app.db.models import ChatStep
        db = SessionLocal()
        try:
            last = (db.query(ChatStep).filter(ChatStep.session_id == session_id)
                    .order_by(ChatStep.step_index.desc()).first())
            return (last.step_index + 1) if last else 0
        finally:
            db.close()
    except Exception:
        return 0


def get_session(session_id: str, user_id: str) -> Optional[dict]:
    if supabase_available():
        try:
            resp = _sb().table("chat_sessions").select("*").eq("id", session_id).eq("user_id", user_id).execute()
            rows = _sb_data(resp)
            if not rows:
                return None
            session = rows[0]
            steps_resp = _sb().table("chat_steps").select("*").eq("session_id", session_id) \
                .order("step_index", desc=False).execute()
            session["steps"] = [
                {"step_index": s["step_index"], "kind": s["kind"],
                 "payload": s.get("payload", {}), "created_at": _iso(s.get("created_at"))}
                for s in _sb_data(steps_resp)
            ]
            booking_resp = _sb().table("bookings").select("*").eq("session_id", session_id).execute()
            session["booking"] = _sb_data(booking_resp)[0] if _sb_data(booking_resp) else None
            return _normalise_session(session)
        except Exception as e:
            logger.warning(f"Supabase get_session failed: {e}")
    return _sqlite_get_session(session_id, user_id)


def _normalise_session(s: dict) -> dict:
    s["created_at"] = _iso(s.get("created_at"))
    s["updated_at"] = _iso(s.get("updated_at"))
    s["emergency"] = bool(s.get("emergency", False))
    s["red_flags"] = s.get("red_flags", []) or []
    return s


def _sqlite_get_session(session_id: str, user_id: str) -> Optional[dict]:
    try:
        from app.db.session import SessionLocal
        from app.db.models import ChatSession, ChatStep, Booking
        db = SessionLocal()
        try:
            s = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == user_id).first()
            if not s:
                return None
            session = _sqlite_session_dict(s)
            steps = (db.query(ChatStep).filter(ChatStep.session_id == session_id)
                     .order_by(ChatStep.step_index.asc()).all())
            session["steps"] = [
                {"step_index": st.step_index, "kind": st.kind,
                 "payload": st.payload or {}, "created_at": _iso(st.created_at)}
                for st in steps
            ]
            b = db.query(Booking).filter(Booking.session_id == session_id).first()
            session["booking"] = _sqlite_booking_dict(b) if b else None
            return session
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"SQLite get_session failed: {e}")
    return None


def list_sessions(user_id: str, limit: int = 5) -> list[dict]:
    if supabase_available():
        try:
            resp = _sb().table("chat_sessions").select("*").eq("user_id", user_id) \
                .order("created_at", desc=True).limit(limit).execute()
            return [_normalise_session(s) for s in _sb_data(resp)]
        except Exception as e:
            logger.warning(f"Supabase list_sessions failed: {e}")
    try:
        from app.db.session import SessionLocal
        from app.db.models import ChatSession
        db = SessionLocal()
        try:
            rows = (db.query(ChatSession).filter(ChatSession.user_id == user_id)
                    .order_by(ChatSession.created_at.desc()).limit(limit).all())
            return [_sqlite_session_dict(s) for s in rows]
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"SQLite list_sessions failed: {e}")
    return []


def delete_session(session_id: str, user_id: str) -> bool:
    if supabase_available():
        try:
            # Steps cascade; null out bookings session_id first.
            _sb().table("bookings").update({"session_id": None}).eq("session_id", session_id).execute()
            resp = _sb().table("chat_sessions").delete().eq("id", session_id).eq("user_id", user_id).execute()
            return bool(_sb_data(resp))
        except Exception as e:
            logger.warning(f"Supabase delete_session failed: {e}")
            return False
    try:
        from app.db.session import SessionLocal
        from app.db.models import ChatSession, Booking
        db = SessionLocal()
        try:
            db.query(Booking).filter(Booking.session_id == session_id).update({"session_id": None})
            n = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == user_id).delete()
            db.commit()
            return n > 0
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"SQLite delete_session failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Caregivers
# ---------------------------------------------------------------------------

def list_caregivers() -> list[dict]:
    if supabase_available():
        try:
            resp = _sb().table("caregivers").select("*").execute()
            return _sb_data(resp)
        except Exception as e:
            logger.warning(f"Supabase list_caregivers failed: {e}")
    # Fall back to the in-memory official roster.
    from app.core.matching import load_caregivers
    return load_caregivers()


def get_caregiver(caregiver_id: str) -> Optional[dict]:
    if supabase_available():
        try:
            resp = _sb().table("caregivers").select("*").eq("id", caregiver_id).execute()
            rows = _sb_data(resp)
            return rows[0] if rows else None
        except Exception as e:
            logger.warning(f"Supabase get_caregiver failed: {e}")
    from app.core.matching import load_caregivers
    for cg in load_caregivers():
        if cg.get("caregiver_id") == caregiver_id or cg.get("id") == caregiver_id:
            return cg
    return None


def _free_window(cg: dict) -> tuple[str, str]:
    free_from = str(cg.get("free_from") or cg.get("free_from_time") or "09:00")
    free_until = str(cg.get("free_until") or cg.get("free_to") or "18:00")
    return free_from, free_until


def _slots_between(free_from: str, free_until: str) -> list[str]:
    """1-hour slots on the hour inside the window, ending at free_until."""
    slots = []
    try:
        start = datetime.strptime(free_from, "%H:%M")
        end = datetime.strptime(free_until, "%H:%M")
    except Exception:
        return slots
    if end <= start:
        end += timedelta(days=1)
    cur = start
    while cur < end:
        slots.append(cur.strftime("%H:%M"))
        cur += timedelta(hours=1)
    return slots


def get_caregiver_slots(caregiver_id: str, date_str: str) -> list[str]:
    cg = get_caregiver(caregiver_id)
    if not cg:
        return []
    free_from, free_until = _free_window(cg)
    slots = _slots_between(free_from, free_until)

    day = _parse_dt(f"{date_str}T00:00:00Z")
    if day is None:
        return []
    day_start = day.replace(tzinfo=timezone.utc)
    booked_start_times: set[str] = set()
    if supabase_available():
        try:
            resp = _sb().table("bookings").select("start_time") \
                .eq("caregiver_id", caregiver_id).in_("status", ["confirmed", "pending"]).execute()
            for b in _sb_data(resp):
                bt = _parse_dt(b.get("start_time"))
                if bt and bt.date() == day_start.date():
                    booked_start_times.add(bt.strftime("%H:%M"))
        except Exception:
            pass
    else:
        try:
            from app.db.session import SessionLocal
            from app.db.models import Booking
            db = SessionLocal()
            try:
                rows = (db.query(Booking).filter(Booking.caregiver_id == caregiver_id,
                                                 Booking.status.in_(["confirmed", "pending"])).all())
                for b in rows:
                    if b.start_time and b.start_time.date() == day_start.date():
                        booked_start_times.add(b.start_time.strftime("%H:%M"))
            finally:
                db.close()
        except Exception:
            pass

    return [s for s in slots if s not in booked_start_times]


# ---------------------------------------------------------------------------
# Bookings
# ---------------------------------------------------------------------------

def _booked_start_times(caregiver_id: str, start_dt: Optional[datetime] = None) -> set[str]:
    times: set[str] = set()
    if supabase_available():
        try:
            resp = _sb().table("bookings").select("start_time") \
                .eq("caregiver_id", caregiver_id).in_("status", ["confirmed", "pending"]).execute()
            for b in _sb_data(resp):
                bt = _parse_dt(b.get("start_time"))
                if bt:
                    times.add(bt.isoformat())
        except Exception:
            pass
    else:
        try:
            from app.db.session import SessionLocal
            from app.db.models import Booking
            db = SessionLocal()
            try:
                rows = (db.query(Booking).filter(Booking.caregiver_id == caregiver_id,
                                                 Booking.status.in_(["confirmed", "pending"])).all())
                for b in rows:
                    if b.start_time:
                        times.add(_iso(b.start_time))
            finally:
                db.close()
        except Exception:
            pass
    return times


def _sqlite_booking_dict(b) -> dict:
    return {
        "id": b.id,
        "user_id": b.user_id,
        "session_id": b.session_id,
        "caregiver_id": b.caregiver_id,
        "care_type": b.care_type,
        "patient_name": b.patient_name,
        "relation": b.relation,
        "contact_phone": b.contact_phone,
        "address": b.address,
        "start_time": _iso(b.start_time),
        "end_time": _iso(b.end_time),
        "status": b.status,
        "reason": b.reason,
        "created_at": _iso(b.created_at),
        "cancelled_at": _iso(b.cancelled_at),
    }


def create_booking(booking: dict) -> dict:
    """Inserts a booking. Raises BookingConflict if the slot is taken."""
    booking["id"] = booking.get("id") or str(uuid.uuid4())
    if supabase_available():
        try:
            resp = _sb().table("bookings").insert(booking).execute()
            rows = _sb_data(resp)
            return rows[0] if rows else booking
        except Exception as e:
            if "23505" in str(e) or "duplicate" in str(e).lower():
                raise BookingConflict(get_caregiver_slots(booking.get("caregiver_id", ""), _iso(booking.get("start_time"))[:10]))
            logger.warning(f"Supabase create_booking failed: {e}")
            raise
    # SQLite path with manual double-booking check.
    try:
        from app.db.session import SessionLocal
        from app.db.models import Booking
        db = SessionLocal()
        try:
            start_dt = _naive_utc(booking.get("start_time"))
            existing = (db.query(Booking).filter(
                Booking.caregiver_id == booking["caregiver_id"],
                Booking.start_time == start_dt,
                Booking.status.in_(["confirmed", "pending"]),
            ).first())
            if existing:
                day = start_dt.date() if start_dt else datetime.utcnow().date()
                raise BookingConflict(get_caregiver_slots(booking["caregiver_id"], str(day)))
            b = Booking()
            for k, v in booking.items():
                if k == "id":
                    b.id = v
                elif k in ("start_time", "end_time", "cancelled_at"):
                    setattr(b, k, _naive_utc(v))
                elif hasattr(b, k):
                    setattr(b, k, v)
            db.add(b)
            db.commit()
            return _sqlite_booking_dict(b)
        finally:
            db.close()
    except BookingConflict:
        raise
    except Exception as e:
        logger.warning(f"SQLite create_booking failed: {e}")
        raise


def get_booking(booking_id: str, user_id: Optional[str] = None) -> Optional[dict]:
    if supabase_available():
        try:
            q = _sb().table("bookings").select("*").eq("id", booking_id)
            if user_id:
                q = q.eq("user_id", user_id)
            resp = q.execute()
            rows = _sb_data(resp)
            return rows[0] if rows else None
        except Exception as e:
            logger.warning(f"Supabase get_booking failed: {e}")
    try:
        from app.db.session import SessionLocal
        from app.db.models import Booking
        db = SessionLocal()
        try:
            q = db.query(Booking).filter(Booking.id == booking_id)
            if user_id:
                q = q.filter(Booking.user_id == user_id)
            b = q.first()
            return _sqlite_booking_dict(b) if b else None
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"SQLite get_booking failed: {e}")
    return None


def list_bookings(user_id: str, status: str = "all") -> list[dict]:
    if supabase_available():
        try:
            q = _sb().table("bookings").select("*").eq("user_id", user_id)
            now = _now().isoformat()
            if status == "upcoming":
                q = q.in_("status", ["confirmed", "pending"]).gte("start_time", now)
            elif status == "past":
                q = q.in_("status", ["completed", "cancelled"])
            q = q.order("start_time", desc=False)
            resp = q.execute()
            return list(_sb_data(resp))
        except Exception as e:
            logger.warning(f"Supabase list_bookings failed: {e}")
    try:
        from app.db.session import SessionLocal
        from app.db.models import Booking
        db = SessionLocal()
        try:
            q = db.query(Booking).filter(Booking.user_id == user_id)
            now = datetime.utcnow()
            if status == "upcoming":
                q = q.filter(Booking.status.in_(["confirmed", "pending"]), Booking.start_time >= now)
            elif status == "past":
                q = q.filter(Booking.status.in_(["completed", "cancelled"]))
            q = q.order_by(Booking.start_time.asc())
            return [_sqlite_booking_dict(b) for b in q.all()]
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"SQLite list_bookings failed: {e}")
    return []


def _update_booking(booking_id: str, user_id: str, fields: dict) -> Optional[dict]:
    if supabase_available():
        try:
            resp = _sb().table("bookings").update(fields).eq("id", booking_id).eq("user_id", user_id).execute()
            rows = _sb_data(resp)
            return rows[0] if rows else None
        except Exception as e:
            logger.warning(f"Supabase update booking failed: {e}")
            return None
    try:
        from app.db.session import SessionLocal
        from app.db.models import Booking
        db = SessionLocal()
        try:
            sql_fields = dict(fields)
            for k in ("start_time", "end_time", "cancelled_at"):
                if k in sql_fields:
                    sql_fields[k] = _naive_utc(sql_fields[k])
            n = db.query(Booking).filter(Booking.id == booking_id, Booking.user_id == user_id).update(sql_fields)
            db.commit()
            if n:
                b = db.query(Booking).filter(Booking.id == booking_id).first()
                return _sqlite_booking_dict(b)
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"SQLite update booking failed: {e}")
    return None


def cancel_booking(booking_id: str, user_id: str) -> Optional[dict]:
    booking = get_booking(booking_id, user_id)
    if not booking or booking["status"] != "confirmed":
        return None
    start = _parse_dt(booking["start_time"])
    if start and start <= _now():
        return None
    return _update_booking(booking_id, user_id, {"status": "cancelled", "cancelled_at": _now().isoformat()})


def reschedule_booking(booking_id: str, user_id: str, start_time: str, end_time: str) -> Optional[dict]:
    booking = get_booking(booking_id, user_id)
    if not booking:
        return None
    return _update_booking(booking_id, user_id, {"start_time": start_time, "end_time": end_time, "status": "confirmed"})

