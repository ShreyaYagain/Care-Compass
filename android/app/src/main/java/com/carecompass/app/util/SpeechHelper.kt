package com.carecompass.app.util

import android.content.Context
import android.content.Intent
import android.media.AudioManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log
import com.carecompass.app.data.ApiService
import com.carecompass.app.data.Repository
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

enum class MicState {
    IDLE,
    LISTENING,
    PROCESSING
}

/**
 * Voice input that keeps listening until the user taps the mic again (or a 60 s
 * hard limit), instead of stopping at the first short pause.
 *
 * The SpeechRecognizer ends a session after a short silence. While the user has
 * NOT tapped stop we append each session's text to a [TranscriptBuffer] and
 * immediately start a new session (250 ms later, recreating the recogniser if
 * it is busy). The final text is the joined buffer; it is handed back via
 * [onFinalResult] and NEVER auto-sent — the caller fills the input box so the
 * user can review/edit and press Send.
 */
class SpeechHelper(
    private val context: Context,
    private val repository: Repository = Repository(ApiService.create()),
    private val onStateChanged: (MicState) -> Unit,
    private val onPartialResult: (String) -> Unit,
    private val onFinalResult: (String) -> Unit,
    private val onError: (String) -> Unit,
    private val onLevelChanged: (Float) -> Unit = {}
) {
    private var speechRecognizer: SpeechRecognizer? = null
    private var currentLanguage = "hinglish"
    private var currentIntent: Intent? = null

    private val mainHandler = Handler(Looper.getMainLooper())
    private val scope = CoroutineScope(Dispatchers.Main)

    private val buffer = TranscriptBuffer()
    private var userWantsListening = false
    private var finalized = false

    // Long-silence hints: many devices ignore these, but they help where honoured.
    private val silenceWindowMs = 8000L
    private val restartDelayMs = 250L
    private val stopGraceMs = 1600L
    private val hardLimitMs = 60_000L

    private val hardLimitRunnable = Runnable {
        if (userWantsListening) {
            Log.i("Voice", "60s hard limit reached; stopping")
            stopListening()
        }
    }
    private val stopGraceRunnable = Runnable { finalizeSession() }

    init {
        mainHandler.post { initRecognizer() }
    }

    private fun initRecognizer() {
        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            Log.w("Voice", "SpeechRecognizer is NOT available on this device/emulator.")
            return
        }
        try {
            speechRecognizer?.destroy()
            speechRecognizer = SpeechRecognizer.createSpeechRecognizer(context).apply {
                setRecognitionListener(buildListener())
            }
        } catch (e: Exception) {
            Log.e("Voice", "Failed to create SpeechRecognizer: ${e.localizedMessage}")
            speechRecognizer = null
        }
    }

    private fun buildListener(): RecognitionListener = object : RecognitionListener {
        override fun onReadyForSpeech(params: Bundle?) {
            onStateChanged(MicState.LISTENING)
        }

        override fun onBeginningOfSpeech() {
            onStateChanged(MicState.LISTENING)
        }

        override fun onRmsChanged(rmsdB: Float) {
            onLevelChanged(rmsdB)
        }

        override fun onBufferReceived(buffer: ByteArray?) {}

        override fun onEndOfSpeech() {
            // A short session ended; if the user hasn't stopped we will restart.
            if (userWantsListening) onStateChanged(MicState.LISTENING)
        }

        override fun onError(error: Int) {
            Log.w("Voice", "SpeechRecognizer onError code: $error (wantsListening=$userWantsListening)")
            if (!userWantsListening) {
                // Normal end after an explicit stop: finalize with whatever we have.
                finalizeSession()
                return
            }
            when (error) {
                SpeechRecognizer.ERROR_NO_MATCH -> restartSession()
                SpeechRecognizer.ERROR_SPEECH_TIMEOUT -> restartSession()
                SpeechRecognizer.ERROR_CLIENT -> restartSession()
                SpeechRecognizer.ERROR_RECOGNIZER_BUSY -> {
                    // Recreate the recogniser so the next start isn't rejected.
                    initRecognizer()
                    restartSession()
                }
                else -> {
                    // Fatal: stop and surface a clear message.
                    userWantsListening = false
                    mainHandler.removeCallbacks(hardLimitRunnable)
                    val message = when (error) {
                        SpeechRecognizer.ERROR_AUDIO ->
                            "Microphone audio error. Check mic settings or type."
                        SpeechRecognizer.ERROR_NETWORK, SpeechRecognizer.ERROR_NETWORK_TIMEOUT ->
                            "Network issue with speech engine. Please type symptoms."
                        SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS ->
                            "Microphone permission is required for voice input."
                        else ->
                            "Speech could not be recognized. Please type symptoms."
                    }
                    onStateChanged(MicState.IDLE)
                    onError(message)
                }
            }
        }

        override fun onResults(results: Bundle?) {
            val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            val text = matches?.firstOrNull()?.trim().orEmpty()
            buffer.commit(text)
            onPartialResult(buffer.display())
            if (VoiceRestartPolicy.shouldContinue(VoiceEvent.RESULTS, userWantsListening)) {
                restartSession()
            } else {
                finalizeSession()
            }
        }

        override fun onPartialResults(partialResults: Bundle?) {
            if (!userWantsListening) return
            val matches = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
            val text = matches?.firstOrNull()?.trim().orEmpty()
            if (text.isNotBlank()) {
                buffer.setPartial(text)
                onPartialResult(buffer.display())
            }
        }

        override fun onEvent(eventType: Int, params: Bundle?) {}
    }

    private fun buildIntent(speechLang: String): Intent =
        Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, speechLang)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, speechLang)
            putExtra("android.speech.extra.EXTRA_ADDITIONAL_LANGUAGES", arrayOf("hi-IN", "en-IN"))
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
            putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, context.packageName)
            // Long silence windows (hints only; devices may ignore them).
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, silenceWindowMs)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, silenceWindowMs)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS, silenceWindowMs)
        }

    fun startListening(languageCode: String) {
        currentLanguage = languageCode
        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            onStateChanged(MicState.IDLE)
            onError("Speech recognition unavailable on this device. Please type your symptoms.")
            return
        }
        val speechLang = when (languageCode) {
            "en" -> "en-IN"
            "hi" -> "hi-IN"
            "hinglish" -> "hi-IN"
            else -> "en-IN"
        }
        currentIntent = buildIntent(speechLang)
        buffer.clear()
        userWantsListening = true
        finalized = false
        mainHandler.removeCallbacks(stopGraceRunnable)
        mainHandler.post {
            onStateChanged(MicState.LISTENING)
            muteBeepBriefly()
            startSession()
            mainHandler.removeCallbacks(hardLimitRunnable)
            mainHandler.postDelayed(hardLimitRunnable, hardLimitMs)
        }
    }

    private fun startSession() {
        val recognizer = speechRecognizer ?: run { initRecognizer(); speechRecognizer }
        if (recognizer == null) {
            userWantsListening = false
            onStateChanged(MicState.IDLE)
            onError("Speech engine unavailable. Please type your symptoms.")
            return
        }
        try {
            recognizer.startListening(currentIntent)
        } catch (e: Exception) {
            Log.w("Voice", "startListening failed, recreating recogniser: ${e.localizedMessage}")
            initRecognizer()
            try {
                speechRecognizer?.startListening(currentIntent)
            } catch (e2: Exception) {
                Log.e("Voice", "startListening failed after recreate: ${e2.localizedMessage}")
                userWantsListening = false
                onStateChanged(MicState.IDLE)
                onError("Speech engine busy. Please tap the mic again.")
            }
        }
    }

    private fun restartSession() {
        if (!userWantsListening) {
            finalizeSession()
            return
        }
        try {
            speechRecognizer?.cancel()
        } catch (_: Exception) {
        }
        mainHandler.postDelayed({
            if (userWantsListening) startSession()
        }, restartDelayMs)
    }

    fun stopListening() {
        if (!userWantsListening) return
        userWantsListening = false
        mainHandler.removeCallbacks(hardLimitRunnable)
        onStateChanged(MicState.PROCESSING)
        try {
            speechRecognizer?.stopListening()
        } catch (e: Exception) {
            Log.w("Voice", "stopListening failed: ${e.localizedMessage}")
        }
        muteBeepBriefly()
        // If the recogniser never delivers onResults, finalize with what we have.
        mainHandler.removeCallbacks(stopGraceRunnable)
        mainHandler.postDelayed(stopGraceRunnable, stopGraceMs)
    }

    private fun finalizeSession() {
        if (finalized) return
        finalized = true
        mainHandler.removeCallbacks(hardLimitRunnable)
        mainHandler.removeCallbacks(stopGraceRunnable)
        userWantsListening = false
        val text = buffer.finish()
        onStateChanged(MicState.IDLE)
        if (text.isNotBlank()) {
            validateAndSubmit(text)
        } else {
            onError("No speech recognized. Please tap the mic and try again, or type.")
        }
    }

    // On-device recognition produces the raw transcript; DeepSeek validates and
    // normalises it before it reaches triage. The user still reviews and sends.
    private fun validateAndSubmit(rawText: String) {
        onStateChanged(MicState.PROCESSING)
        scope.launch {
            val result = withContext(Dispatchers.IO) {
                repository.validateTranscript(rawText, currentLanguage)
            }
            result.fold(
                onSuccess = { resp ->
                    onStateChanged(MicState.IDLE)
                    onFinalResult(if (resp.text.isNotBlank()) resp.text else rawText)
                },
                onFailure = { err ->
                    Log.w("Voice", "Transcript validation failed: ${err.localizedMessage}")
                    onStateChanged(MicState.IDLE)
                    onFinalResult(rawText)
                }
            )
        }
    }

    /** Best-effort: mute the system/media streams briefly around start/stop so
     * the recogniser beep is not distracting; always restored. */
    private fun muteBeepBriefly() {
        try {
            val am = context.getSystemService(Context.AUDIO_SERVICE) as? AudioManager ?: return
            val streams = intArrayOf(AudioManager.STREAM_SYSTEM, AudioManager.STREAM_MUSIC)
            val saved = streams.map { it to am.getStreamVolume(it) }
            streams.forEach { am.setStreamVolume(it, 0, 0) }
            mainHandler.postDelayed({
                try {
                    saved.forEach { (stream, vol) -> am.setStreamVolume(stream, vol, 0) }
                } catch (_: Exception) {
                }
            }, 800L)
        } catch (_: Exception) {
        }
    }

    fun destroy() {
        mainHandler.post {
            mainHandler.removeCallbacks(hardLimitRunnable)
            mainHandler.removeCallbacks(stopGraceRunnable)
            userWantsListening = false
            try {
                speechRecognizer?.destroy()
                speechRecognizer = null
            } catch (e: Exception) {
            }
            onStateChanged(MicState.IDLE)
        }
    }
}
