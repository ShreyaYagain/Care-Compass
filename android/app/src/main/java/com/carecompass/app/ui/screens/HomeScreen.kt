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
import androidx.compose.foundation.horizontalScroll
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
    val canonicalKeyword: String,
    val labelEnRes: Int,
    val labelHiRes: Int,
    val labelHinglishRes: Int
)

// Group 1: General symptoms (Multi-select)
private val GENERAL_SYMPTOMS = listOf(
    SymptomItem("fever", Icons.Default.Whatshot, "fever", R.string.symptom_fever_en, R.string.symptom_fever_hi, R.string.symptom_fever_hinglish),
    SymptomItem("cough_cold", Icons.Default.Info, "cough and cold", R.string.symptom_cough_cold_en, R.string.symptom_cough_cold_hi, R.string.symptom_cough_cold_hinglish),
    SymptomItem("headache", Icons.Default.Face, "headache", R.string.symptom_headache_en, R.string.symptom_headache_hi, R.string.symptom_headache_hinglish),
    SymptomItem("stomach_pain", Icons.Default.Place, "stomach pain", R.string.symptom_stomach_pain_en, R.string.symptom_stomach_pain_hi, R.string.symptom_stomach_pain_hinglish),
    SymptomItem("vomiting", Icons.Default.Refresh, "vomiting and loose motion", R.string.symptom_vomiting_en, R.string.symptom_vomiting_hi, R.string.symptom_vomiting_hinglish),
    SymptomItem("body_pain", Icons.Default.Person, "body pain", R.string.symptom_body_pain_en, R.string.symptom_body_pain_hi, R.string.symptom_body_pain_hinglish),
    SymptomItem("weakness", Icons.Default.Person, "extreme weakness", R.string.symptom_weakness_en, R.string.symptom_weakness_hi, R.string.symptom_weakness_hinglish),
    SymptomItem("wound_injury", Icons.Default.Healing, "wound injury", R.string.symptom_wound_injury_en, R.string.symptom_wound_injury_hi, R.string.symptom_wound_injury_hinglish),
    SymptomItem("skin_problem", Icons.Default.Face, "skin rash itching", R.string.symptom_skin_problem_en, R.string.symptom_skin_problem_hi, R.string.symptom_skin_problem_hinglish),
    SymptomItem("not_eating", Icons.Default.Close, "patient not eating or drinking", R.string.symptom_not_eating_en, R.string.symptom_not_eating_hi, R.string.symptom_not_eating_hinglish)
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

        // Red Emergency Call Button (Dials 112)
        Button(
            onClick = {
                val intent = Intent(Intent.ACTION_DIAL, Uri.parse("tel:112"))
                context.startActivity(intent)
            },
            modifier = Modifier
                .fillMaxWidth()
                .height(54.dp),
            shape = RoundedCornerShape(12.dp),
            colors = ButtonDefaults.buttonColors(containerColor = EmergencyRed, contentColor = Color.White)
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

        Spacer(modifier = Modifier.height(12.dp))

        // Blue Book Services Button
        val bookServicesLabel = when (uiState.selectedLanguage) {
            "hi" -> stringResource(R.string.book_services_hi)
            "hinglish" -> stringResource(R.string.book_services_hinglish)
            else -> stringResource(R.string.book_services_en)
        }

        Button(
            onClick = {
                onBookServices()
            },
            modifier = Modifier
                .fillMaxWidth()
                .height(54.dp),
            shape = RoundedCornerShape(12.dp),
            colors = ButtonDefaults.buttonColors(containerColor = PrimaryBlue, contentColor = Color.White)
        ) {
            Icon(
                imageVector = Icons.Default.CalendarMonth,
                contentDescription = bookServicesLabel,
                tint = Color.White
            )
            Spacer(modifier = Modifier.width(8.dp))
            Text(
                text = bookServicesLabel,
                fontSize = 18.sp,
                fontWeight = FontWeight.Bold,
                color = Color.White
            )
        }

        Spacer(modifier = Modifier.height(20.dp))

        // Group 1: "What is wrong?" (Symptoms, min 72dp, 2 columns, multi-select)
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

        Spacer(modifier = Modifier.height(18.dp))

        // Continue Button (appears when at least one symptom is selected)
        if (selectedSymptoms.isNotEmpty()) {
            Spacer(modifier = Modifier.height(16.dp))
            BigButton(
                text = "Continue (${selectedSymptoms.size} selected)",
                onClick = {
                    val parts = mutableListOf<String>()
                    selectedSymptoms.forEach { sId ->
                        GENERAL_SYMPTOMS.find { it.id == sId }?.let { parts.add(it.canonicalKeyword) }
                    }
                    val sentence = parts.joinToString(", ")
                    if (sentence.isNotBlank()) {
                        viewModel.submitUserInput(sentence)
                        selectedSymptoms.clear()
                    }
                }
            )
        }

        Spacer(modifier = Modifier.height(24.dp))
        HorizontalDivider(color = Color(0xFFE0E0E0))
        Spacer(modifier = Modifier.height(18.dp))

        // Voice Input & Mic
        MicButton(
            state = micState,
            onClick = { handleMicTap() }
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
                    fontSize = 16.sp,
                    modifier = Modifier.padding(10.dp)
                )
            }
        }

        if (uiState.isLoading) {
            Spacer(modifier = Modifier.height(12.dp))
            CircularProgressIndicator(color = PrimaryBlue)
        }

        Spacer(modifier = Modifier.height(18.dp))

        // Text input with Send button (White bold Send icon)
        val submitTextInput = {
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
                placeholder = { Text("Or type symptoms here...", fontSize = 17.sp) },
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

        Spacer(modifier = Modifier.height(16.dp))
    }
}
