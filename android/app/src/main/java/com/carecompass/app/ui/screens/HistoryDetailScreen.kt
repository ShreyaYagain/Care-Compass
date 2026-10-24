package com.carecompass.app.ui.screens

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.carecompass.app.R
import com.carecompass.app.data.HistoryDetail
import com.carecompass.app.data.HistoryStep
import com.carecompass.app.ui.components.BigButton
import com.carecompass.app.ui.components.CommonFooter
import com.carecompass.app.ui.components.LanguageToggle
import com.carecompass.app.ui.theme.AmberWarning
import com.carecompass.app.ui.theme.EmergencyRed
import com.carecompass.app.ui.theme.GreenSafe
import com.carecompass.app.ui.theme.PrimaryBlue
import com.carecompass.app.ui.theme.SurfaceBackground
import com.carecompass.app.ui.theme.TextDark
import com.carecompass.app.ui.theme.TextGray
import com.carecompass.app.viewmodel.HistoryViewModel

@Composable
fun HistoryDetailScreen(
    viewModel: HistoryViewModel,
    selectedLanguage: String,
    onLanguageSelected: (String) -> Unit,
    onBack: () -> Unit,
    onViewInBookings: () -> Unit,
    modifier: Modifier = Modifier
) {
    val uiState by viewModel.uiState.collectAsState()
    val detail = uiState.selectedDetail

    val titleText = when (selectedLanguage) {
        "hi" -> stringResource(R.string.history_detail_title_hi)
        "hinglish" -> stringResource(R.string.history_detail_title_hinglish)
        else -> stringResource(R.string.history_detail_title_en)
    }

    val deleteChatLabel = when (selectedLanguage) {
        "hi" -> stringResource(R.string.btn_delete_chat_hi)
        "hinglish" -> stringResource(R.string.btn_delete_chat_hinglish)
        else -> stringResource(R.string.btn_delete_chat_en)
    }

    // Delete Confirmation Dialog
    if (uiState.showDeleteConfirmDialog) {
        val dialogTitle = when (selectedLanguage) {
            "hi" -> stringResource(R.string.dialog_delete_title_hi)
            "hinglish" -> stringResource(R.string.dialog_delete_title_hinglish)
            else -> stringResource(R.string.dialog_delete_title_en)
        }
        val dialogMsg = when (selectedLanguage) {
            "hi" -> stringResource(R.string.dialog_delete_msg_hi)
            "hinglish" -> stringResource(R.string.dialog_delete_msg_hinglish)
            else -> stringResource(R.string.dialog_delete_msg_en)
        }
        val confirmText = when (selectedLanguage) {
            "hi" -> stringResource(R.string.btn_delete_confirm_hi)
            "hinglish" -> stringResource(R.string.btn_delete_confirm_hinglish)
            else -> stringResource(R.string.btn_delete_confirm_en)
        }
        val cancelText = when (selectedLanguage) {
            "hi" -> stringResource(R.string.btn_cancel_hi)
            "hinglish" -> stringResource(R.string.btn_cancel_hinglish)
            else -> stringResource(R.string.btn_cancel_en)
        }

        AlertDialog(
            onDismissRequest = { viewModel.dismissDeleteDialog() },
            icon = { Icon(Icons.Default.DeleteForever, contentDescription = null, tint = EmergencyRed) },
            title = { Text(dialogTitle, fontWeight = FontWeight.Bold, fontSize = 20.sp) },
            text = { Text(dialogMsg, fontSize = 16.sp) },
            confirmButton = {
                Button(
                    onClick = {
                        viewModel.confirmDelete {
                            onBack()
                        }
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = EmergencyRed)
                ) {
                    Text(confirmText, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                }
            },
            dismissButton = {
                OutlinedButton(onClick = { viewModel.dismissDeleteDialog() }) {
                    Text(cancelText, fontSize = 16.sp)
                }
            }
        )
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(SurfaceBackground)
            .padding(horizontal = 16.dp, vertical = 12.dp)
            .verticalScroll(rememberScrollState())
    ) {
        // Top Bar: Back Button, Title, Language Toggle, Delete Icon
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            IconButton(
                onClick = onBack,
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
                text = titleText,
                fontSize = 22.sp,
                fontWeight = FontWeight.Bold,
                color = PrimaryBlue,
                modifier = Modifier
                    .weight(1f)
                    .padding(horizontal = 6.dp)
            )

            LanguageToggle(
                selectedLanguage = selectedLanguage,
                onLanguageSelected = onLanguageSelected
            )

            Spacer(modifier = Modifier.width(6.dp))

            IconButton(
                onClick = {
                    if (detail != null) {
                        viewModel.promptDelete(detail.id)
                    }
                },
                modifier = Modifier.size(48.dp)
            ) {
                Icon(
                    imageVector = Icons.Default.Delete,
                    contentDescription = deleteChatLabel,
                    tint = Color(0xFFB91C1C),
                    modifier = Modifier.size(26.dp)
                )
            }
        }

        if (detail == null) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(40.dp),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator(color = PrimaryBlue)
            }
        } else {
            // Vertical Timeline replay
            val steps = detail.steps

            steps.forEachIndexed { index, step ->
                TimelineItemRow(
                    step = step,
                    isLast = index == steps.lastIndex,
                    selectedLanguage = selectedLanguage,
                    onViewInBookings = onViewInBookings
                )
            }

            Spacer(modifier = Modifier.height(24.dp))
            CommonFooter(selectedLanguage = selectedLanguage)
        }
    }
}

