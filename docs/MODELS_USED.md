# Models and APIs Used in CareCompass

In accordance with Hackathon guidelines, every model, open-source library, and external API utilized in CareCompass is declared below:

## 1. Machine Learning & Embeddings
- **Feature Extraction**: `scikit-learn` Char N-Gram TF-IDF Vectorizer (2-5 grams). Handles multilingual noise, Hindi-English code-mixing, phonetic spelling variants (`bukhar`, `bukhaar`, `buhar`), and typos without vocabulary mismatch.
- **Triage & Urgency Classification**: `scikit-learn` Calibrated Logistic Regression (`CalibratedClassifierCV`) and `LightGBM` (4.7.0). Calibrated probabilities fed into an asymmetric cost-sensitive Bayesian risk decision matrix.
- **Multilingual Embeddings**: `sentence-transformers` (`intfloat/multilingual-e5-small`) for 384-dimensional dense semantic representations of Hindi and English medical texts.

## 2. LLMs & GenAI
- **Gemini API (`gemini-1.5-flash`) via `google-genai`**: Used strictly for slot extraction and conversational rephrasing with temperature = 0.0 and strict JSON schema output.
- **Deterministic Rule Fallback**: Fully independent deterministic rule/regex fallback that operates with zero API key or during network downtime.

## 3. Speech & Audio
- **Android On-Device `SpeechRecognizer`**: Client-side speech-to-text supporting native Hindi, Hinglish, and English voice queries.
- **Backend STT (`faster-whisper`)**: `small` model with `language=hi` for audio uploads.

## 4. Transliteration & Normalization
- **`indic-transliteration`**: Converts Devanagari script to Roman phonetic representation.
- **Curated Hinglish Lexicon (`hinglish_norm.json`)**: Normalizes vernacular medical terms and spelling noise into canonical English medical terms.
