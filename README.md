# CareCompass: AI-Powered Care Navigation and Caregiver Matching

CareCompass understands patient requests in English, Hindi, and Hinglish (text or voice), asks targeted follow-up questions, classifies care type and urgency, flags red-flag symptoms, incorporates real-time environmental & seasonal context, and matches the best available caregiver.

### Dataset Citation
Trained and evaluated using:
> **"Sanocare synthetic care-triage dataset v1 (2026), provided for the IIIT-Delhi hackathon."**

### Official Label Specification
- **Care Types**: `paramedic_home_visit`, `home_nursing`, `lab_test_home`, `teleconsultation`, `emergency_112`
- **Urgencies**: `emergency`, `same_day`, `scheduled`
- **Red Flags**: `chest_pain`, `breathlessness`, `unconsciousness`, `severe_bleeding`, `stroke_symptoms`, `seizure`, `high_fever_infant`, `suicidal_ideation`, `severe_dehydration`
- **Deterministic Urgency**: Urgency is mapped directly from care type via `CARE_TO_URGENCY`.

## Tech Stack
- **Language**: Python 3.11 / 3.14
- **API**: FastAPI, Uvicorn, Pydantic v2
- **ML**: scikit-learn, LightGBM, sentence-transformers, PyTorch
- **LLM & Speech**: Groq Cloud SDK (`openai/gpt-oss-120b`, `llama-3.3-70b-versatile`, `whisper-large-v3-turbo`), Gemini API fallback, rule/regex deterministic safety fallback
- **Context & Weather**: Open-Meteo real-time weather & air quality API, North India seasonal modeling
- **Database**: SQLite via SQLAlchemy
- **Frontend**: Android Native (Kotlin, Jetpack Compose, Material 3, MVVM, Retrofit, Location API)

---

## 1. Quickstart with Docker (One-Command Start)
```bash
# Build and run the FastAPI server on port 8000
docker compose up --build
```
- API Docs (Swagger): `http://localhost:8000/docs`
- Health Endpoint: `http://localhost:8000/health`

---

## 2. Local Python Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
python -m unittest discover tests

# Start API server
./scripts/run_dev.sh
```

---

## 3. Running Smoke Tests
With the server running on `http://localhost:8000`:
```bash
./scripts/smoke_test.sh
```
Runs automated test cases:
1. `GET /health`
2. `POST /triage` - Vague fever (triggers follow-up question)
3. `POST /triage` - Chest pain Hinglish (High-severity Red Flag -> Emergency immediate)
4. `POST /triage` - Negation handling ("saans me koi dikkat nahi" -> Paramedic home visit, same-day)
5. `POST /match` - Standalone Caregiver ranking
6. `POST /book` - Appointment booking
7. `POST /transcribe` - Groq Whisper speech transcription

---

## 4. Running the Android App in Android Studio
1. Open Android Studio.
2. Select **Open** and select the `/android` directory:
   `/Users/shreyayagain/Desktop/Care-Compass/android`
3. Wait for Gradle sync to complete (Java 17+, Android Gradle Plugin 8.3+, Kotlin 1.9+).
4. Start an Android Virtual Device (Emulator) running API 26 or higher.
5. Note: The app connects to the local backend using Android emulator loopback:
   `http://10.0.2.2:8000/` (pre-configured with `usesCleartextTraffic="true"` for development).
6. Click **Run 'app'** (`Shift + F10`) to build and launch the app.

### 5. Voice & Context Features
1. **Groq Whisper Voice Transcription**:
   - High-accuracy multilingual Hindi/Hinglish/English voice input via `/transcribe`.
   - On-device speech recognition via Android `SpeechRecognizer` (`hi-IN`, `en-IN`) with real-time partial results and pulsing microphone indicator.
2. **Environmental & Seasonal Context**:
   - Location-aware weather & air quality (Open-Meteo) and season derivation.
   - Clinical escalation rules for extreme heat waves and severe air quality (AQI $\ge 200$) in vulnerable patients.
   - User privacy consent controls: context lookups are strictly opt-in and can be bypassed anytime.
