package com.carecompass.app.ui.screens

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.carecompass.app.R
import com.carecompass.app.ui.components.BigButton
import com.carecompass.app.ui.components.LanguageToggle
import com.carecompass.app.ui.components.MicButton
import com.carecompass.app.ui.theme.EmergencyRed
import com.carecompass.app.ui.theme.PrimaryBlue
import com.carecompass.app.util.MicState
import com.carecompass.app.util.SpeechHelper
import com.carecompass.app.viewmodel.TriageUiState
import com.carecompass.app.viewmodel.TriageViewModel

private data class SymptomOption(
    val id: String,
    val icon: ImageVector,
    val canonicalKeyword: String,
    val labelEnRes: Int,
    val labelHiRes: Int,
    val labelHinglishRes: Int
)

private val SYMPTOM_OPTIONS = listOf(
    SymptomOption("fever_cough", Icons.Default.Whatshot, "fever and cough", R.string.symptom_service_fever_cough_en, R.string.symptom_service_fever_cough_hi, R.string.symptom_service_fever_cough_hinglish),
    SymptomOption("pain_injury", Icons.Default.Healing, "severe pain and injury wound", R.string.symptom_service_pain_injury_en, R.string.symptom_service_pain_injury_hi, R.string.symptom_service_pain_injury_hinglish),
    SymptomOption("nursing", Icons.Default.MedicalServices, "ghar pe IM injection lagwana hai dressing", R.string.symptom_service_nursing_en, R.string.symptom_service_nursing_hi, R.string.symptom_service_nursing_hinglish),
    SymptomOption("lab_test", Icons.Default.Science, "full body checkup home collection", R.string.symptom_service_lab_test_en, R.string.symptom_service_lab_test_hi, R.string.symptom_service_lab_test_hinglish),
    SymptomOption("doctor", Icons.Default.Psychology, "doctor chahiye consult", R.string.symptom_service_doctor_consult_en, R.string.symptom_service_doctor_consult_hi, R.string.symptom_service_doctor_consult_hinglish),
    SymptomOption("elderly_weak", Icons.Default.Person, "elderly weak patient home visit", R.string.symptom_service_elderly_weak_en, R.string.symptom_service_elderly_weak_hi, R.string.symptom_service_elderly_weak_hinglish)
)