@Composable
private fun TimelineItemRow(
    step: HistoryStep,
    isLast: Boolean,
    selectedLanguage: String,
    onViewInBookings: () -> Unit
) {
    val isEmergency = step.type == "emergency_alert" || step.urgency == "emergency"

    val (icon, nodeColor) = when (step.type) {
        "user_said" -> Pair(Icons.Default.Person, PrimaryBlue)
        "follow_up" -> Pair(Icons.Default.QuestionAnswer, PrimaryBlue)
        "result" -> Pair(Icons.Default.MedicalServices, if (isEmergency) EmergencyRed else PrimaryBlue)
        "caregivers" -> Pair(Icons.Default.Group, PrimaryBlue)
        "booking" -> Pair(Icons.Default.CalendarMonth, GreenSafe)
        "emergency_alert" -> Pair(Icons.Default.Warning, EmergencyRed)
        else -> Pair(Icons.Default.Info, PrimaryBlue)
    }

    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.Top
    ) {
        // Vertical line with icon circle
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.width(44.dp)
        ) {
            Surface(
                shape = CircleShape,
                color = nodeColor,
                modifier = Modifier.size(36.dp)
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(
                        imageVector = icon,
                        contentDescription = null,
                        tint = Color.White,
                        modifier = Modifier.size(20.dp)
                    )
                }
            }

            if (!isLast) {
                Box(
                    modifier = Modifier
                        .width(3.dp)
                        .heightIn(min = 90.dp)
                        .background(Color(0xFFCBD5E1))
                )
            }
        }

        Spacer(modifier = Modifier.width(12.dp))

        // Step Content Card
        Column(
            modifier = Modifier
                .weight(1f)
                .padding(bottom = if (isLast) 12.dp else 24.dp)
        ) {
            TimelineCardContent(
                step = step,
                selectedLanguage = selectedLanguage,
                onViewInBookings = onViewInBookings
            )
        }
    }
}

