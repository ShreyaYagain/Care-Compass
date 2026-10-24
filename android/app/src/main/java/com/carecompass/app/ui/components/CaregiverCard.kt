package com.carecompass.app.ui.components

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.carecompass.app.data.MatchedCaregiver
import com.carecompass.app.ui.theme.GreenSafe
import com.carecompass.app.ui.theme.PrimaryBlue

@Composable
fun CaregiverCard(
    caregiver: MatchedCaregiver,
    onBookClick: () -> Unit = {},
    modifier: Modifier = Modifier,
    isSelected: Boolean = false,
    onSelect: (() -> Unit)? = null,
    showBookButton: Boolean = true
) {
    val displayName = caregiver.name?.takeIf { it.isNotBlank() } ?: "Caregiver ${caregiver.caregiverId}"
    val roleDisplay = when (caregiver.role?.lowercase()) {
        "medic" -> "Medic"
        "doctor" -> "Doctor"
        "phlebotomist" -> "Lab technician"
        else -> caregiver.role?.replaceFirstChar { it.uppercase() } ?: "Caregiver"
    }

    val ratingValue = caregiver.rating ?: 4.5
    val freeWindow = "Free ${caregiver.freeFrom ?: "09:00"}–${caregiver.freeUntil ?: "18:00"}"
    val langs = if (caregiver.languages.isNotEmpty()) caregiver.languages.joinToString(", ") else "Hindi, English"

    val cardBorder = if (isSelected) BorderStroke(2.dp, PrimaryBlue) else null
    val cardBg = if (isSelected) PrimaryBlue.copy(alpha = 0.05f) else Color.White

    Card(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp)
            .then(if (onSelect != null) Modifier.clickable { onSelect() } else Modifier),
        shape = RoundedCornerShape(16.dp),
        border = cardBorder,
        elevation = CardDefaults.cardElevation(defaultElevation = if (isSelected) 6.dp else 4.dp),
        colors = CardDefaults.cardColors(containerColor = cardBg)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            // Header: Name & Rating
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            text = displayName,
                            fontSize = 20.sp,
                            fontWeight = FontWeight.Bold,
                            color = Color(0xFF212121)
                        )
                        if (isSelected) {
                            Spacer(modifier = Modifier.width(8.dp))
                            Icon(
                                imageVector = Icons.Default.CheckCircle,
                                contentDescription = "Selected",
                                tint = PrimaryBlue,
                                modifier = Modifier.size(20.dp)
                            )
                        }
                    }
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        Surface(
                            shape = RoundedCornerShape(6.dp),
                            color = PrimaryBlue.copy(alpha = 0.1f)
                        ) {
                            Text(
                                text = roleDisplay,
                                fontSize = 13.sp,
                                fontWeight = FontWeight.Bold,
                                color = PrimaryBlue,
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                            )
                        }
                        if (!caregiver.qualification.isNullOrBlank()) {
                            Text(
                                text = caregiver.qualification,
                                fontSize = 13.sp,
                                color = Color(0xFF757575),
                                fontWeight = FontWeight.Medium
                            )
                        }
                    }
                }

                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = GreenSafe.copy(alpha = 0.15f)
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            imageVector = Icons.Default.Star,
                            contentDescription = "Rating",
                            tint = Color(0xFFF57F17),
                            modifier = Modifier.size(18.dp)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text(
                            text = String.format("%.1f", ratingValue),
                            fontWeight = FontWeight.Bold,
                            color = GreenSafe,
                            fontSize = 16.sp
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(10.dp))

            // Details: Free window & distance
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(16.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Default.Schedule,
                        contentDescription = "Free Window",
                        tint = Color(0xFF616161),
                        modifier = Modifier.size(16.dp)
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        text = freeWindow,
                        fontSize = 14.sp,
                        color = Color(0xFF616161),
                        fontWeight = FontWeight.Medium
                    )
                }

                // Hide distance for video consults (doctor role or distanceKm == null)
                if (caregiver.distanceKm != null && caregiver.role?.lowercase() != "doctor") {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            imageVector = Icons.Default.LocationOn,
                            contentDescription = "Distance",
                            tint = Color(0xFF616161),
                            modifier = Modifier.size(16.dp)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text(
                            text = "${caregiver.distanceKm} km",
                            fontSize = 14.sp,
                            color = Color(0xFF616161),
                            fontWeight = FontWeight.Medium
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(6.dp))

            // Languages
            Text(
                text = "Languages: $langs",
                fontSize = 13.sp,
                color = Color(0xFF757575)
            )

            Spacer(modifier = Modifier.height(8.dp))

            // Reason line (factual from matching factors)
            Text(
                text = caregiver.reason,
                fontSize = 15.sp,
                color = Color(0xFF424242),
                lineHeight = 20.sp
            )

            if (showBookButton) {
                Spacer(modifier = Modifier.height(14.dp))

                // Button: White, bold, at least 18sp
                Button(
                    onClick = onBookClick,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(52.dp),
                    shape = RoundedCornerShape(10.dp),
                    colors = ButtonDefaults.buttonColors(
                        containerColor = PrimaryBlue,
                        contentColor = Color.White
                    )
                ) {
                    Text(
                        text = "Select & Book",
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold,
                        color = Color.White
                    )
                }
            }
        }
    }
}
