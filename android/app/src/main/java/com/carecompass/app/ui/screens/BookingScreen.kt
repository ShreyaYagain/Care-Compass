package com.carecompass.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.carecompass.app.ui.components.BigButton
import com.carecompass.app.ui.theme.GreenSafe
import com.carecompass.app.ui.theme.PrimaryBlue
import com.carecompass.app.viewmodel.TriageUiState
import com.carecompass.app.viewmodel.TriageViewModel

@Composable
fun BookingScreen(
    caregiverId: String,
    viewModel: TriageViewModel,
    uiState: TriageUiState,
    onDone: () -> Unit,
    modifier: Modifier = Modifier
) {
    var name by remember { mutableStateOf("Rohan Gupta") }
    var phone by remember { mutableStateOf("+91 98765 43210") }
    var selectedSlot by remember { mutableStateOf("today_afternoon") }

    val slots = listOf(
        "today_afternoon" to "Today, 3:30 PM - 5:00 PM",
        "today_evening" to "Today, 6:00 PM - 7:30 PM",
        "tomorrow_morning" to "Tomorrow, 9:00 AM - 10:30 AM"
    )

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(Color(0xFFF8F9FA))
            .padding(20.dp)
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(18.dp)
    ) {
        if (uiState.bookingResponse != null) {
            // Confirmation card
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = Color.White),
                elevation = CardDefaults.cardElevation(defaultElevation = 4.dp)
            ) {
                Column(
                    modifier = Modifier.padding(24.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Icon(
                        imageVector = Icons.Default.CheckCircle,
                        contentDescription = "Confirmed",
                        tint = GreenSafe,
                        modifier = Modifier.size(64.dp)
                    )
                    Spacer(modifier = Modifier.height(16.dp))
                    Text(
                        text = "Booking Confirmed!",
                        fontSize = 24.sp,
                        fontWeight = FontWeight.Bold,
                        color = Color(0xFF212121)
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "Booking ID: ${uiState.bookingResponse.bookingId}",
                        fontSize = 16.sp,
                        color = Color(0xFF757575)
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "Estimated Arrival: ${uiState.bookingResponse.eta ?: "30-45 mins"}",
                        fontSize = 18.sp,
                        fontWeight = FontWeight.SemiBold,
                        color = PrimaryBlue
                    )
                    Spacer(modifier = Modifier.height(24.dp))
                    BigButton(
                        text = "Return to Home",
                        onClick = onDone
                    )
                }
            }
        } else {
            Text(
                text = "Book Caregiver Visit",
                fontSize = 26.sp,
                fontWeight = FontWeight.Bold,
                color = Color(0xFF212121)
            )

            Text(
                text = "Assigning: Caregiver $caregiverId",
                fontSize = 16.sp,
                color = PrimaryBlue,
                fontWeight = FontWeight.SemiBold
            )

            // Slot Selection
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(containerColor = Color.White)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = "Select Time Slot",
                        fontSize = 17.sp,
                        fontWeight = FontWeight.Bold,
                        color = Color(0xFF212121)
                    )
                    Spacer(modifier = Modifier.height(10.dp))
                    slots.forEach { (slotKey, slotLabel) ->
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 4.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            RadioButton(
                                selected = selectedSlot == slotKey,
                                onClick = { selectedSlot = slotKey },
                                colors = RadioButtonDefaults.colors(selectedColor = PrimaryBlue)
                            )
                            Spacer(modifier = Modifier.width(6.dp))
                            Text(text = slotLabel, fontSize = 16.sp)
                        }
                    }
                }
            }

            // Patient Contact Info
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(containerColor = Color.White)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = "Contact Details",
                        fontSize = 17.sp,
                        fontWeight = FontWeight.Bold,
                        color = Color(0xFF212121)
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    OutlinedTextField(
                        value = name,
                        onValueChange = { name = it },
                        label = { Text("Patient / Contact Name") },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(10.dp)
                    )
                    Spacer(modifier = Modifier.height(12.dp))
                    OutlinedTextField(
                        value = phone,
                        onValueChange = { phone = it },
                        label = { Text("Phone Number") },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(10.dp)
                    )
                }
            }

            if (uiState.isLoading) {
                Box(modifier = Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = PrimaryBlue)
                }
            }

            BigButton(
                text = "Confirm Booking",
                onClick = {
                    viewModel.confirmBooking(
                        caregiverId = caregiverId,
                        name = name,
                        phone = phone,
                        slot = selectedSlot
                    )
                }
            )
        }
    }
}
