package com.carecompass.app.util

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer

enum class MicState {
    IDLE,
    LISTENING,
    PROCESSING
}

class SpeechHelper(
    private val context: Context,
    private val onStateChanged: (MicState) -> Unit,
    private val onPartialResult: (String) -> Unit,
    private val onFinalResult: (String) -> Unit,
    private val onError: (String) -> Unit
) {
    private var speechRecognizer: SpeechRecognizer? = null
    private val mainHandler = Handler(Looper.getMainLooper())

    init {
        mainHandler.post { initRecognizer() }
    }

    private fun initRecognizer() {
        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            return
        }

        try {
            speechRecognizer?.destroy()
            speechRecognizer = SpeechRecognizer.createSpeechRecognizer(context).apply {
                setRecognitionListener(object : RecognitionListener {
                    override fun onReadyForSpeech(params: Bundle?) {
                        onStateChanged(MicState.LISTENING)
                    }

                    override fun onBeginningOfSpeech() {
                        onStateChanged(MicState.LISTENING)
                    }

                    override fun onRmsChanged(rmsdB: Float) {}

                    override fun onBufferReceived(buffer: ByteArray?) {}

                    override fun onEndOfSpeech() {
                        onStateChanged(MicState.PROCESSING)
                    }

                    override fun onError(error: Int) {
                        onStateChanged(MicState.IDLE)
                        val message = when (error) {
                            SpeechRecognizer.ERROR_NO_MATCH ->
                                "No speech detected. Please tap mic again or type."
                            SpeechRecognizer.ERROR_SPEECH_TIMEOUT ->
                                "Speech timed out. Please tap mic again or type."
                            SpeechRecognizer.ERROR_AUDIO ->
                                "Microphone audio error. Please check mic settings."
                            SpeechRecognizer.ERROR_NETWORK, SpeechRecognizer.ERROR_NETWORK_TIMEOUT ->
                                "Network issue with speech engine. Please type symptoms."
                            SpeechRecognizer.ERROR_RECOGNIZER_BUSY ->
                                "Speech engine busy. Please retry in a moment."
                            SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS ->
                                "Microphone permission is required for voice input."
                            else ->
                                "Speech could not be recognized. Please type symptoms."
                        }
                        onError(message)
                    }

                    override fun onResults(results: Bundle?) {
                        onStateChanged(MicState.IDLE)
                        val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                        val text = matches?.firstOrNull()?.trim()
                        if (!text.isNullOrBlank()) {
                            onFinalResult(text)
                        } else {
                            onError("No speech recognized. Please type your symptoms.")
                        }
                    }

                    override fun onPartialResults(partialResults: Bundle?) {
                        val matches = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                        val text = matches?.firstOrNull()?.trim()
                        if (!text.isNullOrBlank()) {
                            onPartialResult(text)
                        }
                    }

                    override fun onEvent(eventType: Int, params: Bundle?) {}
                })
            }
        } catch (e: Exception) {
            speechRecognizer = null
        }
    }

    fun startListening(languageCode: String) {
        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            onError("Speech recognition is not available on this device/emulator. Please type symptoms.")
            onStateChanged(MicState.IDLE)
            return
        }

        val speechLang = when (languageCode) {
            "en" -> "en-IN"
            "hi" -> "hi-IN"
            "hinglish" -> "hi-IN"
            else -> "en-IN"
        }

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, speechLang)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, speechLang)
            putExtra("android.speech.extra.EXTRA_ADDITIONAL_LANGUAGES", arrayOf("en-IN", "hi-IN"))
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 3)
            putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, context.packageName)
        }

        mainHandler.post {
            try {
                if (speechRecognizer == null) {
                    initRecognizer()
                }
                onStateChanged(MicState.LISTENING)
                speechRecognizer?.startListening(intent)
            } catch (e: Exception) {
                onStateChanged(MicState.IDLE)
                onError("Failed to start microphone: ${e.localizedMessage}. Please type.")
            }
        }
    }

    fun stopListening() {
        mainHandler.post {
            try {
                speechRecognizer?.stopListening()
                onStateChanged(MicState.PROCESSING)
            } catch (e: Exception) {
                onStateChanged(MicState.IDLE)
            }
        }
    }

    fun destroy() {
        mainHandler.post {
            try {
                speechRecognizer?.destroy()
                speechRecognizer = null
            } catch (e: Exception) {}
            onStateChanged(MicState.IDLE)
        }
    }
}
