package com.carecompass.app

import com.carecompass.app.util.TranscriptBuffer
import com.carecompass.app.util.VoiceEvent
import com.carecompass.app.util.VoiceRestartPolicy
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Tests the continuous-listening buffer/restart logic with a FAKE recogniser
 * (no Android device needed). The real SpeechHelper feeds the same logic from
 * onPartialResults / onResults / onError.
 */
class VoiceSessionTest {

    /** A scripted recogniser session: partials, then either a final result or an error. */
    private data class FakeSession(
        val partials: List<String> = emptyList(),
        val final: String? = null,
        val error: VoiceEvent? = null
    )

    /**
     * Replays the fake sessions exactly like SpeechHelper's listener would:
     * partials replace the live text, a final commits a segment, and an error
     * either restarts (while listening) or finishes (after stop).
     */
    private fun replay(
        sessions: List<FakeSession>,
        stopBeforeSession: Int? = null
    ): Pair<String, List<Boolean>> {
        val buffer = TranscriptBuffer()
        var userWantsListening = true
        val restarts = mutableListOf<Boolean>()
        sessions.forEachIndexed { index, session ->
            if (stopBeforeSession == index) userWantsListening = false
            session.partials.forEach { buffer.setPartial(it) }
            when {
                session.error != null -> {
                    val cont = VoiceRestartPolicy.shouldContinue(session.error, userWantsListening)
                    restarts.add(cont)
                }
                session.final != null -> {
                    buffer.commit(session.final)
                    val cont = VoiceRestartPolicy.shouldContinue(VoiceEvent.RESULTS, userWantsListening)
                    restarts.add(cont)
                }
            }
        }
        return buffer.finish() to restarts
    }

    @Test
    fun bufferJoinsSegmentsAcrossRecogniserRestarts() {
        val (text, restarts) = replay(
            listOf(
                FakeSession(partials = listOf("papa ko"), final = "papa ko"),
                FakeSession(partials = listOf("seene mein"), final = "seene mein dard"),
                FakeSession(partials = listOf("aur saans nahi"), final = "aur saans nahi aa rahi")
            )
        )
        assertEquals("papa ko seene mein dard aur saans nahi aa rahi", text)
        // Every session restarted while the user is still listening.
        assertTrue(restarts.all { it })
        assertEquals(3, restarts.size)
    }

    @Test
    fun longPauseSentenceIsStitchedWhole() {
        // The exact reported sentence delivered with long pauses between phrases.
        val (text, _) = replay(
            listOf(
                FakeSession(partials = listOf("papa"), final = "papa ko"),
                FakeSession(partials = listOf("seene", "seene mein dard"), final = "seene mein dard"),
                FakeSession(final = "aur saans nahi aa rahi")
            )
        )
        assertEquals("papa ko seene mein dard aur saans nahi aa rahi", text)
    }

    @Test
    fun partialReplacesInsteadOfAppending() {
        val buffer = TranscriptBuffer()
        buffer.setPartial("papa")
        buffer.setPartial("papa ko")
        assertEquals("papa ko", buffer.display())
        buffer.commit("papa ko")
        assertEquals("papa ko", buffer.display())
        buffer.setPartial("seene")
        assertEquals("papa ko seene", buffer.display())
    }

    @Test
    fun restartPolicyKeepsGoingWhileListening() {
        assertTrue(VoiceRestartPolicy.shouldContinue(VoiceEvent.RESULTS, true))
        assertTrue(VoiceRestartPolicy.shouldContinue(VoiceEvent.NO_MATCH, true))
        assertTrue(VoiceRestartPolicy.shouldContinue(VoiceEvent.SPEECH_TIMEOUT, true))
        assertTrue(VoiceRestartPolicy.shouldContinue(VoiceEvent.CLIENT_ERROR, true))
        assertFalse(VoiceRestartPolicy.shouldContinue(VoiceEvent.FATAL_ERROR, true))
    }

    @Test
    fun noRestartAfterUserTapsStop() {
        for (event in VoiceEvent.values()) {
            assertFalse("event $event must not restart after stop",
                VoiceRestartPolicy.shouldContinue(event, false))
        }
    }

    @Test
    fun errorClientAfterStopIsNormalAndKeepsText() {
        // User tapped stop before the last (empty) session; ERROR_CLIENT must be
        // a normal end, not an error, and the earlier text is preserved.
        val (text, restarts) = replay(
            listOf(
                FakeSession(final = "papa ko seene mein dard"),
                FakeSession(error = VoiceEvent.CLIENT_ERROR)
            ),
            stopBeforeSession = 1
        )
        assertEquals("papa ko seene mein dard", text)
        assertEquals(listOf(true, false), restarts)
    }

    @Test
    fun noSpeechProducesEmptyText() {
        val buffer = TranscriptBuffer()
        buffer.setPartial("")
        assertEquals("", buffer.finish())
        assertTrue(buffer.isEmpty())
    }
}
