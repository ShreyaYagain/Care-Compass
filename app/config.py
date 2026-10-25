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
        MODEL_VERSION: str = "2.2.0-tfidf-a"
        MODEL_NAME: str = "Model A: TF-IDF Char (2-5) + Calibrated Logistic Regression"
        DEBUG: bool = False
        HOST: str = "0.0.0.0"
        PORT: int = 8000
        DATABASE_URL: str = f"sqlite:///{BASE_DIR}/carecompass.db"

        # LLM Settings
        LLM_TIMEOUT_S: float = float(os.getenv("LLM_TIMEOUT_S", "3.0"))
        SCREEN_TIMEOUT_S: float = float(os.getenv("SCREEN_TIMEOUT_S", "4.0"))
        # The second opinion runs on a tight budget so it never blocks the result.
        SECOND_OPINION_TIMEOUT_S: float = float(os.getenv("SECOND_OPINION_TIMEOUT_S", "2.5"))

        # LLM Settings (provider-agnostic, OpenAI-compatible chat completions).
        # Provider is "deepseek" | "groq"; the API key is read per provider.
        LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "deepseek")
        LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "")   # empty -> provider default
        LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-v4-pro")
        LLM_FAST_MODEL: str = os.getenv("LLM_FAST_MODEL", "deepseek-flash")  # empty -> LLM_MODEL
        DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
        GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

        # Legacy names (kept so an existing .env keeps working).
        DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        LLM_TIMEOUT_SECONDS: float = 3.0

        # Speech-to-text provider: groq_whisper | local_whisper | android_only.
        # Empty -> groq_whisper only if a Groq key is present, else android_only.
        STT_PROVIDER: str = os.getenv("STT_PROVIDER", "")

        # LLM role in the decision pipeline (ML-first architecture).
        #   second_opinion (default): the LLM runs in parallel AFTER the ML
        #     models and can only raise severity (ask a confirmation question),
        #     never lower a decision.
        #   off: the LLM is disabled for triage decisions (rules + ML only).
        LLM_ROLE: str = os.getenv("LLM_ROLE", "second_opinion")

        # Care-type decision policy. Empty = existing hybrid (rules + ML argmax).
        #   weighted: ML and a strict-JSON LLM care-type call are combined by
        #     0.4*ML_prob + 0.6*LLM_confidence; ML wins if its top prob >= 0.90.
        DECISION_POLICY: str = os.getenv("DECISION_POLICY", "")

        # Supabase (Postgres + Auth). Empty -> SQLite fallback (no-key demo/tests).
        SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
        SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "")
        SUPABASE_JWKS_URL: str = os.getenv("SUPABASE_JWKS_URL", "")
        ENV: str = os.getenv("ENV", "dev")
        DEV_USER_ID: str = os.getenv("DEV_USER_ID", "")

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
        CONF_THRESHOLD: float = 0.5
        HISTORY_KEY_HEADER: str = "X-Device-Id"
        MAX_FOLLOWUPS: int = 2
        MAX_KM: float = 35.0

        EMERGENCY_NUMBERS: list[str] = ["112", "102"]
        MENTAL_HEALTH_HELPLINE: str = "14416 (Tele-MANAS)"

        RED_FLAGS_FILE: Path = DATA_DIR / "red_flags.yaml"
        SYMPTOMS_FILE: Path = DATA_DIR / "symptoms.yaml"
        MODULES_FILE: Path = DATA_DIR / "modules.yaml"
        USE_SYNTHETIC_CAREGIVERS: bool = False
        SYNTHETIC_CAREGIVERS_FILE: Path = DATA_DIR / "caregivers_synthetic.csv"
        HINGLISH_NORM_FILE: Path = DATA_DIR / "hinglish_norm.json"
        OFFICIAL_DATA_DIR: Path = ML_DIR / "data" / "official"
        CAREGIVERS_CSV_FILE: Path = OFFICIAL_DATA_DIR / "caregivers.csv"
        EMERGENCY_STEPS_FILE: Path = DATA_DIR / "emergency_steps.yaml"
        ARTIFACTS_DIR: Path = ARTIFACTS_DIR

        class Config:
            env_file = ".env"
            extra = "ignore"

    settings = Settings()

