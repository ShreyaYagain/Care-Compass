package com.carecompass.app.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.carecompass.app.data.*
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
}

data class TriageUiState(
    val selectedLanguage: String = "hinglish",
    val isLoading: Boolean = false,
    val conversationHistory: List<ChatMessage> = emptyList(),
    val currentQuestion: String? = null,
    val currentOptions: List<String> = emptyList(),
    val latestResponse: TriageResponse? = null,
    val emergencyInfo: EmergencyInfo? = null,
    val bookingResponse: BookingResponse? = null,
    val errorMessage: String? = null,
    val destination: ScreenDestination = ScreenDestination.Home
)

class TriageViewModel(
    private val repository: Repository = Repository(ApiService.create())
) : ViewModel() {

    private val _uiState = MutableStateFlow(TriageUiState())
    val uiState: StateFlow<TriageUiState> = _uiState.asStateFlow()

    fun setLanguage(lang: String) {
        _uiState.value = _uiState.value.copy(selectedLanguage = lang)
    }

    fun submitUserInput(text: String) {
        if (text.isBlank()) return

        val state = _uiState.value
        val updatedHistory = state.conversationHistory + ChatMessage(role = "user", text = text)

        _uiState.value = state.copy(
            isLoading = true,
            conversationHistory = updatedHistory,
            errorMessage = null
        )

        viewModelScope.launch {
            val req = TriageRequest(
                userInput = text,
                language = state.selectedLanguage,
                location = Location(lat = 28.54, lng = 77.27), // Hardcoded Delhi location
                conversationHistory = updatedHistory
            )

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

        if (response.emergency != null) {
            _uiState.value = _uiState.value.copy(
                isLoading = false,
                latestResponse = response,
                emergencyInfo = response.emergency,
                destination = ScreenDestination.Emergency
            )
            return
        }

        if (!response.followUpQuestion.isNullOrBlank()) {
            currentHistory.add(ChatMessage(role = "assistant", text = response.followUpQuestion))
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

    fun confirmBooking(caregiverId: String, name: String, phone: String, slot: String) {
        _uiState.value = _uiState.value.copy(isLoading = true)
        viewModelScope.launch {
            val req = BookingRequest(
                caregiverId = caregiverId,
                slot = slot,
                userName = name,
                phone = phone,
                triageSummary = _uiState.value.latestResponse?.reasoning
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
