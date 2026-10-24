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
        MODEL_VERSION: str = "1.0.0"
        DEBUG: bool = False
        HOST: str = "0.0.0.0"
        PORT: int = 8000
        DATABASE_URL: str = f"sqlite:///{BASE_DIR}/carecompass.db"

        # LLM Settings
        GEMINI_API_KEY: str = ""
        GEMINI_MODEL: str = "gemini-1.5-flash"
        LLM_TIMEOUT_SECONDS: float = 3.0

        # Label sets
        CARE_TYPES: list[str] = [
            "paramedic_home_visit",
            "nurse_home_visit",
            "gp_teleconsult",
            "specialist",
            "emergency_referral",
        ]

        URGENCIES: list[str] = [
            "routine",
            "same_day",
            "immediate",
        ]

        SPECIALTIES: list[str] = [
            "cardiology",
            "pulmonology",
            "paediatrics",
            "gynaecology",
            "orthopaedics",
            "general_medicine",
            "dermatology",
            "neurology",
            "psychiatry",
        ]

        # Safety & Triage Tunables
        CONF_THRESHOLD: float = 0.55
        MAX_FOLLOWUPS: int = 4
        MAX_KM: float = 35.0

        # Asymmetric urgency cost matrix
        URGENCY_COST_MATRIX: dict[str, dict[str, float]] = {
            "routine": {"routine": 0.0, "same_day": 1.0, "immediate": 2.0},
            "same_day": {"routine": 4.0, "same_day": 0.0, "immediate": 1.0},
            "immediate": {"routine": 10.0, "same_day": 3.0, "immediate": 0.0},
        }

        # Matching weights
        MATCHING_WEIGHTS: dict[str, dict[str, float]] = {
            "routine": {
                "skill": 0.30,
                "distance": 0.15,
                "availability": 0.15,
                "language": 0.25,
                "rating": 0.15,
            },
            "same_day": {
                "skill": 0.30,
                "distance": 0.25,
                "availability": 0.25,
                "language": 0.10,
                "rating": 0.10,
            },
            "immediate": {
                "availability": 0.40,
                "distance": 0.35,
                "skill": 0.25,
                "language": 0.00,
                "rating": 0.00,
            },
        }

        EMERGENCY_NUMBERS: list[str] = ["112", "102"]
        MENTAL_HEALTH_HELPLINE: str = "14416 (Tele-MANAS)"

        RED_FLAGS_FILE: Path = DATA_DIR / "red_flags.yaml"
        SYMPTOMS_FILE: Path = DATA_DIR / "symptoms.yaml"
        HINGLISH_NORM_FILE: Path = DATA_DIR / "hinglish_norm.json"
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
        MODEL_VERSION: str = "1.0.0"
        DEBUG: bool = False
        HOST: str = "0.0.0.0"
        PORT: int = 8000
        DATABASE_URL: str = f"sqlite:///{BASE_DIR}/carecompass.db"

        GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
        GEMINI_MODEL: str = "gemini-1.5-flash"
        LLM_TIMEOUT_SECONDS: float = 3.0

        CARE_TYPES: list[str] = [
            "paramedic_home_visit",
            "nurse_home_visit",
            "gp_teleconsult",
            "specialist",
            "emergency_referral",
        ]

        URGENCIES: list[str] = [
            "routine",
            "same_day",
            "immediate",
        ]

        SPECIALTIES: list[str] = [
            "cardiology",
            "pulmonology",
            "paediatrics",
            "gynaecology",
            "orthopaedics",
            "general_medicine",
            "dermatology",
            "neurology",
            "psychiatry",
        ]

        CONF_THRESHOLD: float = 0.55
        MAX_FOLLOWUPS: int = 4
        MAX_KM: float = 35.0

        URGENCY_COST_MATRIX: dict[str, dict[str, float]] = {
            "routine": {"routine": 0.0, "same_day": 1.0, "immediate": 2.0},
            "same_day": {"routine": 4.0, "same_day": 0.0, "immediate": 1.0},
            "immediate": {"routine": 10.0, "same_day": 3.0, "immediate": 0.0},
        }

        MATCHING_WEIGHTS: dict[str, dict[str, float]] = {
            "routine": {
                "skill": 0.30,
                "distance": 0.15,
                "availability": 0.15,
                "language": 0.25,
                "rating": 0.15,
            },
            "same_day": {
                "skill": 0.30,
                "distance": 0.25,
                "availability": 0.25,
                "language": 0.10,
                "rating": 0.10,
            },
            "immediate": {
                "availability": 0.40,
                "distance": 0.35,
                "skill": 0.25,
                "language": 0.00,
                "rating": 0.00,
            },
        }

        EMERGENCY_NUMBERS: list[str] = ["112", "102"]
        MENTAL_HEALTH_HELPLINE: str = "14416 (Tele-MANAS)"

        RED_FLAGS_FILE: Path = DATA_DIR / "red_flags.yaml"
        SYMPTOMS_FILE: Path = DATA_DIR / "symptoms.yaml"
        HINGLISH_NORM_FILE: Path = DATA_DIR / "hinglish_norm.json"
        CAREGIVERS_FILE: Path = DATA_DIR / "caregivers.json"
        EMERGENCY_STEPS_FILE: Path = DATA_DIR / "emergency_steps.yaml"
        ARTIFACTS_DIR: Path = ARTIFACTS_DIR

    settings = Settings()
