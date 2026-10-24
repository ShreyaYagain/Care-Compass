package com.carecompass.app.util

import android.content.Context
import android.content.Intent
import android.media.MediaRecorder
import android.os.Build
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
import java.io.File

enum class MicState {
    IDLE,
    LISTENING,
    PROCESSING
}

class SpeechHelper(
    private val context: Context,
    private val repository: Repository = Repository(ApiService.create()),
    private val onStateChanged: (MicState) -> Unit,
    private val onPartialResult: (String) -> Unit,
    private val onFinalResult: (String) -> Unit,
    private val onError: (String) -> Unit
) {
    private var speechRecognizer: SpeechRecognizer? = null
    private var mediaRecorder: MediaRecorder? = null
    private var audioFile: File? = null
    private var isRecordingFallback = false
    private var useFallback = false
    private var currentLanguage = "hinglish"

    private val mainHandler = Handler(Looper.getMainLooper())
    private val scope = CoroutineScope(Dispatchers.Main)
    private val maxRecordRunnable = Runnable { stopListening() }

    init {
        mainHandler.post { initRecognizer() }
    }

    private fun initRecognizer() {
        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            Log.w("Voice", "SpeechRecognizer is NOT available on this device/emulator. Defaulting to fallback recorder.")
            useFallback = true
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
                        Log.e("Voice", "SpeechRecognizer onError code: $error")

                        // Switch to fallback path (b) on client, busy, network, or permissions errors
                        val switchCodes = listOf(
                            SpeechRecognizer.ERROR_CLIENT,
                            SpeechRecognizer.ERROR_RECOGNIZER_BUSY,
                            SpeechRecognizer.ERROR_NETWORK,
                            SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS
                        )

                        if (error in switchCodes && !useFallback) {
                            Log.w("Voice", "Switching to path (b) MediaRecorder fallback due to error code $error")
                            useFallback = true
                            startFallbackRecording(currentLanguage)
                            return
                        }

                        onStateChanged(MicState.IDLE)
                        val message = when (error) {
                            SpeechRecognizer.ERROR_NO_MATCH ->
                                "No speech detected. Please tap mic again or type."
                            SpeechRecognizer.ERROR_SPEECH_TIMEOUT ->
                                "Speech timed out. Please tap mic again or type."
                            SpeechRecognizer.ERROR_AUDIO ->
                                "Microphone audio error. Check mic settings or type."
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
            Log.e("Voice", "Failed to create SpeechRecognizer: ${e.localizedMessage}. Using fallback.")
            speechRecognizer = null
            useFallback = true
        }
    }

    fun startListening(languageCode: String) {
        currentLanguage = languageCode

        if (useFallback || !SpeechRecognizer.isRecognitionAvailable(context)) {
            startFallbackRecording(languageCode)
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
                Log.e("Voice", "Exception in startListening: ${e.localizedMessage}. Falling back.")
                useFallback = true
                startFallbackRecording(languageCode)
            }
        }
    }

    // Path (b) Fallback: MediaRecorder up to 15 seconds -> POST /transcribe
    private fun startFallbackRecording(languageCode: String) {
        mainHandler.post {
            try {
                audioFile = File(context.cacheDir, "voice_record.m4a")
                if (audioFile?.exists() == true) {
                    audioFile?.delete()
                }

                mediaRecorder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                    MediaRecorder(context)
                } else {
                    @Suppress("DEPRECATION")
                    MediaRecorder()
                }.apply {
                    setAudioSource(MediaRecorder.AudioSource.MIC)
                    setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
                    setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                    setAudioEncodingBitRate(64000)
                    setAudioSamplingRate(16000)
                    setOutputFile(audioFile?.absolutePath)
                    prepare()
                    start()
                }

                isRecordingFallback = true
                onStateChanged(MicState.LISTENING)
                onPartialResult("Listening… (Speak now)")

                // Auto stop after 15 seconds
                mainHandler.removeCallbacks(maxRecordRunnable)
                mainHandler.postDelayed(maxRecordRunnable, 15000)
            } catch (e: Exception) {
                Log.e("Voice", "MediaRecorder fallback failed: ${e.localizedMessage}")
                isRecordingFallback = false
                onStateChanged(MicState.IDLE)
                onError("Microphone unavailable on emulator. Please check mic settings or type symptoms.")
            }
        }
    }

    fun stopListening() {
        mainHandler.removeCallbacks(maxRecordRunnable)

        if (isRecordingFallback) {
            stopFallbackRecording()
            return
        }

        mainHandler.post {
            try {
                speechRecognizer?.stopListening()
                onStateChanged(MicState.PROCESSING)
            } catch (e: Exception) {
                onStateChanged(MicState.IDLE)
            }
        }
    }

    private fun stopFallbackRecording() {
        mainHandler.post {
            try {
                if (isRecordingFallback) {
                    isRecordingFallback = false
                    mediaRecorder?.stop()
                    mediaRecorder?.release()
                    mediaRecorder = null
                    onStateChanged(MicState.PROCESSING)

                    val file = audioFile
                    if (file != null && file.exists() && file.length() > 0) {
                        uploadAudioForTranscription(file, currentLanguage)
                    } else {
                        onStateChanged(MicState.IDLE)
                        onError("No audio recorded. Please try again or type.")
                    }
                }
            } catch (e: Exception) {
                Log.e("Voice", "Error stopping MediaRecorder: ${e.localizedMessage}")
                isRecordingFallback = false
                mediaRecorder = null
                onStateChanged(MicState.IDLE)
                onError("Audio recording error. Please type symptoms.")
            }
        }
    }

    private fun uploadAudioForTranscription(file: File, languageCode: String) {
        scope.launch {
            onStateChanged(MicState.PROCESSING)
            val result = withContext(Dispatchers.IO) {
                repository.transcribeAudio(file, languageCode)
            }

            result.fold(
                onSuccess = { resp ->
                    onStateChanged(MicState.IDLE)
                    if (resp.text.isNotBlank()) {
                        onFinalResult(resp.text)
                    } else {
                        onError("Could not transcribe speech. Please type your symptoms.")
                    }
                },
                onFailure = { err ->
                    Log.e("Voice", "Server transcription error: ${err.localizedMessage}")
                    onStateChanged(MicState.IDLE)
                    onError("Voice transcription error. Please type your symptoms.")
                }
            )
        }
    }

    fun destroy() {
        mainHandler.removeCallbacks(maxRecordRunnable)
        mainHandler.post {
            try {
                if (isRecordingFallback) {
                    mediaRecorder?.stop()
                    mediaRecorder?.release()
                    mediaRecorder = null
                    isRecordingFallback = false
                }
                speechRecognizer?.destroy()
                speechRecognizer = null
            } catch (e: Exception) {}
            onStateChanged(MicState.IDLE)
        }
    }
}
