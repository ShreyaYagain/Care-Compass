package com.carecompass.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.MedicalServices
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.carecompass.app.ui.components.CaregiverCard
import com.carecompass.app.ui.theme.AmberWarning
import com.carecompass.app.ui.theme.GreenSafe
import com.carecompass.app.ui.theme.PrimaryBlue
import com.carecompass.app.viewmodel.TriageUiState

@Composable
fun ResultScreen(
    uiState: TriageUiState,
    onBookCaregiver: (String) -> Unit,
    onStartOver: () -> Unit,
    modifier: Modifier = Modifier
) {
    val resp = uiState.latestResponse
    val careType = resp?.careType ?: "paramedic_home_visit"
    val urgency = resp?.urgency ?: "same_day"
    val reasoning = resp?.reasoning ?: "Fever with cough for 2 days, no breathing difficulty reported."
    val caregivers = resp?.matchedCaregivers ?: emptyList()

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
        "emergency_112" -> "Emergency (112)"
        else -> careType.replace("_", " ").capitalize()
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(Color(0xFFF8F9FA))
            .padding(16.dp)
            .verticalScroll(rememberScrollState())
    ) {
        // Triage Header Card
        Card(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(16.dp),
            colors = CardDefaults.cardColors(containerColor = Color.White),
            elevation = CardDefaults.cardElevation(defaultElevation = 3.dp)
        ) {
            Column(modifier = Modifier.padding(18.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            imageVector = Icons.Default.MedicalServices,
                            contentDescription = "Care",
                            tint = PrimaryBlue,
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

                    // Urgency Chip
                    Surface(
                        shape = RoundedCornerShape(8.dp),
                        color = urgencyBg
                    ) {
                        Text(
                            text = urgency.replace("_", "-").toUpperCase(),
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Black,
                            color = urgencyColor,
                            modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp)
                        )
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))

                // Plain Language Reasoning
                Text(
                    text = reasoning,
                    fontSize = 17.sp,
                    color = Color(0xFF424242),
                    lineHeight = 24.sp
                )
            }
        }

        Spacer(modifier = Modifier.height(20.dp))

        // Caregivers recommendation section
        Text(
            text = "Recommended Caregivers (Top Matches)",
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

        Spacer(modifier = Modifier.height(20.dp))

        OutlinedButton(
            onClick = onStartOver,
            modifier = Modifier
                .fillMaxWidth()
                .height(50.dp),
            shape = RoundedCornerShape(10.dp)
        ) {
            Icon(imageVector = Icons.Default.Home, contentDescription = "Home")
            Spacer(modifier = Modifier.width(8.dp))
            Text("Start New Triage", fontSize = 16.sp)
        }
    }
}
