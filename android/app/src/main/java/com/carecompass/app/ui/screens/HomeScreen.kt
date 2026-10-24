package com.carecompass.app.ui.screens

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.carecompass.app.ui.components.BigButton
import com.carecompass.app.ui.components.LanguageToggle
import com.carecompass.app.ui.components.MicButton
import com.carecompass.app.ui.theme.EmergencyRed
import com.carecompass.app.ui.theme.PrimaryBlue
import com.carecompass.app.viewmodel.TriageViewModel

@Composable
fun HomeScreen(
    viewModel: TriageViewModel,
    uiState: com.carecompass.app.viewmodel.TriageUiState,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    var inputText by remember { mutableStateOf("") }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(Color(0xFFF8F9FA))
            .padding(20.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.SpaceBetween
    ) {
        // Top section: Language & Emergency Bar
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "CareCompass",
                    fontSize = 26.sp,
                    fontWeight = FontWeight.ExtraBold,
                    color = PrimaryBlue
                )
                LanguageToggle(
                    selectedLanguage = uiState.selectedLanguage,
                    onLanguageSelected = { viewModel.setLanguage(it) }
                )
            }

            Spacer(modifier = Modifier.height(16.dp))

            // Dedicated Red Emergency Call Button (Dials 112)
            Button(
                onClick = {
                    val intent = Intent(Intent.ACTION_DIAL, Uri.parse("tel:112"))
                    context.startActivity(intent)
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .height(52.dp),
                shape = RoundedCornerShape(12.dp),
                colors = ButtonDefaults.buttonColors(containerColor = EmergencyRed)
            ) {
                Icon(
                    imageVector = Icons.Default.Warning,
                    contentDescription = "Emergency",
                    tint = Color.White
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = "Emergency: Call 112",
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Bold,
                    color = Color.White
                )
            }
        }

        // Center section: Mic Button & Large Action Text
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.padding(vertical = 24.dp)
        ) {
            Text(
                text = "What is the problem?",
                fontSize = 24.sp,
                fontWeight = FontWeight.Bold,
                textAlign = TextAlign.Center
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = "Tap the mic and speak in Hindi, English, or Hinglish",
                fontSize = 17.sp,
                color = Color(0xFF616161),
                textAlign = TextAlign.Center
            )

            Spacer(modifier = Modifier.height(28.dp))

            MicButton(
                onClick = {
                    // Demo utterance if device STT is triggered or mock
                    viewModel.submitUserInput("Papa ko do din se bukhar hai aur khansi bhi")
                }
            )

            Spacer(modifier = Modifier.height(16.dp))
            Text(
                text = "Tap & Speak",
                fontSize = 18.sp,
                fontWeight = FontWeight.SemiBold,
                color = PrimaryBlue
            )
        }

        // Bottom section: Typing Input Fallback
        Column(modifier = Modifier.fillMaxWidth()) {
            if (uiState.isLoading) {
                Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = PrimaryBlue)
                }
                Spacer(modifier = Modifier.height(12.dp))
            }

            if (uiState.errorMessage != null) {
                Text(
                    text = uiState.errorMessage,
                    color = EmergencyRed,
                    fontSize = 15.sp,
                    modifier = Modifier.padding(bottom = 8.dp)
                )
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically
            ) {
                OutlinedTextField(
                    value = inputText,
                    onValueChange = { inputText = it },
                    placeholder = { Text("Or type symptoms here...", fontSize = 16.sp) },
                    modifier = Modifier.weight(1f),
                    shape = RoundedCornerShape(12.dp),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = PrimaryBlue,
                        unfocusedBorderColor = Color(0xFFBDBDBD)
                    ),
                    maxLines = 3
                )
                Spacer(modifier = Modifier.width(8.dp))
                IconButton(
                    onClick = {
                        if (inputText.isNotBlank()) {
                            viewModel.submitUserInput(inputText.trim())
                            inputText = ""
                        }
                    },
                    modifier = Modifier
                        .size(54.dp)
                        .background(PrimaryBlue, RoundedCornerShape(12.dp))
                ) {
                    Icon(
                        imageVector = Icons.Default.Send,
                        contentDescription = "Send",
                        tint = Color.White
                    )
                }
            }
        }
    }
}
