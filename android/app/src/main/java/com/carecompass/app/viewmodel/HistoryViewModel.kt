package com.carecompass.app.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.carecompass.app.data.HistoryDetail
import com.carecompass.app.data.HistorySummary
import com.carecompass.app.data.Repository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class HistoryUiState(
    val isLoading: Boolean = false,
    val isRefreshing: Boolean = false,
    val historyItems: List<HistorySummary> = emptyList(),
    val selectedDetail: HistoryDetail? = null,
    val isLoadingDetail: Boolean = false,
    val errorMessage: String? = null,
    val isOfflineCached: Boolean = false,
    val showDeleteConfirmDialog: Boolean = false,
    val itemPendingDelete: String? = null
)

class HistoryViewModel(
    private val repository: Repository
) : ViewModel() {

    private val _uiState = MutableStateFlow(HistoryUiState())
    val uiState: StateFlow<HistoryUiState> = _uiState.asStateFlow()

    init {
        loadHistory()
    }

    fun loadHistory(isRefresh: Boolean = false) {
        _uiState.value = _uiState.value.copy(
            isLoading = !isRefresh,
            isRefreshing = isRefresh,
            errorMessage = null
        )

        viewModelScope.launch {
            repository.getHistory(limit = 5).fold(
                onSuccess = { items ->
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        isRefreshing = false,
                        historyItems = items,
                        errorMessage = null,
                        isOfflineCached = false
                    )
                },
                onFailure = { err ->
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        isRefreshing = false,
                        errorMessage = err.localizedMessage ?: "Unable to load chats. Please try again."
                    )
                }
            )
        }
    }

    fun selectHistoryItem(id: String) {
        _uiState.value = _uiState.value.copy(isLoadingDetail = true, errorMessage = null)
        viewModelScope.launch {
            repository.getHistoryDetail(id).fold(
                onSuccess = { detail ->
                    _uiState.value = _uiState.value.copy(
                        isLoadingDetail = false,
                        selectedDetail = detail
                    )
                },
                onFailure = { err ->
                    _uiState.value = _uiState.value.copy(
                        isLoadingDetail = false,
                        errorMessage = err.localizedMessage ?: "Failed to open chat details."
                    )
                }
            )
        }
    }

    fun clearSelectedDetail() {
        _uiState.value = _uiState.value.copy(selectedDetail = null)
    }

    fun promptDelete(id: String) {
        _uiState.value = _uiState.value.copy(
            showDeleteConfirmDialog = true,
            itemPendingDelete = id
        )
    }

    fun dismissDeleteDialog() {
        _uiState.value = _uiState.value.copy(
            showDeleteConfirmDialog = false,
            itemPendingDelete = null
        )
    }

    fun confirmDelete(onDeleted: () -> Unit) {
        val id = _uiState.value.itemPendingDelete ?: _uiState.value.selectedDetail?.id ?: return
        dismissDeleteDialog()
        _uiState.value = _uiState.value.copy(isLoading = true)

        viewModelScope.launch {
            repository.deleteHistory(id).fold(
                onSuccess = {
                    val updated = _uiState.value.historyItems.filter { it.id != id }
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        historyItems = updated,
                        selectedDetail = null
                    )
                    onDeleted()
                },
                onFailure = { err ->
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        errorMessage = err.localizedMessage ?: "Failed to delete chat."
                    )
                }
            )
        }
    }
}
