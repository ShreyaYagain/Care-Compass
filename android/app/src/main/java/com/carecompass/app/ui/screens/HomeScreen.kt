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
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
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
import androidx.compose.ui.text.input.ImeAction
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

private data class SymptomItem(
    val id: String,
    val icon: ImageVector,
    val labelEnRes: Int,
    val labelHiRes: Int,
    val labelHinglishRes: Int
)

// General symptoms (multi-select). Each tile has a DISTINCT icon; the natural
// text is built from the single map in TriageViewModel.SymptomTilePhrases.
private val GENERAL_SYMPTOMS = listOf(
    SymptomItem("fever", Icons.Default.Whatshot, R.string.symptom_fever_en, R.string.symptom_fever_hi, R.string.symptom_fever_hinglish),
    SymptomItem("cough_cold", Icons.Default.Air, R.string.symptom_cough_cold_en, R.string.symptom_cough_cold_hi, R.string.symptom_cough_cold_hinglish),
    SymptomItem("headache", Icons.Default.SentimentVeryDissatisfied, R.string.symptom_headache_en, R.string.symptom_headache_hi, R.string.symptom_headache_hinglish),
    SymptomItem("stomach_pain", Icons.Default.Sick, R.string.symptom_stomach_pain_en, R.string.symptom_stomach_pain_hi, R.string.symptom_stomach_pain_hinglish),
    SymptomItem("vomiting", Icons.Default.WaterDrop, R.string.symptom_vomiting_en, R.string.symptom_vomiting_hi, R.string.symptom_vomiting_hinglish),
    SymptomItem("body_pain", Icons.Default.FitnessCenter, R.string.symptom_body_pain_en, R.string.symptom_body_pain_hi, R.string.symptom_body_pain_hinglish),
    SymptomItem("weakness", Icons.Default.BatteryAlert, R.string.symptom_weakness_en, R.string.symptom_weakness_hi, R.string.symptom_weakness_hinglish),
    SymptomItem("wound_injury", Icons.Default.Healing, R.string.symptom_wound_injury_en, R.string.symptom_wound_injury_hi, R.string.symptom_wound_injury_hinglish),
    SymptomItem("skin_problem", Icons.Default.Spa, R.string.symptom_skin_problem_en, R.string.symptom_skin_problem_hi, R.string.symptom_skin_problem_hinglish),
    SymptomItem("not_eating", Icons.Default.NoFood, R.string.symptom_not_eating_en, R.string.symptom_not_eating_hi, R.string.symptom_not_eating_hinglish)
)

