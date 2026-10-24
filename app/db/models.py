import uuid
from datetime import datetime
from app.db.session import Base

try:
    from sqlalchemy import (
        Column,
        String,
        Float,
        DateTime,
        Text,
        JSON,
        Boolean,
        Integer,
        ForeignKey,
        UniqueConstraint,
    )

    def _uuid() -> str:
        return str(uuid.uuid4())

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
        debug_trace = Column(JSON, nullable=True)
        created_at = Column(DateTime, default=datetime.utcnow)

    class ChatSession(Base):
        __tablename__ = "chat_sessions"

        id = Column(String, primary_key=True, default=_uuid)
        user_id = Column(String, nullable=False, index=True)
        language = Column(String, nullable=True)
        first_message = Column(Text, nullable=True)
        input_mode = Column(String, nullable=True, default="text")
        care_type = Column(String, nullable=True)
        urgency = Column(String, nullable=True)
        emergency = Column(Boolean, default=False)
        red_flags = Column(JSON, default=list)
        reasoning = Column(Text, nullable=True)
        status = Column(String, default="needs_info")
        created_at = Column(DateTime, default=datetime.utcnow)
        updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class ChatStep(Base):
        __tablename__ = "chat_steps"
        __table_args__ = (UniqueConstraint("session_id", "step_index", name="uq_chat_step"),)

        id = Column(String, primary_key=True, default=_uuid)
        session_id = Column(String, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
        step_index = Column(Integer, nullable=False)
        kind = Column(String, nullable=False)
        payload = Column(JSON, default=dict)
        created_at = Column(DateTime, default=datetime.utcnow)

    class Booking(Base):
        __tablename__ = "bookings"

        id = Column(String, primary_key=True, default=_uuid)
        user_id = Column(String, nullable=False, index=True)
        session_id = Column(String, ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True)
        caregiver_id = Column(String, nullable=False)
        care_type = Column(String, nullable=True)
        patient_name = Column(String, nullable=False, default="Myself")
        relation = Column(String, nullable=True)
        contact_phone = Column(String, nullable=True)
        address = Column(String, nullable=True)
        start_time = Column(DateTime, nullable=False)
        end_time = Column(DateTime, nullable=False)
        status = Column(String, default="confirmed")
        reason = Column(Text, nullable=True)
        created_at = Column(DateTime, default=datetime.utcnow)
        cancelled_at = Column(DateTime, nullable=True)

except ImportError:
    # Minimal fallbacks for environments without sqlalchemy.
    class AuditLog:  # type: ignore
        pass

    class ChatSession:  # type: ignore
        pass

    class ChatStep:  # type: ignore
        pass

    class Booking:  # type: ignore
        pass
