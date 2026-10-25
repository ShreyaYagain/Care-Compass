package com.carecompass.app.ui.screens

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.carecompass.app.ui.components.BigButton
import com.carecompass.app.ui.components.MicButton
import com.carecompass.app.ui.theme.PrimaryBlue
import com.carecompass.app.util.MicState
import com.carecompass.app.util.SpeechHelper
import com.carecompass.app.viewmodel.TriageUiState
import com.carecompass.app.viewmodel.TriageViewModel
import kotlinx.coroutines.delay

@Composable
fun ChatScreen(
    viewModel: TriageViewModel,
    uiState: TriageUiState,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val question = uiState.currentQuestion ?: "Is there any difficulty in breathing?"
    val options = if (uiState.currentOptions.isNotEmpty()) {
        uiState.currentOptions
    } else {
        listOf("Yes", "No", "Not sure")
    }

    var inputText by remember { mutableStateOf("") }
    var micState by remember { mutableStateOf(MicState.IDLE) }
    var micLevel by remember { mutableStateOf(0f) }
    var elapsedSeconds by remember { mutableStateOf(0) }
    var userMessage by remember { mutableStateOf<String?>(null) }

    // SpeechRecognizer Helper for follow-up answering
    val speechHelper = remember {
        SpeechHelper(
            context = context,
            onStateChanged = { state -> micState = state },
            onPartialResult = { partial ->
                inputText = partial
            },
            onFinalResult = { finalResult ->
                // Never auto-send: fill the box so the user can review/edit and press Send.
                inputText = finalResult
                if (finalResult.isNotBlank()) {
                    userMessage = "Transcription ready — check it, then press send."
                }
            },
            onError = { errMsg ->
                userMessage = errMsg
            },
            onLevelChanged = { level -> micLevel = level }
        )
    }

    LaunchedEffect(micState) {
        if (micState == MicState.LISTENING) {
            elapsedSeconds = 0
            while (true) {
                delay(1000)
                elapsedSeconds += 1
            }
        } else {
            micLevel = 0f
        }
    }

    DisposableEffect(Unit) {
        onDispose {
            speechHelper.destroy()
        }
    }

    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            userMessage = null
            speechHelper.startListening(uiState.selectedLanguage)
        } else {
            userMessage = "Please allow the microphone, or type your response"
            micState = MicState.IDLE
        }
    }

    fun handleMicTap() {
        if (micState == MicState.LISTENING) {
            speechHelper.stopListening()
            return
        }
        userMessage = null
        val permissionCheck = ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO)
        if (permissionCheck == PackageManager.PERMISSION_GRANTED) {
            speechHelper.startListening(uiState.selectedLanguage)
        } else {
            permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(Color(0xFFF8F9FA))
            .padding(18.dp)
            .verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.SpaceBetween
    ) {
        // Visible error banner (e.g. parse fallback) — never a silent blank.
        val errorMessage = uiState.errorMessage
        if (!errorMessage.isNullOrBlank()) {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = Color(0xFFFFEBEE))
            ) {
                Text(
                    text = errorMessage,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = Color(0xFFB71C1C),
                    modifier = Modifier.padding(12.dp)
                )
            }
            Spacer(modifier = Modifier.height(10.dp))
        }

        // Question Header Card
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = Color.White),
            elevation = CardDefaults.cardElevation(defaultElevation = 3.dp)
        ) {
            Column(modifier = Modifier.padding(20.dp)) {
                Text(
                    text = "Follow-up Question",
                    fontSize = 18.sp,
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

        Spacer(modifier = Modifier.height(20.dp))

        // Options: neutral colors (NOT red), high-contrast white text, min 56dp
        Column(
            modifier = Modifier.fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            options.forEach { opt ->
                val (btnColor, textColor) = when (opt.trim().lowercase()) {
                    "yes", "haan" -> Pair(PrimaryBlue, Color.White) // Neutral primary blue, NOT red
                    "no", "nahi" -> Pair(Color(0xFF37474F), Color.White) // Deep blue-grey
                    else -> Pair(Color(0xFF546E7A), Color.White) // Medium slate
                }

                BigButton(
                    text = opt,
                    onClick = {
                        viewModel.submitUserInput(opt)
                    },
                    containerColor = btnColor,
                    contentColor = textColor
                )
            }
        }

        Spacer(modifier = Modifier.height(24.dp))

        // Mic available for voice reply
        MicButton(
            state = micState,
            onClick = { handleMicTap() },
            elapsedSeconds = elapsedSeconds,
            level = micLevel
        )

        if (userMessage != null) {
            Spacer(modifier = Modifier.height(10.dp))
            Surface(
                color = Color(0xFFFFF3E0),
                shape = RoundedCornerShape(8.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(
                    text = userMessage!!,
                    color = Color(0xFFE65100),
                    fontSize = 18.sp,
                    modifier = Modifier.padding(10.dp)
                )
            }
        }

        if (uiState.isLoading) {
            Spacer(modifier = Modifier.height(14.dp))
            CircularProgressIndicator(color = PrimaryBlue)
        }

        Spacer(modifier = Modifier.height(20.dp))

        // Fallback text input (min 56dp)
        val submitAnswer = {
            val trimmed = inputText.trim()
            if (trimmed.isNotBlank()) {
                viewModel.submitUserInput(trimmed)
                inputText = ""
            }
        }

        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            OutlinedTextField(
                value = inputText,
                onValueChange = { inputText = it },
                placeholder = { Text("Or type answer...", fontSize = 18.sp) },
                modifier = Modifier
                    .weight(1f)
                    .heightIn(min = 56.dp),
                shape = RoundedCornerShape(12.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = PrimaryBlue,
                    unfocusedBorderColor = Color(0xFFBDBDBD)
                ),
                maxLines = 2,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(onSend = { submitAnswer() })
            )
            Spacer(modifier = Modifier.width(8.dp))
            IconButton(
                onClick = { submitAnswer() },
                modifier = Modifier
                    .size(56.dp)
                    .clip(RoundedCornerShape(12.dp))
                    .background(PrimaryBlue)
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
