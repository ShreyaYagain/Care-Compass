package com.carecompass.app.ui.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import com.carecompass.app.ui.screens.*
import com.carecompass.app.viewmodel.ScreenDestination
import com.carecompass.app.viewmodel.TriageViewModel

@Composable
fun CareCompassNavGraph(
    viewModel: TriageViewModel,
    modifier: Modifier = Modifier
) {
    val uiState by viewModel.uiState.collectAsState()

    when (val dest = uiState.destination) {
        is ScreenDestination.Home -> {
            HomeScreen(
                viewModel = viewModel,
                uiState = uiState,
                modifier = modifier
            )
        }
        is ScreenDestination.Chat -> {
            ChatScreen(
                viewModel = viewModel,
                uiState = uiState,
                modifier = modifier
            )
        }
        is ScreenDestination.Emergency -> {
            EmergencyScreen(
                uiState = uiState,
                onReset = { viewModel.reset() },
                modifier = modifier
            )
        }
        is ScreenDestination.Result -> {
            ResultScreen(
                uiState = uiState,
                onBookCaregiver = { cgId -> viewModel.startBooking(cgId) },
                onStartOver = { viewModel.reset() },
                modifier = modifier
            )
        }
        is ScreenDestination.Booking -> {
            BookingScreen(
                caregiverId = dest.caregiverId,
                viewModel = viewModel,
                uiState = uiState,
                onDone = { viewModel.reset() },
                modifier = modifier
            )
        }
        is ScreenDestination.BookingConfirmed -> {
            BookingScreen(
                caregiverId = uiState.bookingResponse?.caregiverId ?: "",
                viewModel = viewModel,
                uiState = uiState,
                onDone = { viewModel.reset() },
                modifier = modifier
            )
        }
    }
}
