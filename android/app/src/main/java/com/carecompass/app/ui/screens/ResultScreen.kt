package com.carecompass.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.MedicalServices
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.carecompass.app.data.CardLines
import com.carecompass.app.data.SecondaryOption
import com.carecompass.app.ui.components.BigButton
import com.carecompass.app.ui.components.CaregiverCard
import com.carecompass.app.ui.theme.AmberWarning
import com.carecompass.app.ui.theme.GreenSafe
import com.carecompass.app.ui.theme.PrimaryBlue
import com.carecompass.app.viewmodel.TriageUiState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ResultScreen(
    uiState: TriageUiState,
    onBookCaregiver: (String) -> Unit,
    onStartOver: () -> Unit,
    modifier: Modifier = Modifier
) {
    val resp = uiState.latestResponse
    val careType = resp?.careType ?: "teleconsultation"
    val urgency = resp?.urgency ?: "same_day"
    val caregivers = resp?.matchedCaregivers ?: emptyList()
    val isEmergency = careType == "emergency_112" || urgency == "emergency"
    val lines: CardLines? = resp?.cardLines

    val (urgencyColor, urgencyBg, urgencyLabel) = when (urgency) {
        "scheduled" -> Triple(GreenSafe, GreenSafe.copy(alpha = 0.12f), "Scheduled")
        "same_day" -> Triple(AmberWarning, AmberWarning.copy(alpha = 0.12f), "Same-Day")
        "emergency" -> Triple(Color(0xFFD32F2F), Color(0xFFD32F2F).copy(alpha = 0.12f), "Emergency")
        else -> Triple(AmberWarning, AmberWarning.copy(alpha = 0.12f), "Same-Day")
    }

    val careTypeTitle = when (careType) {
        "paramedic_home_visit" -> "Medic home visit"
        "home_nursing" -> "Home nursing"
        "lab_test_home" -> "Lab test at home"
        "teleconsultation" -> "Doctor video consult"
        "emergency_112" -> "Emergency"
        else -> careType.replace("_", " ").replaceFirstChar { it.uppercase() }
    }

    var showDetailsSheet by remember { mutableStateOf(false) }

    if (showDetailsSheet) {
        ModalBottomSheet(onDismissRequest = { showDetailsSheet = false }) {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 20.dp, vertical = 8.dp)
                    .padding(bottom = 28.dp)
            ) {
                Text(
                    text = "How we got this result",
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Bold,
                    color = Color(0xFF212121)
                )
                Spacer(modifier = Modifier.height(12.dp))

                val details = resp?.details
                DetailRow("Symptoms used", (details?.symptoms ?: emptyList()).joinToString(", ").ifBlank { "—" })
                if (details != null && details.answers.isNotEmpty()) {
                    DetailRow("Your answers", details.answers.entries.joinToString(", ") { "${it.key}: ${it.value}" })
                }
                val ctx = details?.contextUsed ?: resp?.contextUsed
                val ctxText = listOfNotNull(
                    ctx?.location, ctx?.weather, ctx?.aqi?.let { "AQI $it" },
                    ctx?.season?.replace("_", " "), ctx?.time
                ).joinToString(", ").ifBlank { null }
                DetailRow("Context used", ctxText ?: "Not used")
                DetailRow("Confidence", details?.confidence?.let { "${(it * 100).toInt()}%" } ?: "—")
                DetailRow("Care type", details?.careType ?: careType)
                DetailRow("Urgency", details?.urgency ?: urgency)
                if (details != null && details.redFlags.isNotEmpty()) {
                    DetailRow("Red flags", details.redFlags.joinToString(", ").replace("_", " "))
                }

                Spacer(modifier = Modifier.height(16.dp))
                Button(
                    onClick = { showDetailsSheet = false },
                    modifier = Modifier.fillMaxWidth().height(48.dp),
                    shape = RoundedCornerShape(10.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = PrimaryBlue)
                ) {
                    Text("Close", fontWeight = FontWeight.Bold, color = Color.White)
                }
            }
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(Color(0xFFF8F9FA))
            .padding(16.dp)
            .verticalScroll(rememberScrollState())
    ) {
        // Result card
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(
                containerColor = if (isEmergency) Color(0xFFFFEBEE) else Color.White
            ),
            elevation = CardDefaults.cardElevation(defaultElevation = 3.dp)
        ) {
            Column(modifier = Modifier.padding(18.dp)) {
                // Title + urgency badge
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            imageVector = Icons.Default.MedicalServices,
                            contentDescription = "Care",
                            tint = if (isEmergency) Color(0xFFD32F2F) else PrimaryBlue,
                            modifier = Modifier.size(28.dp)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = careTypeTitle,
                            fontSize = 22.sp,
                            fontWeight = FontWeight.Bold,
                            color = Color(0xFF212121)
                        )
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Surface(
                            shape = RoundedCornerShape(8.dp),
                            color = urgencyBg
                        ) {
                            Text(
                                text = urgencyLabel.uppercase(),
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Black,
                                color = urgencyColor,
                                modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp)
                            )
                        }
                        Spacer(modifier = Modifier.width(8.dp))
                        Icon(
                            imageVector = Icons.Default.Info,
                            contentDescription = "Details",
                            tint = Color(0xFF757575),
                            modifier = Modifier
                                .size(20.dp)
                                .clickable { showDetailsSheet = true }
                        )
                    }
                }

                Spacer(modifier = Modifier.height(14.dp))

                if (isEmergency) {
                    // Emergency card: big call-to-action + fixed steps.
                    Text(
                        text = "Call 112 now",
                        fontSize = 28.sp,
                        fontWeight = FontWeight.Black,
                        color = Color(0xFFD32F2F)
                    )
                    if (!lines?.why.isNullOrBlank()) {
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = lines?.why ?: "",
                            fontSize = 17.sp,
                            color = Color(0xFF424242),
                            lineHeight = 24.sp
                        )
                    }
                    resp?.emergencySteps?.takeIf { it.isNotEmpty() }?.let { steps ->
                        Spacer(modifier = Modifier.height(12.dp))
                        Text(
                            text = "First aid steps",
                            fontSize = 15.sp,
                            fontWeight = FontWeight.Bold,
                            color = Color(0xFF212121)
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        steps.forEachIndexed { index, step ->
                            Text(
                                text = "${index + 1}. $step",
                                fontSize = 15.sp,
                                color = Color(0xFF424242),
                                lineHeight = 22.sp
                            )
                        }
                    }
                } else {
                    // Short lines, no passage.
                    CardLine(label = "Why", text = lines?.why ?: (resp?.reasoning ?: ""))
                    if (!lines?.contextLine.isNullOrBlank()) {
                        CardLine(label = "", text = lines?.contextLine ?: "", highlight = true)
                    }
                    CardLine(label = "Next", text = lines?.next ?: "")
                    if (!lines?.watchFor.isNullOrBlank()) {
                        Spacer(modifier = Modifier.height(10.dp))
                        Text(
                            text = "Watch for:",
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Bold,
                            color = Color(0xFFB71C1C)
                        )
                        Text(
                            text = lines?.watchFor ?: "",
                            fontSize = 15.sp,
                            color = Color(0xFF424242),
                            lineHeight = 22.sp
                        )
                    }
                }
            }
        }

        // Caregiver list (never on emergency results)
        if (!isEmergency) {
            Spacer(modifier = Modifier.height(20.dp))

            Text(
                text = "Recommended Caregivers",
                fontSize = 18.sp,
                fontWeight = FontWeight.Bold,
                color = Color(0xFF212121)
            )
            Text(
                text = "Ranked by proximity, slot availability, skill, and language",
                fontSize = 14.sp,
                color = Color(0xFF757575)
            )

            Spacer(modifier = Modifier.height(12.dp))

            if (caregivers.isEmpty()) {
                Text(
                    text = "No caregiver free right now. Try a doctor video consult.",
                    fontSize = 16.sp,
                    color = Color.Gray,
                    modifier = Modifier.padding(vertical = 16.dp)
                )
            } else {
                caregivers.forEach { cg ->
                    CaregiverCard(
                        caregiver = cg,
                        onBookClick = { onBookCaregiver(cg.caregiverId) }
                    )
                }
            }

            val secondary = resp?.secondaryOptions ?: emptyList()
            if (secondary.isNotEmpty()) {
                Spacer(modifier = Modifier.height(24.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Other ways to see a doctor",
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold,
                        color = Color(0xFF212121)
                    )
                    Surface(
                        color = Color(0xFFEEEEEE),
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Text(
                            text = "demo data",
                            fontSize = 11.sp,
                            fontWeight = FontWeight.SemiBold,
                            color = Color(0xFF616161),
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp)
                        )
                    }
                }
                Text(
                    text = "Hospital OPD appointments and doctors who visit home",
                    fontSize = 14.sp,
                    color = Color(0xFF757575)
                )
                Spacer(modifier = Modifier.height(10.dp))
                secondary.forEach { opt ->
                    SecondaryDoctorCard(
                        option = opt,
                        onBookClick = { onBookCaregiver(opt.caregiverId) }
                    )
                }
            }

            Spacer(modifier = Modifier.height(20.dp))

            BigButton(
                text = "Return to Home",
                onClick = onStartOver
            )
        }
    }
}

