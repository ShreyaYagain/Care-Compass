import uuid
from datetime import datetime
from app.db.session import Base

try:
    from sqlalchemy import Column, String, Float, DateTime, Text, JSON

    class Booking(Base):
        __tablename__ = "bookings"

        id = Column(String, primary_key=True, default=lambda: f"BK_{uuid.uuid4().hex[:8].upper()}")
        caregiver_id = Column(String, nullable=False)
        slot = Column(String, nullable=False)
        user_name = Column(String, nullable=False)
        phone = Column(String, nullable=False)
        triage_summary = Column(Text, nullable=True)
        status = Column(String, default="confirmed")
        eta = Column(String, default="30-45 mins")
        created_at = Column(DateTime, default=datetime.utcnow)

    class AuditLog(Base):
        __tablename__ = "audit_logs"

        id = Column(String, primary_key=True, default=lambda: f"AUD_{uuid.uuid4().hex[:10]}")
        user_input = Column(Text, nullable=False)
        language = Column(String, nullable=True)
        red_flags = Column(JSON, default=list)
        probabilities = Column(JSON, nullable=True)
        care_type = Column(String, nullable=True)
        urgency = Column(String, nullable=True)
        confidence = Column(Float, nullable=True)
        reasoning = Column(Text, nullable=True)
        created_at = Column(DateTime, default=datetime.utcnow)

except ImportError:
    class Booking:
        def __init__(self, caregiver_id, slot, user_name, phone, triage_summary=None, status="confirmed", eta="30-45 mins"):
            self.id = f"BK_{uuid.uuid4().hex[:8].upper()}"
            self.caregiver_id = caregiver_id
            self.slot = slot
            self.user_name = user_name
            self.phone = phone
            self.triage_summary = triage_summary
            self.status = status
            self.eta = eta
            self.created_at = datetime.utcnow()

    class AuditLog:
        def __init__(self, user_input, language=None, red_flags=None, probabilities=None, care_type=None, urgency=None, confidence=None, reasoning=None):
            self.id = f"AUD_{uuid.uuid4().hex[:10]}"
            self.user_input = user_input
            self.language = language
            self.red_flags = red_flags or []
            self.probabilities = probabilities
            self.care_type = care_type
            self.urgency = urgency
            self.confidence = confidence
            self.reasoning = reasoning
            self.created_at = datetime.utcnow()
