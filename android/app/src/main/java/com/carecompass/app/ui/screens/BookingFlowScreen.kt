package com.carecompass.app.ui.screens

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.provider.CalendarContract
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.carecompass.app.R
import com.carecompass.app.data.Location
import com.carecompass.app.data.MatchedCaregiver
import com.carecompass.app.data.TriageResponse
import com.carecompass.app.ui.components.BigButton
import com.carecompass.app.ui.components.CaregiverCard
import com.carecompass.app.ui.components.LanguageToggle
import com.carecompass.app.ui.components.MicButton
import com.carecompass.app.ui.theme.GreenSafe
import com.carecompass.app.ui.theme.PrimaryBlue
import com.carecompass.app.ui.theme.SurfaceBackground
import com.carecompass.app.ui.theme.TextDark
import com.carecompass.app.ui.theme.TextGray
import com.carecompass.app.util.MicState
import com.carecompass.app.util.SpeechHelper
import com.carecompass.app.util.TtsHelper
import com.carecompass.app.viewmodel.BookingUiState
import com.carecompass.app.viewmodel.BookingViewModel
import com.carecompass.app.viewmodel.CareService

@Composable
fun BookingFlowScreen(
    viewModel: BookingViewModel,
    selectedLanguage: String,
    onLanguageSelected: (String) -> Unit,
    userLocation: Location?,
    onEmergency: (TriageResponse) -> Unit,
    onBack: () -> Unit,
    onDone: () -> Unit,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val uiState by viewModel.uiState.collectAsState()
    val ttsHelper = remember { TtsHelper(context) }

    DisposableEffect(Unit) {
        onDispose {
            ttsHelper.shutdown()
        }
    }

    val disclaimerText = when (selectedLanguage) {
        "hi" -> stringResource(R.string.medical_disclaimer_hi)
        "hinglish" -> stringResource(R.string.medical_disclaimer_hinglish)
        else -> stringResource(R.string.medical_disclaimer_en)
    }

    val serviceTitle = uiState.service?.let { stringResource(it.getTitle(selectedLanguage)) }
        ?: when (selectedLanguage) {
            "hi" -> stringResource(R.string.book_service_title_hi)
            "hinglish" -> stringResource(R.string.book_service_title_hinglish)
            else -> stringResource(R.string.book_service_title_en)
        }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(SurfaceBackground)
            .padding(16.dp)
            .verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        // Top Header: Back Arrow, Service Title, Language Toggle
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(
                onClick = { viewModel.goBack(onBack) },
                modifier = Modifier.size(48.dp)
            ) {
                Icon(
                    imageVector = Icons.AutoMirrored.Filled.ArrowBack,
                    contentDescription = "Back",
                    tint = PrimaryBlue,
                    modifier = Modifier.size(28.dp)
                )
            }

            Text(
                text = serviceTitle,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
                color = PrimaryBlue,
                modifier = Modifier.weight(1f).padding(horizontal = 8.dp)
            )

            LanguageToggle(
                selectedLanguage = selectedLanguage,
                onLanguageSelected = onLanguageSelected
            )
        }

        Spacer(modifier = Modifier.height(12.dp))

        // Progress Dots (Steps 1, 2, 3) - Only shown before final confirmation (step 4)
        if (uiState.currentStep in 1..3) {
            ProgressDotsHeader(currentStep = uiState.currentStep)
            Spacer(modifier = Modifier.height(20.dp))
        }

        // Error message banner with Retry
        if (uiState.errorMessage != null) {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 16.dp),
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = Color(0xFFFFF3E0)),
                border = BorderStroke(1.dp, Color(0xFFFFB74D))
            ) {
                Column(modifier = Modifier.padding(14.dp)) {
                    Text(
                        text = uiState.errorMessage ?: "",
                        color = Color(0xFFE65100),
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Medium
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Button(
                        onClick = {
                            when (uiState.currentStep) {
                                1 -> viewModel.submitReason(selectedLanguage, userLocation, onEmergency)
                                2 -> viewModel.loadCaregivers(selectedLanguage, userLocation)
                                3 -> viewModel.confirmBooking { }
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = PrimaryBlue),
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        val retryLabel = when (selectedLanguage) {
                            "hi" -> stringResource(R.string.btn_retry_hi)
                            "hinglish" -> stringResource(R.string.btn_retry_hinglish)
                            else -> stringResource(R.string.btn_retry_en)
                        }
                        Text(retryLabel, color = Color.White)
                    }
                }
            }
        }

        // Active Step Content
        when (uiState.currentStep) {
            1 -> {
                Step1ReasonView(
                    viewModel = viewModel,
                    uiState = uiState,
                    selectedLanguage = selectedLanguage,
                    userLocation = userLocation,
                    onEmergency = onEmergency
                )
            }
            2 -> {
                Step2CaregiversView(
                    viewModel = viewModel,
                    uiState = uiState,
                    selectedLanguage = selectedLanguage,
                    userLocation = userLocation
                )
            }
            3 -> {
                Step3DateTimeView(
                    viewModel = viewModel,
                    uiState = uiState,
                    selectedLanguage = selectedLanguage,
                    onBookingConfirmed = { bResp ->
                        val spoken = buildConfirmationSpeech(
                            lang = selectedLanguage,
                            serviceTitle = serviceTitle,
                            caregiverName = uiState.selectedCaregiver?.name ?: "Caregiver",
                            slot = bResp.slot,
                            bookingId = bResp.bookingId
                        )
                        ttsHelper.speak(spoken, selectedLanguage)
                    }
                )
            }
            4 -> {
                ConfirmationView(
                    viewModel = viewModel,
                    uiState = uiState,
                    selectedLanguage = selectedLanguage,
                    onDone = onDone
                )
            }
        }

        Spacer(modifier = Modifier.height(32.dp))

        // Mandatory Footer Line on every booking screen
        Text(
            text = disclaimerText,
            fontSize = 13.sp,
            color = Color(0xFF757575),
            textAlign = TextAlign.Center,
            lineHeight = 18.sp,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 8.dp)
        )
    }
}