except ImportError:
    class Settings:
        APP_NAME: str = "CareCompass"
        MODEL_VERSION: str = "2.2.0-tfidf-a"
        MODEL_NAME: str = "Model A: TF-IDF Char (2-5) + Calibrated Logistic Regression"
        DEBUG: bool = False
        HOST: str = "0.0.0.0"
        PORT: int = 8000
        DATABASE_URL: str = f"sqlite:///{BASE_DIR}/carecompass.db"

        LLM_TIMEOUT_S: float = float(os.getenv("LLM_TIMEOUT_S", "3.0"))
        SCREEN_TIMEOUT_S: float = float(os.getenv("SCREEN_TIMEOUT_S", "2.5"))

        # LLM Settings (provider-agnostic, OpenAI-compatible chat completions).
        # Provider is "deepseek" | "groq"; the API key is read per provider.
        LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "deepseek")
        LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "")   # empty -> provider default
        LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-v4-pro")
        LLM_FAST_MODEL: str = os.getenv("LLM_FAST_MODEL", "deepseek-flash")  # empty -> LLM_MODEL
        DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
        GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

        # Legacy names (kept so an existing .env keeps working).
        DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        LLM_TIMEOUT_SECONDS: float = 3.0

        # Speech-to-text provider: groq_whisper | local_whisper | android_only.
        # Empty -> groq_whisper only if a Groq key is present, else android_only.
        STT_PROVIDER: str = os.getenv("STT_PROVIDER", "")

        # LLM role in the decision pipeline (ML-first architecture).
        #   second_opinion (default): the LLM runs in parallel AFTER the ML
        #     models and can only raise severity (ask a confirmation question),
        #     never lower a decision.
        #   off: the LLM is disabled for triage decisions (rules + ML only).
        LLM_ROLE: str = os.getenv("LLM_ROLE", "second_opinion")

        # Care-type decision policy. Empty = existing hybrid (rules + ML argmax).
        #   weighted: ML and a strict-JSON LLM care-type call are combined by
        #     0.4*ML_prob + 0.6*LLM_confidence; ML wins if its top prob >= 0.90.
        DECISION_POLICY: str = os.getenv("DECISION_POLICY", "")

        # Supabase (Postgres + Auth). Empty -> SQLite fallback (no-key demo/tests).
        SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
        SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "")
        SUPABASE_JWKS_URL: str = os.getenv("SUPABASE_JWKS_URL", "")
        ENV: str = os.getenv("ENV", "dev")
        DEV_USER_ID: str = os.getenv("DEV_USER_ID", "")

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

        CONF_THRESHOLD: float = 0.5
        MAX_FOLLOWUPS: int = 2
        MAX_KM: float = 35.0
        HISTORY_KEY_HEADER: str = "X-Device-Id"

        EMERGENCY_NUMBERS: list[str] = ["112", "102"]
        MENTAL_HEALTH_HELPLINE: str = "14416 (Tele-MANAS)"

        RED_FLAGS_FILE: Path = DATA_DIR / "red_flags.yaml"
        SYMPTOMS_FILE: Path = DATA_DIR / "symptoms.yaml"
        MODULES_FILE: Path = DATA_DIR / "modules.yaml"
        USE_SYNTHETIC_CAREGIVERS: bool = False
        SYNTHETIC_CAREGIVERS_FILE: Path = DATA_DIR / "caregivers_synthetic.csv"
        HINGLISH_NORM_FILE: Path = DATA_DIR / "hinglish_norm.json"
        OFFICIAL_DATA_DIR: Path = ML_DIR / "data" / "official"
        CAREGIVERS_CSV_FILE: Path = OFFICIAL_DATA_DIR / "caregivers.csv"
        EMERGENCY_STEPS_FILE: Path = DATA_DIR / "emergency_steps.yaml"
        ARTIFACTS_DIR: Path = ARTIFACTS_DIR

    settings = Settings()