@Composable
private fun TimelineCardContent(
    step: HistoryStep,
    selectedLanguage: String,
    onViewInBookings: () -> Unit
) {
    when (step.type) {
        "user_said" -> {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = Color.White),
                border = BorderStroke(1.dp, Color(0xFFE2E8F0))
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        val youSaidLabel = when (selectedLanguage) {
                            "hi" -> stringResource(R.string.step_you_said_hi)
                            "hinglish" -> stringResource(R.string.step_you_said_hinglish)
                            else -> stringResource(R.string.step_you_said_en)
                        }

                        Text(
                            text = youSaidLabel,
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold,
                            color = PrimaryBlue
                        )

                        if (step.isVoice) {
                            val viaVoiceLabel = when (selectedLanguage) {
                                "hi" -> stringResource(R.string.tag_via_voice_hi)
                                "hinglish" -> stringResource(R.string.tag_via_voice_hinglish)
                                else -> stringResource(R.string.tag_via_voice_en)
                            }
                            Surface(
                                shape = RoundedCornerShape(10.dp),
                                color = PrimaryBlue.copy(alpha = 0.12f)
                            ) {
                                Row(
                                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Icon(Icons.Default.Mic, contentDescription = null, tint = PrimaryBlue, modifier = Modifier.size(16.dp))
                                    Spacer(modifier = Modifier.width(4.dp))
                                    Text(
                                        text = viaVoiceLabel,
                                        fontSize = 13.sp,
                                        fontWeight = FontWeight.SemiBold,
                                        color = PrimaryBlue
                                    )
                                }
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(10.dp))

                    Text(
                        text = step.subtitle ?: step.title,
                        fontSize = 18.sp,
                        color = TextDark,
                        lineHeight = 26.sp
                    )
                }
            }
        }

        "follow_up" -> {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = Color.White),
                border = BorderStroke(1.dp, Color(0xFFE2E8F0))
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = step.title,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = TextDark,
                        lineHeight = 24.sp
                    )

                    if (!step.userAnswer.isNullOrBlank()) {
                        Spacer(modifier = Modifier.height(12.dp))
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text(
                                text = "Answer: ",
                                fontSize = 16.sp,
                                color = TextGray
                            )
                            Surface(
                                shape = RoundedCornerShape(8.dp),
                                color = PrimaryBlue.copy(alpha = 0.1f)
                            ) {
                                Text(
                                    text = step.userAnswer,
                                    fontSize = 16.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = PrimaryBlue,
                                    modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp)
                                )
                            }
                        }
                    }
                }
            }
        }

        "emergency_alert" -> {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = EmergencyRed.copy(alpha = 0.08f)),
                border = BorderStroke(1.5.dp, EmergencyRed)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    val alertHeading = when (selectedLanguage) {
                        "hi" -> stringResource(R.string.step_emergency_alert_hi)
                        "hinglish" -> stringResource(R.string.step_emergency_alert_hinglish)
                        else -> stringResource(R.string.step_emergency_alert_en)
                    }

                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.Warning, contentDescription = null, tint = EmergencyRed, modifier = Modifier.size(24.dp))
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = alertHeading,
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold,
                            color = EmergencyRed
                        )
                    }

                    if (!step.emergencyText.isNullOrBlank()) {
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = step.emergencyText,
                            fontSize = 18.sp,
                            color = TextDark,
                            lineHeight = 24.sp
                        )
                    }
                }
            }
        }

        "result" -> {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = Color.White),
                border = BorderStroke(1.dp, Color(0xFFE2E8F0))
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    val resultHeading = when (selectedLanguage) {
                        "hi" -> stringResource(R.string.step_result_hi)
                        "hinglish" -> stringResource(R.string.step_result_hinglish)
                        else -> stringResource(R.string.step_result_en)
                    }

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = "$resultHeading: ${step.careType ?: "Recommended Care"}",
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold,
                            color = TextDark
                        )

                        val urgency = step.urgency?.lowercase() ?: "scheduled"
                        val (chipText, chipColor, chipBg) = when (urgency) {
                            "emergency" -> Triple("Emergency", EmergencyRed, Color(0xFFFFEBEE))
                            "same_day", "sameday" -> Triple("Same-Day", AmberWarning, Color(0xFFFFF3E0))
                            else -> Triple("Scheduled", PrimaryBlue, Color(0xFFE8F0FE))
                        }

                        Surface(shape = RoundedCornerShape(8.dp), color = chipBg) {
                            Text(
                                text = chipText,
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Bold,
                                color = chipColor,
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                            )
                        }
                    }

                    if (!step.reasoning.isNullOrBlank()) {
                        Spacer(modifier = Modifier.height(10.dp))
                        Text(
                            text = step.reasoning,
                            fontSize = 18.sp,
                            color = TextDark,
                            lineHeight = 26.sp
                        )
                    }
                }
            }
        }

        "caregivers" -> {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = Color.White),
                border = BorderStroke(1.dp, Color(0xFFE2E8F0))
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    val caregiversHeading = when (selectedLanguage) {
                        "hi" -> stringResource(R.string.step_caregivers_hi)
                        "hinglish" -> stringResource(R.string.step_caregivers_hinglish)
                        else -> stringResource(R.string.step_caregivers_en)
                    }

                    Text(
                        text = caregiversHeading,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold,
                        color = PrimaryBlue
                    )

                    Spacer(modifier = Modifier.height(12.dp))

                    step.suggestedCaregivers.forEach { name ->
                        val isChosen = name.equals(step.chosenCaregiver, ignoreCase = true)
                        val bg = if (isChosen) PrimaryBlue else Color(0xFFF1F5F9)
                        val textCol = if (isChosen) Color.White else TextDark

                        Surface(
                            shape = RoundedCornerShape(10.dp),
                            color = bg,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 4.dp)
                        ) {
                            Row(
                                modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                if (isChosen) {
                                    Icon(Icons.Default.CheckCircle, contentDescription = "Chosen", tint = Color.White, modifier = Modifier.size(20.dp))
                                    Spacer(modifier = Modifier.width(8.dp))
                                } else {
                                    Icon(Icons.Default.Person, contentDescription = null, tint = TextGray, modifier = Modifier.size(20.dp))
                                    Spacer(modifier = Modifier.width(8.dp))
                                }
                                Text(
                                    text = name,
                                    fontSize = 18.sp,
                                    fontWeight = if (isChosen) FontWeight.Bold else FontWeight.Medium,
                                    color = textCol
                                )
                            }
                        }
                    }
                }
            }
        }

        "booking" -> {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = Color.White),
                border = BorderStroke(1.5.dp, GreenSafe.copy(alpha = 0.5f))
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    val bookingHeading = when (selectedLanguage) {
                        "hi" -> stringResource(R.string.step_booking_hi)
                        "hinglish" -> stringResource(R.string.step_booking_hinglish)
                        else -> stringResource(R.string.step_booking_en)
                    }

                    val viewInBookingsText = when (selectedLanguage) {
                        "hi" -> stringResource(R.string.btn_view_in_bookings_hi)
                        "hinglish" -> stringResource(R.string.btn_view_in_bookings_hinglish)
                        else -> stringResource(R.string.btn_view_in_bookings_en)
                    }

                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.CheckCircle, contentDescription = null, tint = GreenSafe, modifier = Modifier.size(24.dp))
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = bookingHeading,
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold,
                            color = GreenSafe
                        )
                    }

                    Spacer(modifier = Modifier.height(10.dp))

                    Text(
                        text = "Caregiver: ${step.chosenCaregiver ?: "Assigned Caregiver"}",
                        fontSize = 18.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = TextDark
                    )

                    Spacer(modifier = Modifier.height(4.dp))

                    Text(
                        text = "Date & Time: ${step.bookingDate ?: ""} ${step.bookingTime ?: ""}",
                        fontSize = 16.sp,
                        color = TextGray
                    )

                    Spacer(modifier = Modifier.height(14.dp))

                    Button(
                        onClick = onViewInBookings,
                        colors = ButtonDefaults.buttonColors(containerColor = PrimaryBlue),
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.fillMaxWidth().height(56.dp)
                    ) {
                        Icon(Icons.Default.CalendarMonth, contentDescription = null)
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(viewInBookingsText, fontSize = 18.sp, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }
    }
}