@Composable
private fun ProgressDotsHeader(currentStep: Int) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically
    ) {
        for (step in 1..3) {
            val isActive = step == currentStep
            val isCompleted = step < currentStep

            val dotColor = when {
                isActive || isCompleted -> PrimaryBlue
                else -> Color(0xFFCBD5E1)
            }

            Box(
                modifier = Modifier
                    .size(if (isActive) 14.dp else 10.dp)
                    .clip(CircleShape)
                    .background(dotColor)
            )

            if (step < 3) {
                Box(
                    modifier = Modifier
                        .width(36.dp)
                        .height(3.dp)
                        .background(if (step < currentStep) PrimaryBlue else Color(0xFFE2E8F0))
                )
            }
        }
    }
}

@Composable
private fun Step1ReasonView(
    viewModel: BookingViewModel,
    uiState: BookingUiState,
    selectedLanguage: String,
    userLocation: Location?,
    onEmergency: (TriageResponse) -> Unit
) {
    val context = LocalContext.current
    var micState by remember { mutableStateOf(MicState.IDLE) }
    var micError by remember { mutableStateOf<String?>(null) }

    val speechHelper = remember {
        SpeechHelper(
            context = context,
            onStateChanged = { micState = it },
            onPartialResult = { viewModel.setReason(it) },
            onFinalResult = { viewModel.setReason(it) },
            onError = { micError = it }
        )
    }

    DisposableEffect(Unit) {
        onDispose { speechHelper.destroy() }
    }

    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            micError = null
            speechHelper.startListening(selectedLanguage)
        } else {
            micError = "Microphone permission required for voice input"
            micState = MicState.IDLE
        }
    }

    val heading = when (selectedLanguage) {
        "hi" -> stringResource(R.string.booking_step1_heading_hi)
        "hinglish" -> stringResource(R.string.booking_step1_heading_hinglish)
        else -> stringResource(R.string.booking_step1_heading_en)
    }

    val hintText = when (selectedLanguage) {
        "hi" -> stringResource(R.string.reason_hint_hi)
        "hinglish" -> stringResource(R.string.reason_hint_hinglish)
        else -> stringResource(R.string.reason_hint_en)
    }

    val nextBtnText = when (selectedLanguage) {
        "hi" -> stringResource(R.string.btn_next_hi)
        "hinglish" -> stringResource(R.string.btn_next_hinglish)
        else -> stringResource(R.string.btn_next_en)
    }

    val suggestions = when (uiState.service) {
        CareService.DOCTOR_HOME_VISIT -> listOf(
            "Fever / cough", "Weakness / dizziness", "Post-surgery check", "Mobility problem", "Senior health check"
        )
        CareService.HOME_NURSING -> listOf(
            "Injection", "Dressing change", "Post-surgery care", "IV drip", "Vitals check"
        )
        CareService.LAB_TEST_HOME -> listOf(
            "Blood sugar", "Full body check-up", "Doctor ne test likha hai", "CBC test", "Lipid profile"
        )
        CareService.TELECONSULTATION -> listOf(
            "Fever / cough", "Second opinion", "Prescription query", "Stomach ache", "Skin problem"
        )
        null -> listOf(
            "Fever / cough", "Pain / injury", "Injection / dressing", "Blood test", "Stomach ache"
        )
    }

    Column(modifier = Modifier.fillMaxWidth()) {
        Text(
            text = heading,
            fontSize = 22.sp,
            fontWeight = FontWeight.Bold,
            color = TextDark
        )

        Spacer(modifier = Modifier.height(14.dp))

        // Suggestion Chips
        Text(
            text = "Suggestions (tap to add):",
            fontSize = 14.sp,
            fontWeight = FontWeight.Medium,
            color = TextGray
        )
        Spacer(modifier = Modifier.height(8.dp))

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            suggestions.forEach { chipText ->
                val isSelected = uiState.reason.contains(chipText, ignoreCase = true)
                FilterChip(
                    selected = isSelected,
                    onClick = { viewModel.appendReason(chipText) },
                    label = {
                        Text(
                            text = chipText,
                            fontSize = 14.sp,
                            fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal
                        )
                    },
                    colors = FilterChipDefaults.filterChipColors(
                        selectedContainerColor = PrimaryBlue,
                        selectedLabelColor = Color.White
                    )
                )
            }
        }

        Spacer(modifier = Modifier.height(18.dp))

        // Free-text input field
        OutlinedTextField(
            value = uiState.reason,
            onValueChange = { viewModel.setReason(it) },
            placeholder = { Text(hintText, fontSize = 16.sp) },
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = 100.dp),
            shape = RoundedCornerShape(12.dp),
            colors = OutlinedTextFieldDefaults.colors(
                focusedBorderColor = PrimaryBlue,
                unfocusedBorderColor = Color(0xFFCBD5E1)
            ),
            maxLines = 4,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
            keyboardActions = KeyboardActions(onSend = {
                if (uiState.reason.isNotBlank() && !uiState.isLoading) {
                    viewModel.submitReason(selectedLanguage, userLocation, onEmergency)
                }
            })
        )

        Spacer(modifier = Modifier.height(14.dp))

        // Voice Input & Mic
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.CenterVertically
        ) {
            MicButton(
                state = micState,
                onClick = {
                    if (micState == MicState.LISTENING) {
                        speechHelper.stopListening()
                    } else {
                        val check = ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO)
                        if (check == PackageManager.PERMISSION_GRANTED) {
                            speechHelper.startListening(selectedLanguage)
                        } else {
                            permissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
                        }
                    }
                }
            )
        }

        if (micError != null) {
            Spacer(modifier = Modifier.height(6.dp))
            Text(
                text = micError ?: "",
                fontSize = 13.sp,
                color = Color(0xFFE65100),
                textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth()
            )
        }

        // Follow-up question banner: shows the REAL options from the backend.
        // Never a hardcoded Yes/No/I-don't-know step.
        if (uiState.followUpQuestion != null) {
            Spacer(modifier = Modifier.height(18.dp))
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(containerColor = PrimaryBlue.copy(alpha = 0.08f)),
                border = BorderStroke(1.5.dp, PrimaryBlue)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = uiState.followUpQuestion ?: "",
                        fontSize = 17.sp,
                        fontWeight = FontWeight.Bold,
                        color = TextDark
                    )
                    Spacer(modifier = Modifier.height(14.dp))

                    val options = uiState.followUpOptions.ifEmpty {
                        listOf("Yes", "No", "Not sure")
                    }

                    Column(
                        modifier = Modifier.fillMaxWidth(),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        options.forEach { opt ->
                            Button(
                                onClick = { viewModel.answerFollowUp(opt, selectedLanguage, userLocation, onEmergency) },
                                modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp),
                                shape = RoundedCornerShape(10.dp),
                                colors = ButtonDefaults.buttonColors(containerColor = PrimaryBlue)
                            ) {
                                Text(opt, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }
            }
        }

        if (uiState.isLoading) {
            Spacer(modifier = Modifier.height(16.dp))
            Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = PrimaryBlue)
            }
        }

        Spacer(modifier = Modifier.height(24.dp))

        // Next Button: Disabled until reason is not empty
        BigButton(
            text = nextBtnText,
            enabled = uiState.reason.isNotBlank() && !uiState.isLoading,
            onClick = {
                viewModel.submitReason(selectedLanguage, userLocation, onEmergency)
            }
        )
    }
}

