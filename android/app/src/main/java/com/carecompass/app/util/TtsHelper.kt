package com.carecompass.app.util

import android.content.Context
import android.speech.tts.TextToSpeech
import android.util.Log
import java.util.Locale

class TtsHelper(context: Context) {
    private var tts: TextToSpeech? = null
    private var isReady = false
    private var pendingText: String? = null
    private var pendingLang: String? = null

    init {
        tts = TextToSpeech(context.applicationContext) { status ->
            if (status == TextToSpeech.SUCCESS) {
                isReady = true
                pendingText?.let { text ->
                    speak(text, pendingLang ?: "en")
                    pendingText = null
                    pendingLang = null
                }
            } else {
                Log.e("TtsHelper", "TextToSpeech init failed with status: $status")
            }
        }
    }

    fun speak(text: String, languageCode: String = "en") {
        if (!isReady) {
            pendingText = text
            pendingLang = languageCode
            return
        }

        try {
            val locale = when (languageCode) {
                "hi" -> Locale("hi", "IN")
                else -> Locale.ENGLISH
            }
            tts?.language = locale
            tts?.speak(text, TextToSpeech.QUEUE_FLUSH, null, "CareCompassBookingSummary")
        } catch (e: Exception) {
            Log.e("TtsHelper", "Error in speak: ${e.message}")
        }
    }

    fun stop() {
        try {
            tts?.stop()
        } catch (e: Exception) {
            // Ignore
        }
    }

    fun shutdown() {
        try {
            tts?.stop()
            tts?.shutdown()
        } catch (e: Exception) {
            // Ignore
        }
    }
}