@Composable
fun HomeScreen(
    viewModel: TriageViewModel,
    uiState: TriageUiState,
    onBookServices: () -> Unit,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    var inputText by remember { mutableStateOf("") }
    var micState by remember { mutableStateOf(MicState.IDLE) }
    var userMessage by remember { mutableStateOf<String?>(null) }

    val selectedSymptoms = remember { mutableStateListOf<String>() }

    var showConsentBanner by remember {
        mutableStateOf(
            context.getSharedPreferences("care_compass_prefs", android.content.Context.MODE_PRIVATE)
                .getBoolean("show_consent_banner", true)
        )
    }

    val locationPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        val granted = permissions[Manifest.permission.ACCESS_COARSE_LOCATION] == true ||
                permissions[Manifest.permission.ACCESS_FINE_LOCATION] == true
        if (granted) {
            try {
                val lm = context.getSystemService(android.content.Context.LOCATION_SERVICE) as? android.location.LocationManager
                val loc = lm?.getLastKnownLocation(android.location.LocationManager.NETWORK_PROVIDER)
                    ?: lm?.getLastKnownLocation(android.location.LocationManager.GPS_PROVIDER)
                if (loc != null) {
                    viewModel.setLocation(loc.latitude, loc.longitude)
                }
            } catch (e: Exception) {
                // Ignore fallback to default
            }
        }
    }

    // SpeechRecognizer / Fallback Helper
    val speechHelper = remember {
        SpeechHelper(
            context = context,
            onStateChanged = { state -> micState = state },
            onPartialResult = { partial ->
                inputText = partial
            },
            onFinalResult = { finalResult ->
                inputText = finalResult
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

    fun getLabel(item: SymptomItem): String {
        val resId = when (uiState.selectedLanguage) {
            "hi" -> item.labelHiRes
            "hinglish" -> item.labelHinglishRes
            else -> item.labelEnRes
        }
        return context.getString(resId)
    }

    val submitTextInput = {
        val trimmed = inputText.trim()
        if (trimmed.isNotBlank()) {
            viewModel.submitUserInput(trimmed)
            inputText = ""
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(Color(0xFFF8F9FA))
    ) {
        // Top bar: app name + language toggle
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 10.dp),
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

        // Scrollable middle: consent banner, mic card, symptom grid
        Column(
            modifier = Modifier
                .weight(1f)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp)
        ) {
            if (showConsentBanner) {
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 12.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = Color(0xFFE8F0FE))
                ) {
                    Column(modifier = Modifier.padding(14.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.Place, contentDescription = null, tint = PrimaryBlue, modifier = Modifier.size(20.dp))
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                text = "Local Health & Weather Context",
                                fontWeight = FontWeight.Bold,
                                fontSize = 15.sp,
                                color = PrimaryBlue
                            )
                        }
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = "Use location and time to check weather, seasonal illnesses, and local clinic hours?",
                            fontSize = 13.sp,
                            color = Color(0xFF333333)
                        )
                        Spacer(modifier = Modifier.height(10.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            Button(
                                onClick = {
                                    showConsentBanner = false
                                    context.getSharedPreferences("care_compass_prefs", android.content.Context.MODE_PRIVATE)
                                        .edit().putBoolean("show_consent_banner", false).putBoolean("context_consent", true).apply()
                                    viewModel.setContextConsent(true)
                                    locationPermissionLauncher.launch(
                                        arrayOf(
                                            Manifest.permission.ACCESS_COARSE_LOCATION,
                                            Manifest.permission.ACCESS_FINE_LOCATION
                                        )
                                    )
                                },
                                colors = ButtonDefaults.buttonColors(containerColor = PrimaryBlue),
                                shape = RoundedCornerShape(8.dp),
                                contentPadding = PaddingValues(horizontal = 14.dp, vertical = 6.dp)
                            ) {
                                Text("Allow", fontSize = 13.sp)
                            }

                            OutlinedButton(
                                onClick = {
                                    showConsentBanner = false
                                    context.getSharedPreferences("care_compass_prefs", android.content.Context.MODE_PRIVATE)
                                        .edit().putBoolean("show_consent_banner", false).putBoolean("context_consent", false).apply()
                                    viewModel.setContextConsent(false)
                                },
                                shape = RoundedCornerShape(8.dp),
                                contentPadding = PaddingValues(horizontal = 14.dp, vertical = 6.dp)
                            ) {
                                Text("Not now", fontSize = 13.sp, color = Color(0xFF555555))
                            }
                        }
                    }
                }
            }

            // MIC CARD: the first thing on the Home screen (large, centred)
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = Color.White),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(18.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        text = stringResource(R.string.tap_and_speak),
                        fontSize = 22.sp,
                        fontWeight = FontWeight.Bold,
                        color = Color(0xFF212121)
                    )
                    val micHint = when (uiState.selectedLanguage) {
                        "hi" -> stringResource(R.string.home_mic_hint_hi)
                        "hinglish" -> stringResource(R.string.home_mic_hint_hinglish)
                        else -> stringResource(R.string.home_mic_hint_en)
                    }
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = micHint,
                        fontSize = 13.sp,
                        color = Color(0xFF757575),
                        textAlign = TextAlign.Center
                    )

                    Spacer(modifier = Modifier.height(14.dp))

                    MicButton(
                        state = micState,
                        onClick = { handleMicTap() }
                    )

                    Spacer(modifier = Modifier.height(14.dp))

                    // Text box directly under the mic, inside the same card
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        OutlinedTextField(
                            value = inputText,
                            onValueChange = { inputText = it },
                            placeholder = { Text(stringResource(R.string.describe_symptoms), fontSize = 16.sp) },
                            modifier = Modifier
                                .weight(1f)
                                .heightIn(min = 56.dp),
                            shape = RoundedCornerShape(12.dp),
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedBorderColor = PrimaryBlue,
                                unfocusedBorderColor = Color(0xFFBDBDBD)
                            ),
                            maxLines = 3,
                            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                            keyboardActions = KeyboardActions(onSend = { submitTextInput() })
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        IconButton(
                            onClick = { submitTextInput() },
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
                                fontSize = 15.sp,
                                modifier = Modifier.padding(10.dp)
                            )
                        }
                    }

                    // Visible failure + Retry: never fail silently
                    if (uiState.errorMessage != null && !uiState.isLoading) {
                        Spacer(modifier = Modifier.height(10.dp))
                        Surface(
                            color = Color(0xFFFFEBEE),
                            shape = RoundedCornerShape(8.dp),
                            border = BorderStroke(1.dp, Color(0xFFEF9A9A)),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Column(modifier = Modifier.padding(12.dp)) {
                                Text(
                                    text = uiState.errorMessage ?: "",
                                    color = Color(0xFFB71C1C),
                                    fontSize = 15.sp,
                                    fontWeight = FontWeight.Medium
                                )
                                Spacer(modifier = Modifier.height(8.dp))
                                Button(
                                    onClick = { viewModel.retryLastInput() },
                                    colors = ButtonDefaults.buttonColors(containerColor = PrimaryBlue),
                                    shape = RoundedCornerShape(8.dp)
                                ) {
                                    val retryLabel = when (uiState.selectedLanguage) {
                                        "hi" -> stringResource(R.string.btn_retry_hi)
                                        "hinglish" -> stringResource(R.string.btn_retry_hinglish)
                                        else -> stringResource(R.string.btn_retry_en)
                                    }
                                    Text(retryLabel, color = Color.White)
                                }
                            }
                        }
                    }

                    if (uiState.isLoading) {
                        Spacer(modifier = Modifier.height(12.dp))
                        CircularProgressIndicator(color = PrimaryBlue)
                    }
                }
            }

            Spacer(modifier = Modifier.height(18.dp))

            // "What is wrong?" symptom grid
            Text(
                text = stringResource(R.string.group_symptoms_heading),
                fontSize = 22.sp,
                fontWeight = FontWeight.Bold,
                color = Color(0xFF212121),
                textAlign = TextAlign.Start,
                modifier = Modifier.fillMaxWidth()
            )
            Spacer(modifier = Modifier.height(12.dp))

            val symptomChunks = GENERAL_SYMPTOMS.chunked(2)
            symptomChunks.forEach { rowItems ->
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    rowItems.forEach { item ->
                        val isSelected = selectedSymptoms.contains(item.id)
                        val bgColor = if (isSelected) PrimaryBlue else Color.White
                        val contentColor = if (isSelected) Color.White else Color(0xFF212121)
                        val borderColor = if (isSelected) PrimaryBlue else Color(0xFFD6D6D6)

                        Card(
                            modifier = Modifier
                                .weight(1f)
                                .heightIn(min = 72.dp)
                                .clickable {
                                    if (isSelected) selectedSymptoms.remove(item.id) else selectedSymptoms.add(item.id)
                                },
                            shape = RoundedCornerShape(12.dp),
                            border = BorderStroke(1.5.dp, borderColor),
                            colors = CardDefaults.cardColors(containerColor = bgColor),
                            elevation = CardDefaults.cardElevation(defaultElevation = if (isSelected) 3.dp else 1.dp)
                        ) {
                            Column(
                                modifier = Modifier
                                    .fillMaxSize()
                                    .padding(8.dp),
                                horizontalAlignment = Alignment.CenterHorizontally,
                                verticalArrangement = Arrangement.Center
                            ) {
                                Icon(
                                    imageVector = item.icon,
                                    contentDescription = getLabel(item),
                                    tint = contentColor,
                                    modifier = Modifier.size(24.dp)
                                )
                                Spacer(modifier = Modifier.height(4.dp))
                                Text(
                                    text = getLabel(item),
                                    fontSize = 14.sp,
                                    fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium,
                                    color = contentColor,
                                    textAlign = TextAlign.Center
                                )
                            }
                        }
                    }
                }
                Spacer(modifier = Modifier.height(8.dp))
            }

            Spacer(modifier = Modifier.height(8.dp))
        }

        // Sticky bottom bar: Continue (always visible) + emergency/book services
        Surface(
            modifier = Modifier.fillMaxWidth(),
            color = Color.White,
            shadowElevation = 8.dp
        ) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 10.dp)
            ) {
                val continueLabel = stringResource(R.string.btn_continue) +
                        if (selectedSymptoms.isNotEmpty()) " (${selectedSymptoms.size} selected)" else ""
                BigButton(
                    text = continueLabel,
                    enabled = selectedSymptoms.isNotEmpty() && !uiState.isLoading,
                    onClick = {
                        viewModel.submitSymptomTiles(selectedSymptoms.toList())
                        selectedSymptoms.clear()
                    }
                )

                Spacer(modifier = Modifier.height(8.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    OutlinedButton(
                        onClick = {
                            val intent = Intent(Intent.ACTION_DIAL, Uri.parse("tel:112"))
                            context.startActivity(intent)
                        },
                        modifier = Modifier.weight(1f).height(48.dp),
                        shape = RoundedCornerShape(10.dp),
                        border = BorderStroke(1.5.dp, EmergencyRed),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = EmergencyRed)
                    ) {
                        Icon(Icons.Default.Warning, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(6.dp))
                        Text("Emergency: 112", fontSize = 14.sp, fontWeight = FontWeight.Bold)
                    }

                    val bookServicesLabel = when (uiState.selectedLanguage) {
                        "hi" -> stringResource(R.string.book_services_hi)
                        "hinglish" -> stringResource(R.string.book_services_hinglish)
                        else -> stringResource(R.string.book_services_en)
                    }
                    OutlinedButton(
                        onClick = { onBookServices() },
                        modifier = Modifier.weight(1f).height(48.dp),
                        shape = RoundedCornerShape(10.dp),
                        border = BorderStroke(1.5.dp, PrimaryBlue),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = PrimaryBlue)
                    ) {
                        Icon(Icons.Default.CalendarMonth, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(6.dp))
                        Text(bookServicesLabel, fontSize = 14.sp, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}