@Composable
private fun Step2CaregiversView(
    viewModel: BookingViewModel,
    uiState: BookingUiState,
    selectedLanguage: String,
    userLocation: Location?
) {
    val heading = when (selectedLanguage) {
        "hi" -> stringResource(R.string.booking_step2_heading_hi)
        "hinglish" -> stringResource(R.string.booking_step2_heading_hinglish)
        else -> stringResource(R.string.booking_step2_heading_en)
    }

    val chooseBtnText = when (selectedLanguage) {
        "hi" -> stringResource(R.string.choose_caregiver_btn_hi)
        "hinglish" -> stringResource(R.string.choose_caregiver_btn_hinglish)
        else -> stringResource(R.string.choose_caregiver_btn_en)
    }

    val noCaregiverMsg = when (selectedLanguage) {
        "hi" -> stringResource(R.string.no_caregiver_msg_hi)
        "hinglish" -> stringResource(R.string.no_caregiver_msg_hinglish)
        else -> stringResource(R.string.no_caregiver_msg_en)
    }

    val switchBtnText = when (selectedLanguage) {
        "hi" -> stringResource(R.string.switch_to_tele_btn_hi)
        "hinglish" -> stringResource(R.string.switch_to_tele_btn_hinglish)
        else -> stringResource(R.string.switch_to_tele_btn_en)
    }

    Column(modifier = Modifier.fillMaxWidth()) {
        Text(
            text = heading,
            fontSize = 22.sp,
            fontWeight = FontWeight.Bold,
            color = TextDark
        )

        Spacer(modifier = Modifier.height(16.dp))

        if (uiState.isLoading) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(180.dp),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator(color = PrimaryBlue)
            }
        } else if (uiState.caregivers.isEmpty() || uiState.isMatchedEmpty) {
            // Empty state: Say so plainly and offer teleconsultation option
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = Color.White),
                border = BorderStroke(1.dp, Color(0xFFE2E8F0)),
                elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
            ) {
                Column(
                    modifier = Modifier.padding(20.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Icon(
                        imageVector = Icons.Default.PersonOff,
                        contentDescription = null,
                        tint = TextGray,
                        modifier = Modifier.size(48.dp)
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    Text(
                        text = noCaregiverMsg,
                        fontSize = 17.sp,
                        fontWeight = FontWeight.Medium,
                        color = TextDark,
                        textAlign = TextAlign.Center
                    )
                    Spacer(modifier = Modifier.height(18.dp))
                    Button(
                        onClick = { viewModel.switchToTeleconsultation(selectedLanguage, userLocation) },
                        modifier = Modifier.fillMaxWidth().height(56.dp),
                        shape = RoundedCornerShape(12.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = PrimaryBlue)
                    ) {
                        Icon(Icons.Default.VideoCall, contentDescription = null, tint = Color.White)
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = switchBtnText,
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold,
                            color = Color.White
                        )
                    }
                }
            }
        } else {
            // Top 3 Caregiver Cards
            uiState.caregivers.forEach { caregiver ->
                val isSelected = uiState.selectedCaregiver?.caregiverId == caregiver.caregiverId
                CaregiverCard(
                    caregiver = caregiver,
                    isSelected = isSelected,
                    onSelect = { viewModel.selectCaregiver(caregiver) },
                    showBookButton = false
                )
            }

            Spacer(modifier = Modifier.height(20.dp))

            // Choose this caregiver button (>= 56dp, min font 18sp)
            BigButton(
                text = chooseBtnText,
                enabled = uiState.selectedCaregiver != null,
                onClick = { viewModel.goToStep3() }
            )
        }
    }
}

