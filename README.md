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
- **Database**: Supabase (Postgres + Auth) with automatic SQLite fallback when unconfigured
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

## 4. Supabase Setup (chat history + bookings)

The backend stores chat history, chat steps and bookings in Supabase (Postgres). If the
Supabase env vars are missing, it **falls back to SQLite** (so the no-key demo and the test
suite still run).

### Steps
1. Create a project at https://supabase.com and note the **Project URL** and **Project Ref**.
2. In **Project Settings → API**, copy:
   - `anon` key (client-side) — not used by the backend, but the app needs it.
   - `service_role` key (server-side) — used by the backend, bypasses RLS.
   - **JWT Secret** (Project Settings → API → JWT Settings) — for verifying user tokens
     (`SUPABASE_JWT_SECRET`). If you prefer asymmetric keys, set `SUPABASE_JWKS_URL` instead.
3. Enable **anonymous sign-in** (Authentication → Providers → enable anonymous) so users get a
   JWT without a password (or use any email/social provider).
4. Open the **SQL Editor** and run `supabase/schema.sql` (idempotent — creates tables, indexes
   and Row-Level Security policies).
5. Seed caregivers: `python scripts/seed_caregivers.py` (uses `SUPABASE_URL` + service-role key).
6. Put the values in `.env` (see `.env.example`):
   ```
   SUPABASE_URL=https://<ref>.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=<service_role_jwt>
   SUPABASE_JWT_SECRET=<jwt_secret>
   ```
   `GET /health` reports `store: "supabase"` when configured and reachable.

### Retention
The History tab keeps the user's **latest 5 sessions** via `GET /history` (query `limit`). Older
sessions are retained in the database for the audit log.

### Auth
New endpoints require `Authorization: Bearer <supabase-access-token>`. The backend verifies the
JWT (HS256 with `SUPABASE_JWT_SECRET`, or RS256/ES256 via `SUPABASE_JWKS_URL`), checks `exp` and
`aud == "authenticated"`, and returns `user_id` (`sub`). In dev, set `ENV=dev` and `DEV_USER_ID`
to skip minting a real token. `/triage` works with or without a token (history is logged only when
a token is present).

### curl examples
```bash
# 1. Triage (with a Supabase access token -> history is logged, returns session_id)
curl -X POST http://localhost:8000/triage \
  -H "Authorization: Bearer $ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"user_input":"papa ko do din se bukhar hai","language":"hinglish"}'

# 2. List the last 5 sessions
curl http://localhost:8000/history?limit=5 -H "Authorization: Bearer $ACCESS_TOKEN"

# 3. Get one session (summary + ordered steps + booking)
curl http://localhost:8000/history/$SESSION_ID -H "Authorization: Bearer $ACCESS_TOKEN"

# 4. Delete a session
curl -X DELETE http://localhost:8000/history/$SESSION_ID -H "Authorization: Bearer $ACCESS_TOKEN"

# 5. Book a caregiver (start_time ISO-8601, in the future, inside the caregiver window)
curl -X POST http://localhost:8000/book \
  -H "Authorization: Bearer $ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"caregiver_id":"CG_001","care_type":"teleconsultation","patient_name":"Rohan","start_time":"2026-11-01T14:00:00Z"}'

# 6. List upcoming bookings
curl "http://localhost:8000/bookings?status=upcoming" -H "Authorization: Bearer $ACCESS_TOKEN"

# 7. Cancel a booking (owner only)
curl -X POST http://localhost:8000/bookings/$BOOKING_ID/cancel -H "Authorization: Bearer $ACCESS_TOKEN"

# 8. Reschedule a booking
curl -X POST http://localhost:8000/bookings/$BOOKING_ID/reschedule \
  -H "Authorization: Bearer $ACCESS_TOKEN" -H "Content-Type: application/json" \
  -d '{"start_time":"2026-11-02T10:00:00Z"}'

# 9. Free 1-hour slots for a caregiver on a date
curl "http://localhost:8000/caregivers/CG_001/slots?date=2026-11-01" -H "Authorization: Bearer $ACCESS_TOKEN"
```

---

## 5. Running the Android App in Android Studio
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
