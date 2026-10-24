import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
DATA_DIR = APP_DIR / "data"
ML_DIR = BASE_DIR / "ml"
ARTIFACTS_DIR = ML_DIR / "artifacts"

try:
    from pydantic_settings import BaseSettings

    class Settings(BaseSettings):
        APP_NAME: str = "CareCompass"
        MODEL_VERSION: str = "2.0.0"
        DEBUG: bool = False
        HOST: str = "0.0.0.0"
        PORT: int = 8000
        DATABASE_URL: str = f"sqlite:///{BASE_DIR}/carecompass.db"

        # LLM Settings
        GEMINI_API_KEY: str = ""
        GEMINI_MODEL: str = "gemini-1.5-flash"
        LLM_TIMEOUT_SECONDS: float = 3.0

        # Official Label sets (single source of truth)
        CARE_TYPES: list[str] = [
            "paramedic_home_visit",
            "home_nursing",
            "lab_test_home",
            "teleconsultation",
            "emergency_112",
        ]

        URGENCIES: list[str] = [
            "emergency",
            "same_day",
            "scheduled",
        ]

        RED_FLAGS: list[str] = [
            "chest_pain",
            "breathlessness",
            "unconsciousness",
            "severe_bleeding",
            "stroke_symptoms",
            "seizure",
            "high_fever_infant",
            "suicidal_ideation",
            "severe_dehydration",
        ]

        CARE_TO_URGENCY: dict[str, str] = {
            "emergency_112": "emergency",
            "home_nursing": "same_day",
            "paramedic_home_visit": "same_day",
            "teleconsultation": "same_day",
            "lab_test_home": "scheduled",
        }

        # Safety & Triage Tunables
        CONF_THRESHOLD: float = 0.55
        MAX_FOLLOWUPS: int = 4
        MAX_KM: float = 35.0

        EMERGENCY_NUMBERS: list[str] = ["112", "102"]
        MENTAL_HEALTH_HELPLINE: str = "14416 (Tele-MANAS)"

        RED_FLAGS_FILE: Path = DATA_DIR / "red_flags.yaml"
        SYMPTOMS_FILE: Path = DATA_DIR / "symptoms.yaml"
        HINGLISH_NORM_FILE: Path = DATA_DIR / "hinglish_norm.json"
        OFFICIAL_DATA_DIR: Path = ML_DIR / "data" / "official"
        CAREGIVERS_CSV_FILE: Path = OFFICIAL_DATA_DIR / "caregivers.csv"
        CAREGIVERS_FILE: Path = DATA_DIR / "caregivers.json"
        EMERGENCY_STEPS_FILE: Path = DATA_DIR / "emergency_steps.yaml"
        ARTIFACTS_DIR: Path = ARTIFACTS_DIR

        class Config:
            env_file = ".env"
            extra = "ignore"

    settings = Settings()

except ImportError:
    class Settings:
        APP_NAME: str = "CareCompass"
        MODEL_VERSION: str = "2.0.0"
        DEBUG: bool = False
        HOST: str = "0.0.0.0"
        PORT: int = 8000
        DATABASE_URL: str = f"sqlite:///{BASE_DIR}/carecompass.db"

        GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
        GEMINI_MODEL: str = "gemini-1.5-flash"
        LLM_TIMEOUT_SECONDS: float = 3.0

        CARE_TYPES: list[str] = [
            "paramedic_home_visit",
            "home_nursing",
            "lab_test_home",
            "teleconsultation",
            "emergency_112",
        ]

        URGENCIES: list[str] = [
            "emergency",
            "same_day",
            "scheduled",
        ]

        RED_FLAGS: list[str] = [
            "chest_pain",
            "breathlessness",
            "unconsciousness",
            "severe_bleeding",
            "stroke_symptoms",
            "seizure",
            "high_fever_infant",
            "suicidal_ideation",
            "severe_dehydration",
        ]

        CARE_TO_URGENCY: dict[str, str] = {
            "emergency_112": "emergency",
            "home_nursing": "same_day",
            "paramedic_home_visit": "same_day",
            "teleconsultation": "same_day",
            "lab_test_home": "scheduled",
        }

        CONF_THRESHOLD: float = 0.55
        MAX_FOLLOWUPS: int = 4
        MAX_KM: float = 35.0

        EMERGENCY_NUMBERS: list[str] = ["112", "102"]
        MENTAL_HEALTH_HELPLINE: str = "14416 (Tele-MANAS)"

        RED_FLAGS_FILE: Path = DATA_DIR / "red_flags.yaml"
        SYMPTOMS_FILE: Path = DATA_DIR / "symptoms.yaml"
        HINGLISH_NORM_FILE: Path = DATA_DIR / "hinglish_norm.json"
        OFFICIAL_DATA_DIR: Path = ML_DIR / "data" / "official"
        CAREGIVERS_CSV_FILE: Path = OFFICIAL_DATA_DIR / "caregivers.csv"
        CAREGIVERS_FILE: Path = DATA_DIR / "caregivers.json"
        EMERGENCY_STEPS_FILE: Path = DATA_DIR / "emergency_steps.yaml"
        ARTIFACTS_DIR: Path = ARTIFACTS_DIR

    settings = Settings()
