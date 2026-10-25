package com.carecompass.app.util

/**
 * Pure (no Android) voice-session logic so it can be unit-tested on the JVM with
 * a fake recogniser event stream.
 *
 * The on-device SpeechRecognizer ends a session after a short pause. To let the
 * user speak one long sentence with pauses, we keep ONE logical listening
 * session open (tap-to-start until tap-to-stop) and stitch together the text of
 * every short recogniser session in [TranscriptBuffer].
 */

/** Events a recogniser session can deliver. */
enum class VoiceEvent {
    RESULTS,
    NO_MATCH,
    SPEECH_TIMEOUT,
    CLIENT_ERROR,
    FATAL_ERROR
}

/**
 * Joins the recognised text of consecutive recogniser sessions. Partial results
 * replace the in-progress text; a session's final result is committed as one
 * segment.
 */
class TranscriptBuffer {
    private val committed = mutableListOf<String>()
    private var partial: String = ""

    /** Live in-progress text (replaces the previous partial of this session). */
    fun setPartial(text: String) {
        partial = text.trim()
    }

    /** Commit a recogniser session's final text as a segment. */
    fun commit(text: String) {
        val t = text.trim()
        if (t.isNotEmpty()) committed.add(t)
        partial = ""
    }

    /** Text to show while speaking: committed segments + the current partial. */
    fun display(): String =
        (committed + listOfNotNull(partial.ifBlank { null })).joinToString(" ").trim()

    /** Final text when the user stops (flushes any pending partial). */
    fun finish(): String {
        if (partial.isNotBlank()) {
            committed.add(partial)
            partial = ""
        }
        return committed.joinToString(" ").trim()
    }

    fun clear() {
        committed.clear()
        partial = ""
    }

    fun isEmpty(): Boolean = committed.isEmpty() && partial.isBlank()
}

/**
 * Decides whether to immediately start a new recogniser session after an event.
 *
 * While the user has NOT tapped stop, RESULTS / NO_MATCH / SPEECH_TIMEOUT /
 * CLIENT_ERROR all mean "this short session ended, keep going". Once the user
 * taps stop (userWantsListening == false) nothing restarts, and ERROR_CLIENT is
 * treated as the normal end of the session.
 */
object VoiceRestartPolicy {
    fun shouldContinue(event: VoiceEvent, userWantsListening: Boolean): Boolean {
        if (!userWantsListening) return false
        return when (event) {
            VoiceEvent.RESULTS,
            VoiceEvent.NO_MATCH,
            VoiceEvent.SPEECH_TIMEOUT,
            VoiceEvent.CLIENT_ERROR -> true
            VoiceEvent.FATAL_ERROR -> false
        }
    }
}