@Composable
private fun Step3DateTimeView(
    viewModel: BookingViewModel,
    uiState: BookingUiState,
    selectedLanguage: String,
    onBookingConfirmed: (com.carecompass.app.data.BookingResponse) -> Unit
) {
    val heading = when (selectedLanguage) {
        "hi" -> stringResource(R.string.booking_step3_heading_hi)
        "hinglish" -> stringResource(R.string.booking_step3_heading_hinglish)
        else -> stringResource(R.string.booking_step3_heading_en)
    }

    val fastingNote = when (selectedLanguage) {
        "hi" -> stringResource(R.string.fasting_note_hi)
        "hinglish" -> stringResource(R.string.fasting_note_hinglish)
        else -> stringResource(R.string.fasting_note_en)
    }

    val nameLabel = when (selectedLanguage) {
        "hi" -> stringResource(R.string.patient_name_label_hi)
        "hinglish" -> stringResource(R.string.patient_name_label_hinglish)
        else -> stringResource(R.string.patient_name_label_en)
    }

    val phoneLabel = when (selectedLanguage) {
        "hi" -> stringResource(R.string.phone_label_hi)
        "hinglish" -> stringResource(R.string.phone_label_hinglish)
        else -> stringResource(R.string.phone_label_en)
    }

    val addressLabel = when (selectedLanguage) {
        "hi" -> stringResource(R.string.address_label_hi)
        "hinglish" -> stringResource(R.string.address_label_hinglish)
        else -> stringResource(R.string.address_label_en)
    }

    val confirmBtnText = when (selectedLanguage) {
        "hi" -> stringResource(R.string.confirm_booking_btn_hi)
        "hinglish" -> stringResource(R.string.confirm_booking_btn_hinglish)
        else -> stringResource(R.string.confirm_booking_btn_en)
    }

    val next14Days = remember { BookingViewModel.getNext14Days() }
    val selectedDayItem = next14Days.getOrNull(uiState.selectedDateOffset) ?: next14Days.first()

    val freeFrom = uiState.selectedCaregiver?.freeFrom ?: "09:00"
    val freeUntil = uiState.selectedCaregiver?.freeUntil ?: "18:00"

    val timeSlots = remember(freeFrom, freeUntil, selectedDayItem.isToday) {
        BookingViewModel.generate1HourSlots(freeFrom, freeUntil, selectedDayItem.isToday)
    }

    // Preferred time defaults to the earliest free slot (never blocks the form).
    LaunchedEffect(timeSlots, uiState.selectedDateOffset) {
        if (uiState.selectedSlot == null) {
            timeSlots.firstOrNull { !it.isPast && !it.isBooked }?.let { first ->
                viewModel.selectSlot(first.slotKey)
            }
        }
    }

    var localName by remember { mutableStateOf(uiState.patientName) }
    var localPhone by remember { mutableStateOf(uiState.phone) }
    var localAddress by remember { mutableStateOf(uiState.address) }

    val phoneRegex = Regex("^[6-9]\\d{9}$")
    val isPhoneValid = localPhone.trim().matches(phoneRegex)
    val isNameValid = localName.trim().isNotBlank()
    val isAddressValid = if (uiState.service?.isHomeVisit == true) localAddress.trim().isNotBlank() else true
    val isSlotValid = uiState.selectedSlot != null

    val isFormValid = isPhoneValid && isNameValid && isAddressValid && isSlotValid

    Column(modifier = Modifier.fillMaxWidth()) {
        Text(
            text = heading,
            fontSize = 22.sp,
            fontWeight = FontWeight.Bold,
            color = TextDark
        )

        Spacer(modifier = Modifier.height(16.dp))

        // Horizontal Date Strip for next 14 days
        Text(
            text = "Select Date (next 14 days):",
            fontSize = 15.sp,
            fontWeight = FontWeight.Medium,
            color = TextDark
        )
        Spacer(modifier = Modifier.height(8.dp))

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            next14Days.forEach { item ->
                val isSelected = item.dayOffset == uiState.selectedDateOffset
                val bgCol = if (isSelected) PrimaryBlue else Color.White
                val textCol = if (isSelected) Color.White else TextDark
                val borderCol = if (isSelected) PrimaryBlue else Color(0xFFCBD5E1)

                Card(
                    modifier = Modifier
                        .width(72.dp)
                        .height(84.dp)
                        .clickable { viewModel.selectDate(item.dayOffset) },
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = bgCol),
                    border = BorderStroke(1.5.dp, borderCol),
                    elevation = CardDefaults.cardElevation(defaultElevation = if (isSelected) 4.dp else 1.dp)
                ) {
                    Column(
                        modifier = Modifier.fillMaxSize().padding(6.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center
                    ) {
                        Text(
                            text = item.dayLabel,
                            fontSize = 12.sp,
                            fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium,
                            color = textCol
                        )
                        Spacer(modifier = Modifier.height(2.dp))
                        Text(
                            text = item.dateNumber,
                            fontSize = 20.sp,
                            fontWeight = FontWeight.ExtraBold,
                            color = textCol
                        )
                        Text(
                            text = item.monthLabel,
                            fontSize = 11.sp,
                            color = textCol
                        )
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(20.dp))

        // Time Slot Chips built only from caregiver's free window
        Text(
            text = "Available 1-Hour Slots (${uiState.selectedCaregiver?.name ?: "Caregiver"}):",
            fontSize = 15.sp,
            fontWeight = FontWeight.Medium,
            color = TextDark
        )
        Spacer(modifier = Modifier.height(8.dp))

        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            timeSlots.forEach { slotItem ->
                val isSelected = uiState.selectedSlot == slotItem.slotKey
                val isDisabled = slotItem.isPast || slotItem.isBooked

                FilterChip(
                    selected = isSelected,
                    enabled = !isDisabled,
                    onClick = { viewModel.selectSlot(slotItem.slotKey) },
                    label = {
                        Text(
                            text = if (slotItem.isBooked) "${slotItem.displayLabel} (Booked)" else slotItem.displayLabel,
                            fontSize = 14.sp,
                            fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal
                        )
                    },
                    colors = FilterChipDefaults.filterChipColors(
                        selectedContainerColor = PrimaryBlue,
                        selectedLabelColor = Color.White,
                        disabledContainerColor = Color(0xFFF1F5F9),
                        disabledLabelColor = Color(0xFF94A3B8)
                    )
                )
            }
        }

        // Fasting note for lab test
        if (uiState.service == CareService.LAB_TEST_HOME) {
            Spacer(modifier = Modifier.height(16.dp))
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = PrimaryBlue.copy(alpha = 0.08f)),
                border = BorderStroke(1.dp, PrimaryBlue.copy(alpha = 0.3f))
            ) {
                Row(
                    modifier = Modifier.padding(14.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        imageVector = Icons.Default.Info,
                        contentDescription = "Note",
                        tint = PrimaryBlue,
                        modifier = Modifier.size(22.dp)
                    )
                    Spacer(modifier = Modifier.width(10.dp))
                    Text(
                        text = fastingNote,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Medium,
                        color = PrimaryBlue
                    )
                }
            }
        }

        Spacer(modifier = Modifier.height(20.dp))

        // Contact info Card
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(14.dp),
            colors = CardDefaults.cardColors(containerColor = Color.White),
            border = BorderStroke(1.dp, Color(0xFFE2E8F0))
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                val whoIsThisForText = when (selectedLanguage) {
                    "hi" -> stringResource(R.string.who_is_this_for_hi)
                    "hinglish" -> stringResource(R.string.who_is_this_for_hinglish)
                    else -> stringResource(R.string.who_is_this_for_en)
                }

                val myselfText = when (selectedLanguage) {
                    "hi" -> stringResource(R.string.whom_myself_hi)
                    "hinglish" -> stringResource(R.string.whom_myself_hinglish)
                    else -> stringResource(R.string.whom_myself_en)
                }

                val someoneElseText = when (selectedLanguage) {
                    "hi" -> stringResource(R.string.whom_someone_else_hi)
                    "hinglish" -> stringResource(R.string.whom_someone_else_hinglish)
                    else -> stringResource(R.string.whom_someone_else_en)
                }

                Text(
                    text = whoIsThisForText,
                    fontSize = 17.sp,
                    fontWeight = FontWeight.Bold,
                    color = TextDark
                )
                Spacer(modifier = Modifier.height(10.dp))

                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    FilterChip(
                        selected = uiState.forWhom == "myself",
                        onClick = { viewModel.setForWhom("myself") },
                        label = { Text(myselfText, fontSize = 15.sp, fontWeight = FontWeight.SemiBold) },
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = PrimaryBlue,
                            selectedLabelColor = Color.White
                        )
                    )
                    FilterChip(
                        selected = uiState.forWhom == "someone_else",
                        onClick = { viewModel.setForWhom("someone_else") },
                        label = { Text(someoneElseText, fontSize = 15.sp, fontWeight = FontWeight.SemiBold) },
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = PrimaryBlue,
                            selectedLabelColor = Color.White
                        )
                    )
                }

                if (uiState.forWhom == "someone_else") {
                    Spacer(modifier = Modifier.height(14.dp))
                    val patientNameLabel = when (selectedLanguage) {
                        "hi" -> stringResource(R.string.label_patient_name_req_hi)
                        "hinglish" -> stringResource(R.string.label_patient_name_req_hinglish)
                        else -> stringResource(R.string.label_patient_name_req_en)
                    }

                    OutlinedTextField(
                        value = uiState.patientName,
                        onValueChange = {
                            viewModel.setPatientName(it)
                        },
                        label = { Text(patientNameLabel) },
                        placeholder = { Text("e.g. Papa") },
                        isError = uiState.patientName.isBlank(),
                        supportingText = {
                            if (uiState.patientName.isBlank()) {
                                Text("Patient name is required", color = MaterialTheme.colorScheme.error)
                            }
                        },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(10.dp)
                    )

                    Spacer(modifier = Modifier.height(12.dp))
                    val relationLabel = when (selectedLanguage) {
                        "hi" -> stringResource(R.string.label_relation_opt_hi)
                        "hinglish" -> stringResource(R.string.label_relation_opt_hinglish)
                        else -> stringResource(R.string.label_relation_opt_en)
                    }
                    Text(
                        text = relationLabel,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Medium,
                        color = Color(0xFF555555)
                    )
                    Spacer(modifier = Modifier.height(6.dp))
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        listOf(
                            Triple("Papa", R.string.relation_papa_hi, R.string.relation_papa_hinglish),
                            Triple("Mama", R.string.relation_mama_hi, R.string.relation_mama_hinglish),
                            Triple("Child", R.string.relation_child_hi, R.string.relation_child_hinglish),
                            Triple("Other", R.string.relation_other_hi, R.string.relation_other_hinglish)
                        ).forEach { (key, hiRes, hinglishRes) ->
                            val labelText = when (selectedLanguage) {
                                "hi" -> stringResource(hiRes)
                                "hinglish" -> stringResource(hinglishRes)
                                else -> key
                            }
                            FilterChip(
                                selected = uiState.relation == key,
                                onClick = {
                                    viewModel.setRelation(if (uiState.relation == key) null else key)
                                },
                                label = { Text(labelText, fontSize = 14.sp) },
                                colors = FilterChipDefaults.filterChipColors(
                                    selectedContainerColor = PrimaryBlue,
                                    selectedLabelColor = Color.White
                                )
                            )
                        }
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))
                HorizontalDivider(color = Color(0xFFEEEEEE))
                Spacer(modifier = Modifier.height(14.dp))

                Text(
                    text = "Contact Details",
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Bold,
                    color = TextDark
                )
                Spacer(modifier = Modifier.height(10.dp))

                OutlinedTextField(
                    value = localName,
                    onValueChange = {
                        localName = it
                        viewModel.updatePatientDetails(localName, localPhone, localAddress)
                    },
                    label = { Text(nameLabel) },
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(10.dp)
                )

                Spacer(modifier = Modifier.height(12.dp))

                OutlinedTextField(
                    value = localPhone,
                    onValueChange = { input ->
                        val digits = input.filter { it.isDigit() }.take(10)
                        localPhone = digits
                        viewModel.updatePatientDetails(localName, localPhone, localAddress)
                    },
                    label = { Text(phoneLabel) },
                    placeholder = { Text("e.g. 9876543210") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                    isError = localPhone.isNotBlank() && !isPhoneValid,
                    supportingText = {
                        if (localPhone.isNotBlank() && !isPhoneValid) {
                            Text("Must be a valid 10-digit mobile number", color = MaterialTheme.colorScheme.error)
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(10.dp)
                )

                // Address for home services
                if (uiState.service?.isHomeVisit == true) {
                    Spacer(modifier = Modifier.height(12.dp))
                    OutlinedTextField(
                        value = localAddress,
                        onValueChange = {
                            localAddress = it
                            viewModel.updatePatientDetails(localName, localPhone, localAddress)
                        },
                        label = { Text(addressLabel) },
                        placeholder = { Text("House/flat, street, area...") },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(10.dp),
                        maxLines = 3
                    )
                }
            }
        }

        if (uiState.isLoading) {
            Spacer(modifier = Modifier.height(16.dp))
            Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(color = PrimaryBlue)
            }
        }

        Spacer(modifier = Modifier.height(24.dp))

        // Confirm Booking button (>= 56dp, min font 18sp)
        BigButton(
            text = confirmBtnText,
            enabled = isFormValid && !uiState.isLoading,
            onClick = {
                viewModel.confirmBooking(onBookingConfirmed)
            }
        )
    }
}

