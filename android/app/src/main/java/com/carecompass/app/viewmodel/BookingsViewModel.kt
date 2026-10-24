package com.carecompass.app.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.carecompass.app.data.Booking
import com.carecompass.app.data.Repository
import com.carecompass.app.util.DateTimeFormatterHelper
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class BookingsUiState(
    val isLoading: Boolean = false,
    val isRefreshing: Boolean = false,
    val upcomingBookings: List<Booking> = emptyList(),
    val pastBookings: List<Booking> = emptyList(),
    val isPastExpanded: Boolean = false,
    val errorMessage: String? = null,
    val bookingPendingCancel: Booking? = null,
    val showCancelConfirmDialog: Boolean = false
)

class BookingsViewModel(
    private val repository: Repository
) : ViewModel() {

    private val _uiState = MutableStateFlow(BookingsUiState())
    val uiState: StateFlow<BookingsUiState> = _uiState.asStateFlow()

    init {
        loadBookings()
    }

    fun loadBookings(isRefresh: Boolean = false) {
        _uiState.value = _uiState.value.copy(
            isLoading = !isRefresh,
            isRefreshing = isRefresh,
            errorMessage = null
        )

        viewModelScope.launch {
            repository.getBookings("all").fold(
                onSuccess = { allBookings ->
                    // Sort ascending by start_time
                    val sorted = allBookings.sortedBy { it.startTime }
                    val upcoming = sorted.filter {
                        (it.status == "confirmed" || it.status == "pending") &&
                                !DateTimeFormatterHelper.isPastBooking(it.endTime)
                    }
                    val past = sorted.filter {
                        it.status == "completed" || it.status == "cancelled" ||
                                DateTimeFormatterHelper.isPastBooking(it.endTime)
                    }.sortedByDescending { it.endTime }

                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        isRefreshing = false,
                        upcomingBookings = upcoming,
                        pastBookings = past,
                        errorMessage = null
                    )
                },
                onFailure = { err ->
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        isRefreshing = false,
                        errorMessage = err.localizedMessage ?: "Failed to load bookings. Please retry."
                    )
                }
            )
        }
    }

    fun togglePastExpanded() {
        _uiState.value = _uiState.value.copy(isPastExpanded = !_uiState.value.isPastExpanded)
    }

    fun promptCancel(booking: Booking) {
        _uiState.value = _uiState.value.copy(
            bookingPendingCancel = booking,
            showCancelConfirmDialog = true
        )
    }

    fun dismissCancelDialog() {
        _uiState.value = _uiState.value.copy(
            bookingPendingCancel = null,
            showCancelConfirmDialog = false
        )
    }

    fun confirmCancel() {
        val b = _uiState.value.bookingPendingCancel ?: return
        dismissCancelDialog()
        _uiState.value = _uiState.value.copy(isLoading = true)

        viewModelScope.launch {
            repository.cancelBooking(b.id).fold(
                onSuccess = { cancelled ->
                    val updatedUpcoming = _uiState.value.upcomingBookings.filter { it.id != b.id }
                    val updatedPast = listOf(cancelled) + _uiState.value.pastBookings
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        upcomingBookings = updatedUpcoming,
                        pastBookings = updatedPast
                    )
                },
                onFailure = { err ->
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        errorMessage = err.localizedMessage ?: "Unable to cancel booking."
                    )
                }
            )
        }
    }
}
