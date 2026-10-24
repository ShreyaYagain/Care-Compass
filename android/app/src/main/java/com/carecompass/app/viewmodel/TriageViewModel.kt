package com.carecompass.app.viewmodel

import android.util.Log
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.carecompass.app.BuildConfig
import com.carecompass.app.data.*
import com.carecompass.app.util.DateTimeFormatterHelper
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

sealed class ScreenDestination {
    object Home : ScreenDestination()
    object Chat : ScreenDestination()
    object Emergency : ScreenDestination()
    object Result : ScreenDestination()
    data class Booking(val caregiverId: String) : ScreenDestination()
    object BookingConfirmed : ScreenDestination()
    object BookingFlow : ScreenDestination()
    object BookServices : ScreenDestination()
}

data class TriageUiState(
    val selectedLanguage: String = "hinglish",
    val isLoading: Boolean = false,
    val conversationHistory: List<ChatMessage> = emptyList(),
    val currentQuestion: String? = null,
    val currentOptions: List<String> = emptyList(),
    val latestResponse: TriageResponse? = null,
    val emergencyInfo: EmergencyInfo? = null,
    val emergencySteps: List<String> = emptyList(),
    val bookingResponse: BookingResponse? = null,
    val errorMessage: String? = null,
    val destination: ScreenDestination = ScreenDestination.Home,
    val contextConsent: Boolean = true,
    val userLocation: Location? = Location(lat = 28.54, lng = 77.27)
)

