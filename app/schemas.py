from typing import Any, Optional

try:
    from pydantic import BaseModel, Field, model_validator, field_validator, ConfigDict
except ImportError:
    # Lightweight fallback for environments where pydantic is not yet installed
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
            # Ensure defaults for defined attributes
            for k, v in self.__class__.__dict__.items():
                if not k.startswith("__") and not callable(v) and k not in kwargs:
                    setattr(self, k, v)

        def model_dump(self):
            return self.__dict__

        def dict(self):
            return self.__dict__

    def Field(default=None, default_factory=None, description=""):
        if default_factory is not None:
            return default_factory()
        return default

    def model_validator(*args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    def field_validator(*args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    def ConfigDict(**kwargs):
        return kwargs


class Location(BaseModel):
    lat: float = 0.0
    lng: float = 0.0


class ChatMessage(BaseModel):
    try:
        model_config = ConfigDict(extra="ignore")
    except Exception:
        pass

    role: str = "user"
    content: Optional[str] = None
    text: Optional[str] = None

    def __init__(self, **kwargs):
        role = kwargs.get("role")
        if role not in ("user", "assistant"):
            raise ValueError("role must be 'user' or 'assistant'")
        text = kwargs.get("text")
        content = kwargs.get("content")
        if not text and not content:
            raise ValueError("Either 'text' or 'content' must be provided")
        if text and not content:
            content = text
        elif content and not text:
            text = content
        elif text and content:
            content = text
        kwargs["role"] = role
        kwargs["text"] = text
        kwargs["content"] = content
        super().__init__(**kwargs)

    @field_validator("role", check_fields=False)
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("user", "assistant"):
            raise ValueError("role must be 'user' or 'assistant'")
        return v

    @model_validator(mode="before")
    @classmethod
    def validate_text_and_content(cls, data: Any) -> Any:
        if isinstance(data, dict):
            role = data.get("role")
            if role not in ("user", "assistant"):
                raise ValueError("role must be 'user' or 'assistant'")
            text = data.get("text")
            content = data.get("content")
            if not text and not content:
                raise ValueError("Either 'text' or 'content' must be provided")
            if text and not content:
                data["content"] = text
            elif content and not text:
                data["text"] = content
            elif text and content:
                data["content"] = text
        return data


class PatientProfile(BaseModel):
    relation: Optional[str] = None
    age: Optional[int] = None
    sex: Optional[str] = None
    conditions: list[str] = []
    pregnant: Optional[bool] = False


class MatchedCaregiver(BaseModel):
    caregiver_id: str = ""
    score: float = 0.0
    reason: str = ""
    factors: Optional[dict[str, float]] = None


# --- /triage ---

class TriageRequest(BaseModel):
    user_input: str = ""
    language: str = "auto"
    location: Optional[Location] = None
    conversation_history: list[ChatMessage] = []
    patient: Optional[PatientProfile] = None


class TriageResponse(BaseModel):
    follow_up_question: Optional[str] = None
    follow_up_options: list[str] = []
    care_type: Optional[str] = None
    urgency: Optional[str] = None
    red_flags: list[str] = []
    reasoning: Optional[str] = None
    confidence: Optional[float] = None
    matched_caregivers: list[MatchedCaregiver] = []
    emergency_steps: list[str] = []
    debug: Optional[dict[str, Any]] = None


# --- /match ---

class MatchRequest(BaseModel):
    care_type: str = ""
    urgency: str = ""
    location: Optional[Location] = None
    language: str = "auto"
    time_pref: Optional[str] = None


class MatchResponse(BaseModel):
    matched_caregivers: list[MatchedCaregiver] = []


# --- Caregiver entity ---

class CaregiverProfile(BaseModel):
    id: str = ""
    name: str = ""
    role: str = ""
    specialty: Optional[str] = None
    skills: list[str] = []
    lat: float = 0.0
    lng: float = 0.0
    languages: list[str] = []
    availability_slots: list[str] = []
    rating: float = 4.5
    review_count: int = 10
    home_visit: bool = True


# --- /book ---

class BookingRequest(BaseModel):
    caregiver_id: str = ""
    slot: str = ""
    user_name: str = ""
    phone: str = ""
    triage_summary: Optional[str] = None


class BookingResponse(BaseModel):
    booking_id: str = ""
    status: str = "confirmed"
    eta: Optional[str] = "30-45 mins"
    caregiver_id: str = ""
    slot: str = ""
    user_name: str = ""
    phone: str = ""


# --- /transcribe ---

class TranscribeResponse(BaseModel):
    text: str = ""
    language: str = "en"


# --- /health ---

class HealthResponse(BaseModel):
    status: str = "ok"
    model_version: str = "1.0.0"
    llm_available: bool = False