@Composable
fun HomeScreen(
    viewModel: TriageViewModel,
    uiState: TriageUiState,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    var inputText by remember { mutableStateOf("") }
    var micState by remember { mutableStateOf(MicState.IDLE) }
    var userMessage by remember { mutableStateOf<String?>(null) }
    val selectedSymptoms = remember { mutableStateListOf<String>() }

    // SpeechRecognizer Helper
    val speechHelper = remember {
        SpeechHelper(
            context = context,
            onStateChanged = { state -> micState = state },
            onPartialResult = { partial ->
                // Show partial results live in the text box
                inputText = partial
            },
            onFinalResult = { finalResult ->
                inputText = finalResult
                // Put text in box, then call /triage (BUG 1 fixed: non-empty only)
                if (finalResult.isNotBlank()) {
                    viewModel.submitUserInput(finalResult)
                }
            },
            onError = { errMsg ->
                userMessage = errMsg
            }
        )
    }

    DisposableEffect(Unit) {
        onDispose {
            speechHelper.destroy()
        }
    }

    // Runtime Permission for Microphone
    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            userMessage = null
            speechHelper.startListening(uiState.selectedLanguage)
        } else {
            userMessage = "Please allow the microphone, or type your symptoms"
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
            .padding(16.dp)
            .verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        // Top section: Language & Emergency Bar
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = "CareCompass",
                fontSize = 24.sp,
                fontWeight = FontWeight.ExtraBold,
                color = PrimaryBlue
            )
            LanguageToggle(
                selectedLanguage = uiState.selectedLanguage,
                onLanguageSelected = { viewModel.setLanguage(it) }
            )
        }

        Spacer(modifier = Modifier.height(14.dp))

        // Dedicated Red Emergency Call Button (Dials 112, min 56dp)
        Button(
            onClick = {
                val intent = Intent(Intent.ACTION_DIAL, Uri.parse("tel:112"))
                context.startActivity(intent)
            },
            modifier = Modifier
                .fillMaxWidth()
                .height(56.dp),
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

        Spacer(modifier = Modifier.height(20.dp))

        // Center Heading
        Text(
            text = "What is the problem?",
            fontSize = 24.sp,
            fontWeight = FontWeight.Bold,
            color = Color(0xFF212121),
            textAlign = TextAlign.Center
        )

        Spacer(modifier = Modifier.height(14.dp))

        // FEATURE 2: 2-column Symptom Grid (min 72dp per button, multi-select)
        Column(
            modifier = Modifier.fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            for (i in SYMPTOM_OPTIONS.indices step 2) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    for (j in 0..1) {
                        if (i + j < SYMPTOM_OPTIONS.size) {
                            val symptom = SYMPTOM_OPTIONS[i + j]
                            val isSelected = selectedSymptoms.contains(symptom.id)

                            val label = when (uiState.selectedLanguage) {
                                "hi" -> stringResource(symptom.labelHiRes)
                                "hinglish" -> stringResource(symptom.labelHinglishRes)
                                else -> stringResource(symptom.labelEnRes)
                            }

                            Card(
                                modifier = Modifier
                                    .weight(1f)
                                    .heightIn(min = 72.dp)
                                    .clickable {
                                        if (isSelected) {
                                            selectedSymptoms.remove(symptom.id)
                                        } else {
                                            selectedSymptoms.add(symptom.id)
                                        }
                                    },
                                shape = RoundedCornerShape(12.dp),
                                colors = CardDefaults.cardColors(
                                    containerColor = if (isSelected) PrimaryBlue else Color.White
                                ),
                                border = BorderStroke(
                                    width = if (isSelected) 2.dp else 1.dp,
                                    color = if (isSelected) PrimaryBlue else Color(0xFFD1D5DB)
                                ),
                                elevation = CardDefaults.cardElevation(defaultElevation = if (isSelected) 4.dp else 1.dp)
                            ) {
                                Row(
                                    modifier = Modifier
                                        .fillMaxSize()
                                        .padding(horizontal = 10.dp, vertical = 12.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                    horizontalArrangement = Arrangement.Start
                                ) {
                                    Icon(
                                        imageVector = symptom.icon,
                                        contentDescription = label,
                                        tint = if (isSelected) Color.White else PrimaryBlue,
                                        modifier = Modifier.size(28.dp)
                                    )
                                    Spacer(modifier = Modifier.width(8.dp))
                                    Text(
                                        text = label,
                                        fontSize = 18.sp,
                                        fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium,
                                        color = if (isSelected) Color.White else Color(0xFF1F2937),
                                        lineHeight = 22.sp
                                    )
                                }
                            }
                        } else {
                            Spacer(modifier = Modifier.weight(1f))
                        }
                    }
                }
            }
        }

        // Multi-select "Continue" button appears when at least one is selected
        if (selectedSymptoms.isNotEmpty()) {
            Spacer(modifier = Modifier.height(14.dp))
            BigButton(
                text = "Continue with Selected Symptoms",
                onClick = {
                    val canonicalList = SYMPTOM_OPTIONS
                        .filter { selectedSymptoms.contains(it.id) }
                        .map { it.canonicalKeyword }
                    val query = canonicalList.joinToString(", ")
                    if (query.isNotBlank()) {
                        inputText = query
                        viewModel.submitUserInput(query)
                    }
                },
                containerColor = Color(0xFF2E7D32) // Positive green for continue
            )
        }

        Spacer(modifier = Modifier.height(20.dp))

        // Mic Section with pulsing animation and real SpeechRecognizer
        MicButton(
            state = micState,
            onClick = { handleMicTap() }
        )

        Spacer(modifier = Modifier.height(16.dp))

        // Friendly error or permission message banner
        if (userMessage != null) {
            Surface(
                color = Color(0xFFFFF3E0),
                shape = RoundedCornerShape(8.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 10.dp)
            ) {
                Text(
                    text = userMessage!!,
                    color = Color(0xFFE65100),
                    fontSize = 18.sp,
                    modifier = Modifier.padding(12.dp),
                    textAlign = TextAlign.Center
                )
            }
        }

        if (uiState.isLoading) {
            Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = PrimaryBlue)
            }
            Spacer(modifier = Modifier.height(10.dp))
        }

        // Bottom: Text input box with send button (min height 56dp)
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            OutlinedTextField(
                value = inputText,
                onValueChange = { inputText = it },
                placeholder = { Text("Or type symptoms here...", fontSize = 18.sp) },
                modifier = Modifier
                    .weight(1f)
                    .heightIn(min = 56.dp),
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
                    val trimmed = inputText.trim()
                    if (trimmed.isNotBlank()) {
                        viewModel.submitUserInput(trimmed)
                        inputText = ""
                    }
                },
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

        Spacer(modifier = Modifier.height(16.dp))
    }
}