@Composable
private fun ConfirmationView(
    viewModel: BookingViewModel,
    uiState: BookingUiState,
    selectedLanguage: String,
    onDone: () -> Unit
) {
    val context = LocalContext.current
    val confirmedTitle = when (selectedLanguage) {
        "hi" -> stringResource(R.string.booking_confirmed_title_hi)
        "hinglish" -> stringResource(R.string.booking_confirmed_title_hinglish)
        else -> stringResource(R.string.booking_confirmed_title_en)
    }

    val addToCalendarText = when (selectedLanguage) {
        "hi" -> stringResource(R.string.add_to_calendar_btn_hi)
        "hinglish" -> stringResource(R.string.add_to_calendar_btn_hinglish)
        else -> stringResource(R.string.add_to_calendar_btn_en)
    }

    val backHomeText = when (selectedLanguage) {
        "hi" -> stringResource(R.string.back_to_home_btn_hi)
        "hinglish" -> stringResource(R.string.back_to_home_btn_hinglish)
        else -> stringResource(R.string.back_to_home_btn_en)
    }

    val serviceTitle = uiState.service?.let { stringResource(it.getTitle(selectedLanguage)) } ?: "Service"
    val caregiverName = uiState.selectedCaregiver?.name ?: "Caregiver"
    val bookingId = uiState.bookingResponse?.bookingId ?: "BK-${System.currentTimeMillis() % 100000}"

    val dates = remember { BookingViewModel.getNext14Days() }
    val chosenDate = dates.getOrNull(uiState.selectedDateOffset)?.formattedDate ?: "Scheduled date"
    val slot = uiState.selectedSlot ?: "Scheduled time"

    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White),
        elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),
        border = BorderStroke(1.dp, Color(0xFFE2E8F0))
    ) {
        Column(
            modifier = Modifier.padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Icon(
                imageVector = Icons.Default.CheckCircle,
                contentDescription = "Confirmed",
                tint = GreenSafe,
                modifier = Modifier.size(68.dp)
            )

            Spacer(modifier = Modifier.height(14.dp))

            Text(
                text = confirmedTitle,
                fontSize = 24.sp,
                fontWeight = FontWeight.Bold,
                color = TextDark
            )

            Spacer(modifier = Modifier.height(4.dp))

            Text(
                text = "Booking ID: $bookingId",
                fontSize = 15.sp,
                fontWeight = FontWeight.Medium,
                color = PrimaryBlue
            )

            Spacer(modifier = Modifier.height(20.dp))
            HorizontalDivider(color = Color(0xFFE2E8F0))
            Spacer(modifier = Modifier.height(16.dp))

            // Summary lines
            val forWhomDisplay = if (uiState.forWhom == "someone_else") {
                val rel = uiState.relation
                if (!rel.isNullOrBlank()) "${uiState.patientName} ($rel)" else uiState.patientName
            } else {
                "Myself"
            }
            SummaryRow(label = "For", value = forWhomDisplay)
            Spacer(modifier = Modifier.height(8.dp))
            SummaryRow(label = "Service", value = serviceTitle)
            Spacer(modifier = Modifier.height(8.dp))
            SummaryRow(label = "Caregiver", value = "$caregiverName (${uiState.selectedCaregiver?.role ?: "Specialist"})")
            Spacer(modifier = Modifier.height(8.dp))
            SummaryRow(label = "Date", value = chosenDate)
            Spacer(modifier = Modifier.height(8.dp))
            SummaryRow(label = "Time Slot", value = slot)

            if (uiState.service?.isHomeVisit == true) {
                Spacer(modifier = Modifier.height(8.dp))
                SummaryRow(label = "Address", value = uiState.address)
            }

            Spacer(modifier = Modifier.height(28.dp))

            // Add to Calendar button
            Button(
                onClick = {
                    try {
                        val intent = Intent(Intent.ACTION_INSERT).apply {
                            data = CalendarContract.Events.CONTENT_URI
                            putExtra(CalendarContract.Events.TITLE, "CareCompass: $serviceTitle with $caregiverName")
                            putExtra(CalendarContract.Events.DESCRIPTION, "Booking ID: $bookingId\nService: $serviceTitle\nPatient: ${uiState.patientName}")
                            if (uiState.service?.isHomeVisit == true) {
                                putExtra(CalendarContract.Events.EVENT_LOCATION, uiState.address)
                            }
                        }
                        context.startActivity(intent)
                    } catch (e: Exception) {
                        // Fallback if calendar app not available
                    }
                },
                modifier = Modifier.fillMaxWidth().height(56.dp),
                shape = RoundedCornerShape(12.dp),
                colors = ButtonDefaults.buttonColors(containerColor = PrimaryBlue, contentColor = Color.White)
            ) {
                Icon(Icons.Default.Event, contentDescription = null, tint = Color.White)
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = addToCalendarText,
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Bold,
                    color = Color.White
                )
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Back to Home button
            OutlinedButton(
                onClick = {
                    viewModel.reset()
                    onDone()
                },
                modifier = Modifier.fillMaxWidth().height(56.dp),
                shape = RoundedCornerShape(12.dp),
                border = BorderStroke(1.5.dp, PrimaryBlue),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = PrimaryBlue)
            ) {
                Icon(Icons.Default.Home, contentDescription = null, tint = PrimaryBlue)
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = backHomeText,
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Bold,
                    color = PrimaryBlue
                )
            }
        }
    }
}

@Composable
private fun SummaryRow(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.Top
    ) {
        Text(
            text = label,
            fontSize = 15.sp,
            color = TextGray,
            modifier = Modifier.weight(1f)
        )
        Text(
            text = value,
            fontSize = 15.sp,
            fontWeight = FontWeight.Bold,
            color = TextDark,
            textAlign = TextAlign.End,
            modifier = Modifier.weight(2f)
        )
    }
}

private fun buildConfirmationSpeech(
    lang: String,
    serviceTitle: String,
    caregiverName: String,
    slot: String,
    bookingId: String
): String {
    return when (lang) {
        "hi" -> "$serviceTitle के लिए $caregiverName के साथ $slot पर आपकी बुकिंग कन्फर्म हो गई है। बुकिंग आईडी $bookingId है।"
        "hinglish" -> "Aapki $serviceTitle ki booking $caregiverName ke saath $slot par confirm ho gayi hai. Booking ID $bookingId hai."
        else -> "Your booking for $serviceTitle with $caregiverName at $slot is confirmed. Booking ID is $bookingId."
    }
}
