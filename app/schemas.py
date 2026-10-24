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
    name: Optional[str] = None
    role: Optional[str] = None
    qualification: Optional[str] = None
    languages: list[str] = []
    rating: Optional[float] = None
    free_from: Optional[str] = None
    free_until: Optional[str] = None
    distance_km: Optional[float] = None
    venue: Optional[str] = None
    department: Optional[str] = None
    facility_name: Optional[str] = None


# --- /triage ---

class TriageRequest(BaseModel):
    user_input: str = ""
    language: str = "auto"
    location: Optional[Location] = None
    conversation_history: list[ChatMessage] = []
    patient: Optional[PatientProfile] = None
    client_time: Optional[str] = None
    context_consent: Optional[bool] = False
    session_id: Optional[str] = None
    input_mode: Optional[str] = None
    module_id: Optional[str] = None
    module_answers: Optional[dict[str, Any]] = None


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
    context_used: Optional[dict[str, Any]] = None
    debug: Optional[dict[str, Any]] = None
    session_id: Optional[str] = None
    module_card: Optional[dict[str, Any]] = None
    secondary_options: list[dict[str, Any]] = []
    card_lines: Optional[dict[str, str]] = None
    details: Optional[dict[str, Any]] = None
    disclaimer: Optional[str] = None


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
    caregiver_id: str = ""
    name: str = ""
    role: str = ""
    qualification: Optional[str] = ""
    gender: Optional[str] = ""
    languages: list[str] = []
    skills: list[str] = []
    base_area: Optional[str] = ""
    base_lat: float = 0.0
    base_lng: float = 0.0
    max_radius_km: float = 0.0
    tier: Optional[str] = "base"
    rating: float = 4.0
    experience_years: int = 1
    free_from: str = "09:00"
    free_until: str = "18:00"
    active: bool = True


# --- /book ---

class BookingRequest(BaseModel):
    caregiver_id: str = ""
    slot: str = ""
    user_name: str = ""
    phone: str = ""
    triage_summary: Optional[str] = None
    # New optional fields (backward compatible)
    care_type: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    patient_name: Optional[str] = None
    relation: Optional[str] = None
    session_id: Optional[str] = None
    address: Optional[str] = None
    contact_phone: Optional[str] = None


class BookingResponse(BaseModel):
    booking_id: str = ""
    id: Optional[str] = None
    status: str = "confirmed"
    eta: Optional[str] = "30-45 mins"
    caregiver_id: str = ""
    slot: str = ""
    user_name: str = ""
    phone: str = ""
    # New optional fields
    care_type: Optional[str] = None
    patient_name: Optional[str] = None
    relation: Optional[str] = None
    address: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    contact_phone: Optional[str] = None
    caregiver: Optional[dict[str, Any]] = None


class HistorySessionItem(BaseModel):
    id: str = ""
    first_message: Optional[str] = None
    care_type: Optional[str] = None
    urgency: Optional[str] = None
    emergency: bool = False
    status: Optional[str] = None
    created_at: Optional[str] = None
    # Android-friendly fields
    outcome: Optional[str] = None
    via_voice: bool = False


class HistoryStepItem(BaseModel):
    step_index: int = 0
    kind: str = ""
    payload: dict[str, Any] = {}
    created_at: Optional[str] = None
    # Android-friendly flattened fields
    type: Optional[str] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    is_voice: bool = False
    user_answer: Optional[str] = None
    care_type: Optional[str] = None
    urgency: Optional[str] = None
    reasoning: Optional[str] = None
    suggested_caregivers: list[str] = []
    chosen_caregiver: Optional[str] = None
    booking_id: Optional[str] = None
    booking_date: Optional[str] = None
    booking_time: Optional[str] = None
    emergency_text: Optional[str] = None


class HistoryDetailResponse(BaseModel):
    id: str = ""
    first_message: Optional[str] = None
    language: Optional[str] = None
    input_mode: Optional[str] = None
    care_type: Optional[str] = None
    urgency: Optional[str] = None
    emergency: bool = False
    red_flags: list[str] = []
    reasoning: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    steps: list[HistoryStepItem] = []
    booking: Optional[dict[str, Any]] = None


class BookingItem(BaseModel):
    id: str = ""
    care_type: Optional[str] = None
    patient_name: Optional[str] = None
    relation: Optional[str] = None
    caregiver: Optional[dict[str, Any]] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    address: Optional[str] = None
    status: Optional[str] = None
    reason: Optional[str] = None
    # Android-friendly field
    service: Optional[str] = None


# --- /transcribe ---

class TranscribeResponse(BaseModel):
    text: str = ""
    language: str = "en"


# --- /health ---

class HealthResponse(BaseModel):
    status: str = "ok"
    model_version: str = "1.0.0"
    llm_available: bool = False
    store: str = "sqlite"
    screen_status: Optional[str] = None
