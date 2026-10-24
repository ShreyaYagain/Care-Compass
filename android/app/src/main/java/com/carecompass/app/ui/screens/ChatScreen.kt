package com.carecompass.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.carecompass.app.ui.components.BigButton
import com.carecompass.app.ui.components.MicButton
import com.carecompass.app.ui.theme.PrimaryBlue
import com.carecompass.app.viewmodel.TriageUiState
import com.carecompass.app.viewmodel.TriageViewModel

@Composable
fun ChatScreen(
    viewModel: TriageViewModel,
    uiState: TriageUiState,
    modifier: Modifier = Modifier
) {
    val question = uiState.currentQuestion ?: "Is there any difficulty in breathing?"
    val options = if (uiState.currentOptions.isNotEmpty()) {
        uiState.currentOptions
    } else {
        listOf("Yes", "No", "Not sure")
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(Color(0xFFF8F9FA))
            .padding(20.dp)
            .verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.SpaceBetween
    ) {
        // Question header card
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = Color.White),
            elevation = CardDefaults.cardElevation(defaultElevation = 3.dp)
        ) {
            Column(modifier = Modifier.padding(20.dp)) {
                Text(
                    text = "Doctor / Assistant Question",
                    fontSize = 15.sp,
                    color = PrimaryBlue,
                    fontWeight = FontWeight.Bold
                )
                Spacer(modifier = Modifier.height(10.dp))
                Text(
                    text = question,
                    fontSize = 24.sp,
                    fontWeight = FontWeight.Bold,
                    color = Color(0xFF212121),
                    lineHeight = 32.sp
                )
            }
        }

        Spacer(modifier = Modifier.height(24.dp))

        // Options: Big touch-friendly buttons
        Column(
            modifier = Modifier.fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            options.forEach { opt ->
                BigButton(
                    text = opt,
                    onClick = {
                        viewModel.submitUserInput(opt)
                    },
                    containerColor = when (opt.lowercase()) {
                        "yes", "haan" -> Color(0xFFD32F2F)
                        "no", "nahi" -> PrimaryBlue
                        else -> Color(0xFF5C6BC0)
                    }
                )
            }
        }

        Spacer(modifier = Modifier.height(28.dp))

        // Mic available
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            MicButton(
                onClick = {
                    viewModel.submitUserInput("Nahi, saans me koi dikkat nahi hai")
                }
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = "Or tap mic to reply",
                fontSize = 16.sp,
                color = Color(0xFF757575)
            )
        }

        if (uiState.isLoading) {
            Spacer(modifier = Modifier.height(16.dp))
            CircularProgressIndicator(color = PrimaryBlue)
        }
    }
}