class TriageViewModel(
    private val repository: Repository = Repository(ApiService.create())
) : ViewModel() {

    private val _uiState = MutableStateFlow(TriageUiState())
    val uiState: StateFlow<TriageUiState> = _uiState.asStateFlow()

    fun setLanguage(lang: String) {
        _uiState.value = _uiState.value.copy(selectedLanguage = lang)
    }

    fun setContextConsent(consent: Boolean) {
        _uiState.value = _uiState.value.copy(contextConsent = consent)
    }

    fun setLocation(lat: Double, lng: Double) {
        _uiState.value = _uiState.value.copy(userLocation = Location(lat = lat, lng = lng))
    }

    private fun getCurrentClientTime(): String? {
        return try {
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
                java.time.OffsetDateTime.now().toString()
            } else {
                null
            }
        } catch (e: Exception) {
            null
        }
    }

    // Debug-only request-body logging. Never logs personal data (user input,
    // conversation text, or precise location are omitted/redacted).
    private fun logTriageRequest(tag: String, req: TriageRequest) {
        if (!BuildConfig.DEBUG) return
        Log.d(tag, "Triage request -> language=${req.language}, " +
            "historyTurns=${req.conversationHistory.size}, " +
            "contextConsent=${req.contextConsent}, " +
            "hasLocation=${req.location != null}, " +
            "hasPatient=${req.patient != null}, " +
            "clientTime=${req.clientTime ?: "null"}")
    }

    fun triggerEmergencyImmediately(symptomText: String) {
        val trimmed = symptomText.trim()
        val defaultSteps = listOf(
            "Call 112 (National Emergency) immediately.",
            "Keep the patient calm, resting, and sitting or lying down comfortably.",
            "Do not give food or drink if patient is breathless, drowsy, or having chest pain.",
            "If unconscious or breathing with difficulty, keep airway clear and turn onto side (recovery position)."
        )

        val updatedHistory = _uiState.value.conversationHistory + ChatMessage(role = "user", text = trimmed, content = trimmed)

        _uiState.value = _uiState.value.copy(
            destination = ScreenDestination.Emergency,
            emergencySteps = defaultSteps,
            conversationHistory = updatedHistory,
            isLoading = false
        )

        // Background call to /triage without delaying UI
        viewModelScope.launch {
            try {
                val state = _uiState.value
                val req = TriageRequest(
                    userInput = trimmed,
                    language = state.selectedLanguage,
                    location = if (state.contextConsent) state.userLocation else null,
                    conversationHistory = updatedHistory,
                    clientTime = getCurrentClientTime(),
                    contextConsent = state.contextConsent
                )
                logTriageRequest("Triage", req)
                repository.triage(req).onSuccess { resp ->
                    if (resp.emergencySteps.isNotEmpty()) {
                        _uiState.value = _uiState.value.copy(emergencySteps = resp.emergencySteps)
                    }
                }
            } catch (e: Exception) {
                // Background error ignored
            }
        }
    }

    fun submitUserInput(text: String) {
        val trimmed = text.trim()
        // BUG 1 fix: Never call /triage with an empty user_input
        if (trimmed.isBlank()) {
            return
        }

        val state = _uiState.value
        val updatedHistory = state.conversationHistory + ChatMessage(role = "user", text = trimmed, content = trimmed)

        _uiState.value = state.copy(
            isLoading = true,
            conversationHistory = updatedHistory,
            errorMessage = null
        )

        viewModelScope.launch {
            val req = TriageRequest(
                userInput = trimmed,
                language = state.selectedLanguage,
                location = if (state.contextConsent) state.userLocation else null,
                conversationHistory = updatedHistory,
                clientTime = getCurrentClientTime(),
                contextConsent = state.contextConsent
            )
            logTriageRequest("Triage", req)

            repository.triage(req).fold(
                onSuccess = { resp ->
                    handleTriageResponse(resp)
                },
                onFailure = { err ->
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        errorMessage = err.localizedMessage ?: "Connection error. Please try again."
                    )
                }
            )
        }
    }

    private fun handleTriageResponse(response: TriageResponse) {
        val currentHistory = _uiState.value.conversationHistory.toMutableList()

        val isEmergency = response.redFlags.isNotEmpty() ||
                response.careType == "emergency_112"

        if (isEmergency) {
            val steps = if (response.emergencySteps.isNotEmpty()) {
                response.emergencySteps
            } else {
                response.emergency?.steps ?: emptyList()
            }
            _uiState.value = _uiState.value.copy(
                isLoading = false,
                latestResponse = response,
                emergencyInfo = response.emergency,
                emergencySteps = steps,
                destination = ScreenDestination.Emergency
            )
            return
        }

        if (!response.followUpQuestion.isNullOrBlank()) {
            currentHistory.add(ChatMessage(role = "assistant", text = response.followUpQuestion, content = response.followUpQuestion))
            _uiState.value = _uiState.value.copy(
                isLoading = false,
                conversationHistory = currentHistory,
                currentQuestion = response.followUpQuestion,
                currentOptions = response.followUpOptions,
                latestResponse = response,
                destination = ScreenDestination.Chat
            )
            return
        }

        // Final triage decision
        _uiState.value = _uiState.value.copy(
            isLoading = false,
            latestResponse = response,
            destination = ScreenDestination.Result
        )
    }

    fun startBooking(caregiverId: String) {
        _uiState.value = _uiState.value.copy(
            destination = ScreenDestination.Booking(caregiverId)
        )
    }

    fun navigateToBookingFlow() {
        _uiState.value = _uiState.value.copy(
            destination = ScreenDestination.BookingFlow
        )
    }

    fun navigateToBookServices() {
        _uiState.value = _uiState.value.copy(
            destination = ScreenDestination.BookServices
        )
    }

    fun navigateToEmergency(emergencyResponse: TriageResponse? = null) {
        val steps = emergencyResponse?.emergencySteps?.ifEmpty { null }
            ?: emergencyResponse?.emergency?.steps?.ifEmpty { null }
            ?: listOf(
                "Call 112 (National Emergency) immediately.",
                "Keep the patient calm, resting, and sitting or lying down comfortably.",
                "Do not give food or drink if patient is breathless, drowsy, or having chest pain.",
                "If unconscious or breathing with difficulty, keep airway clear and turn onto side (recovery position)."
            )

        _uiState.value = _uiState.value.copy(
            destination = ScreenDestination.Emergency,
            latestResponse = emergencyResponse ?: _uiState.value.latestResponse,
            emergencySteps = steps,
            emergencyInfo = emergencyResponse?.emergency ?: _uiState.value.emergencyInfo,
            isLoading = false
        )
    }

    fun navigateToHome() {
        _uiState.value = _uiState.value.copy(
            destination = ScreenDestination.Home
        )
    }

    fun confirmBooking(
        caregiverId: String,
        name: String,
        phone: String,
        slot: String,
        patientName: String? = null,
        relation: String? = null
    ) {
        _uiState.value = _uiState.value.copy(isLoading = true)

        // Slot keys look like "today_15_30" or "tomorrow_9_0" (90-minute slots).
        val parts = slot.split("_")
        val dayOffset = if (parts.getOrNull(0) == "tomorrow") 1 else 0
        val slotHour = parts.getOrNull(1)?.toIntOrNull() ?: 9
        val slotMinute = parts.getOrNull(2)?.toIntOrNull() ?: 0
        val startTime = DateTimeFormatterHelper.buildBookingIso(dayOffset, slotHour, slotMinute)
        val endTime = DateTimeFormatterHelper.buildBookingIso(dayOffset, slotHour, slotMinute, 90)

        viewModelScope.launch {
            val req = BookingRequest(
                caregiverId = caregiverId,
                slot = slot,
                userName = name,
                phone = phone,
                triageSummary = _uiState.value.latestResponse?.reasoning,
                patientName = patientName ?: name,
                relation = relation,
                careType = _uiState.value.latestResponse?.careType ?: "paramedic_home_visit",
                startTime = startTime,
                endTime = endTime
            )
            repository.createBooking(req).fold(
                onSuccess = { bResp ->
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        bookingResponse = bResp,
                        destination = ScreenDestination.BookingConfirmed
                    )
                },
                onFailure = { err ->
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        errorMessage = err.localizedMessage
                    )
                }
            )
        }
    }

    fun reset() {
        _uiState.value = TriageUiState()
    }
}