@Composable
private fun CardLine(label: String, text: String, highlight: Boolean = false) {
    if (text.isBlank()) return
    Spacer(modifier = Modifier.height(10.dp))
    if (label.isNotBlank()) {
        Text(
            text = "$label:",
            fontSize = 14.sp,
            fontWeight = FontWeight.Bold,
            color = if (highlight) PrimaryBlue else Color(0xFF212121)
        )
    }
    Text(
        text = text,
        fontSize = if (label.isBlank()) 15.sp else 17.sp,
        color = if (highlight) PrimaryBlue else Color(0xFF424242),
        lineHeight = 24.sp,
        fontWeight = if (label.isBlank()) FontWeight.Medium else FontWeight.Normal
    )
}

@Composable
private fun DetailRow(label: String, value: String) {
    Column(modifier = Modifier.padding(vertical = 4.dp)) {
        Text(
            text = label,
            fontSize = 12.sp,
            fontWeight = FontWeight.Bold,
            color = Color(0xFF757575)
        )
        Text(
            text = value,
            fontSize = 15.sp,
            color = Color(0xFF212121),
            lineHeight = 20.sp
        )
    }
}

@Composable
private fun SecondaryDoctorCard(
    option: SecondaryOption,
    onBookClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "${option.name}, ${option.qualification}",
                    fontWeight = FontWeight.Bold,
                    fontSize = 15.sp,
                    color = Color(0xFF212121)
                )
                Surface(
                    color = Color(0xFFFFF3E0),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Text(
                        text = "★ ${option.rating}",
                        fontWeight = FontWeight.Bold,
                        fontSize = 13.sp,
                        color = Color(0xFFE65100),
                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                    )
                }
            }
            Spacer(modifier = Modifier.height(4.dp))
            val venueText = when (option.venue) {
                "hospital" -> option.facilityName?.let { "Hospital OPD · $it" } ?: "Hospital OPD"
                "home" -> "Doctor Home Consult"
                else -> "Virtual Consultation"
            }
            val deptText = option.department.replace("_", " ").replaceFirstChar { it.uppercase() }
            Text(
                text = "$deptText · $venueText",
                fontSize = 13.sp,
                color = PrimaryBlue,
                fontWeight = FontWeight.Medium
            )
            if (option.languages.isNotEmpty()) {
                Spacer(modifier = Modifier.height(3.dp))
                Text(
                    text = "Languages: " + option.languages.joinToString(", "),
                    fontSize = 12.sp,
                    color = Color(0xFF757575)
                )
            }
            Spacer(modifier = Modifier.height(10.dp))
            OutlinedButton(
                onClick = onBookClick,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(42.dp),
                shape = RoundedCornerShape(10.dp),
                border = BorderStroke(1.5.dp, PrimaryBlue),
                colors = ButtonDefaults.outlinedButtonColors(contentColor = PrimaryBlue)
            ) {
                Text(
                    text = if (option.venue == "hospital") "Select & Book OPD" else "Select & Book",
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold
                )
            }
        }
    }
}
