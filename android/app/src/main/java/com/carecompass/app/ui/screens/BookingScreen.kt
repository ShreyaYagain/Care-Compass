package com.carecompass.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.carecompass.app.ui.components.BigButton
import com.carecompass.app.ui.theme.GreenSafe
import com.carecompass.app.ui.theme.PrimaryBlue
import com.carecompass.app.viewmodel.TriageUiState
import com.carecompass.app.viewmodel.TriageViewModel
import java.util.Calendar

private fun generateCaregiverSlots(freeFrom: String, freeUntil: String): List<Pair<String, String>> {
    fun parseMins(t: String): Int {
        val parts = t.split(":")
        val h = parts.getOrNull(0)?.trim()?.toIntOrNull() ?: 9
        val m = parts.getOrNull(1)?.trim()?.toIntOrNull() ?: 0
        return h * 60 + m
    }

    val freeStart = parseMins(freeFrom)
    val freeEnd = parseMins(freeUntil)

    val now = Calendar.getInstance()
    val currentHour = now.get(Calendar.HOUR_OF_DAY)
    val currentMinute = now.get(Calendar.MINUTE)
    val currentMins = currentHour * 60 + currentMinute

    // Next half hour:
    val nextHalfHour = ((currentMins + 29) / 30) * 30
    val todayStart = maxOf(freeStart, nextHalfHour)

    fun formatTime(mins: Int): String {
        val h24 = (mins / 60) % 24
        val m = mins % 60
        val ampm = if (h24 < 12) "AM" else "PM"
        val h12 = if (h24 == 0) 12 else if (h24 > 12) h24 - 12 else h24
        return String.format("%d:%02d %s", h12, m, ampm)
    }

    val todaySlots = mutableListOf<Pair<String, String>>()
    var slotCursor = todayStart
    while (slotCursor + 90 <= freeEnd) {
        val startStr = formatTime(slotCursor)
        val endStr = formatTime(slotCursor + 90)
        val key = "today_${slotCursor / 60}_${slotCursor % 60}"
        todaySlots.add(key to "Today, $startStr – $endStr")
        slotCursor += 90
    }

    if (todaySlots.isNotEmpty()) {
        return todaySlots
    }

    // If none remain today, generate Tomorrow slots from freeFrom
    val tomorrowSlots = mutableListOf<Pair<String, String>>()
    var tCursor = freeStart
    while (tCursor + 90 <= freeEnd) {
        val startStr = formatTime(tCursor)
        val endStr = formatTime(tCursor + 90)
        val key = "tomorrow_${tCursor / 60}_${tCursor % 60}"
        tomorrowSlots.add(key to "Tomorrow, $startStr – $endStr")
        tCursor += 90
    }

    return if (tomorrowSlots.isNotEmpty()) {
        tomorrowSlots
    } else {
        listOf("tomorrow_morning" to "Tomorrow, 9:00 AM – 10:30 AM")
    }
}

@Composable
fun BookingScreen(
    caregiverId: String,
    viewModel: TriageViewModel,
    uiState: TriageUiState,
    onDone: () -> Unit,
    modifier: Modifier = Modifier
) {
    val matched = uiState.latestResponse?.matchedCaregivers?.find { it.caregiverId == caregiverId }
    val caregiverName = matched?.name?.takeIf { it.isNotBlank() } ?: "Caregiver $caregiverId"
    val caregiverRole = when (matched?.role?.lowercase()) {
        "medic" -> "Medic"
        "doctor" -> "Doctor"
        "phlebotomist" -> "Lab technician"
        else -> matched?.role?.replaceFirstChar { it.uppercase() } ?: "Caregiver"
    }

    val freeFrom = matched?.freeFrom ?: "09:00"
    val freeUntil = matched?.freeUntil ?: "18:00"

    val slots = remember(freeFrom, freeUntil) {
        generateCaregiverSlots(freeFrom, freeUntil)
    }

    var selectedSlot by remember(slots) {
        mutableStateOf(slots.firstOrNull()?.first ?: "today_afternoon")
    }

    var forWhom by remember { mutableStateOf("myself") } // "myself" or "someone_else"
    var patientName by remember { mutableStateOf("") }
    var selectedRelation by remember { mutableStateOf<String?>(null) }
    var contactName by remember { mutableStateOf("Rohan Gupta") }
    var phone by remember { mutableStateOf("9876543210") }
    var attemptedSubmit by remember { mutableStateOf(false) }

    val phoneRegex = Regex("^[6-9]\\d{9}$")
    val isPhoneValid = phone.trim().matches(phoneRegex)
    val isContactNameValid = contactName.trim().isNotBlank()
    val isPatientNameValid = if (forWhom == "someone_else") patientName.trim().isNotBlank() else true

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(Color(0xFFF8F9FA))
            .padding(20.dp)
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(18.dp)
    ) {
        if (uiState.bookingResponse != null) {
            // Confirmation card with full booking summary
            val chosenSlotLabel = slots.find { it.first == selectedSlot }?.second ?: selectedSlot
            val forWhomDisplay = if (uiState.bookingResponse.relation != null && uiState.bookingResponse.relation.isNotBlank()) {
                "${uiState.bookingResponse.patientName ?: "Someone else"} (${uiState.bookingResponse.relation})"
            } else if (!uiState.bookingResponse.patientName.isNullOrBlank() && uiState.bookingResponse.patientName != "Myself") {
                uiState.bookingResponse.patientName
            } else {
                "Myself"
            }

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
                        fontSize = 26.sp,
                        fontWeight = FontWeight.Bold,
                        color = Color(0xFF212121)
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "Booking ID: ${uiState.bookingResponse.bookingId}",
                        fontSize = 15.sp,
                        color = Color(0xFF757575)
                    )

                    Spacer(modifier = Modifier.height(20.dp))
                    HorizontalDivider(color = Color(0xFFEEEEEE))
                    Spacer(modifier = Modifier.height(16.dp))

                    // Booking Summary Details
                    Text(
                        text = "Booking Summary",
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold,
                        color = Color(0xFF212121)
                    )
                    Spacer(modifier = Modifier.height(12.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text("For:", color = Color(0xFF757575), fontSize = 15.sp)
                        Text(forWhomDisplay, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                    }
                    Spacer(modifier = Modifier.height(8.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text("Assigned Caregiver:", color = Color(0xFF757575), fontSize = 15.sp)
                        Text("$caregiverName ($caregiverRole)", fontWeight = FontWeight.Bold, fontSize = 15.sp)
                    }
                    Spacer(modifier = Modifier.height(8.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text("Scheduled Slot:", color = Color(0xFF757575), fontSize = 15.sp)
                        Text(chosenSlotLabel, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                    }
                    Spacer(modifier = Modifier.height(8.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text("Booked by:", color = Color(0xFF757575), fontSize = 15.sp)
                        Text(contactName, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                    }
                    Spacer(modifier = Modifier.height(8.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text("Contact Phone:", color = Color(0xFF757575), fontSize = 15.sp)
                        Text(phone, fontWeight = FontWeight.Bold, fontSize = 15.sp)
                    }

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

            // Assigned Caregiver Banner
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = PrimaryBlue.copy(alpha = 0.08f))
            ) {
                Row(
                    modifier = Modifier.padding(14.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Icon(
                        imageVector = Icons.Default.Person,
                        contentDescription = "Caregiver",
                        tint = PrimaryBlue,
                        modifier = Modifier.size(24.dp)
                    )
                    Spacer(modifier = Modifier.width(10.dp))
                    Column {
                        Text(
                            text = caregiverName,
                            fontSize = 17.sp,
                            fontWeight = FontWeight.Bold,
                            color = PrimaryBlue
                        )
                        Text(
                            text = "$caregiverRole · Free $freeFrom–$freeUntil today",
                            fontSize = 13.sp,
                            color = Color(0xFF555555)
                        )
                    }
                }
            }

            // Slot Selection
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(containerColor = Color.White)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            imageVector = Icons.Default.Schedule,
                            contentDescription = "Time",
                            tint = PrimaryBlue,
                            modifier = Modifier.size(20.dp)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "Select 90-Minute Time Slot",
                            fontSize = 17.sp,
                            fontWeight = FontWeight.Bold,
                            color = Color(0xFF212121)
                        )
                    }
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

            // Step 3 Addition: "Who is this for?" selector
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(containerColor = Color.White)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = "Who is this for?",
                        fontSize = 17.sp,
                        fontWeight = FontWeight.Bold,
                        color = Color(0xFF212121)
                    )
                    Spacer(modifier = Modifier.height(12.dp))

                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        FilterChip(
                            selected = forWhom == "myself",
                            onClick = { forWhom = "myself" },
                            label = { Text("Myself", fontSize = 15.sp, fontWeight = FontWeight.SemiBold) },
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = PrimaryBlue,
                                selectedLabelColor = Color.White
                            )
                        )
                        FilterChip(
                            selected = forWhom == "someone_else",
                            onClick = { forWhom = "someone_else" },
                            label = { Text("Someone else", fontSize = 15.sp, fontWeight = FontWeight.SemiBold) },
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = PrimaryBlue,
                                selectedLabelColor = Color.White
                            )
                        )
                    }

                    if (forWhom == "someone_else") {
                        Spacer(modifier = Modifier.height(14.dp))
                        OutlinedTextField(
                            value = patientName,
                            onValueChange = { patientName = it },
                            label = { Text("Patient Name *") },
                            placeholder = { Text("e.g. Ramesh Gupta") },
                            isError = attemptedSubmit && !isPatientNameValid,
                            supportingText = {
                                if (attemptedSubmit && !isPatientNameValid) {
                                    Text("Patient name is required", color = MaterialTheme.colorScheme.error)
                                }
                            },
                            modifier = Modifier.fillMaxWidth(),
                            shape = RoundedCornerShape(10.dp)
                        )

                        Spacer(modifier = Modifier.height(10.dp))
                        Text(
                            text = "Relation",
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Medium,
                            color = Color(0xFF555555)
                        )
                        Spacer(modifier = Modifier.height(6.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            listOf("Papa", "Mama", "Child", "Other").forEach { rel ->
                                FilterChip(
                                    selected = selectedRelation == rel,
                                    onClick = {
                                        selectedRelation = if (selectedRelation == rel) null else rel
                                    },
                                    label = { Text(rel, fontSize = 14.sp) },
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
                        text = "Your Contact Details",
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold,
                        color = Color(0xFF212121)
                    )
                    Spacer(modifier = Modifier.height(10.dp))

                    OutlinedTextField(
                        value = contactName,
                        onValueChange = { contactName = it },
                        label = { Text("Contact Person Name") },
                        isError = attemptedSubmit && !isContactNameValid,
                        supportingText = {
                            if (attemptedSubmit && !isContactNameValid) {
                                Text("Contact name cannot be empty", color = MaterialTheme.colorScheme.error)
                            }
                        },
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(10.dp)
                    )

                    Spacer(modifier = Modifier.height(8.dp))

                    OutlinedTextField(
                        value = phone,
                        onValueChange = { input ->
                            phone = input.filter { it.isDigit() }.take(10)
                        },
                        label = { Text("Phone Number (10 digits)") },
                        placeholder = { Text("e.g. 9876543210") },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                        isError = attemptedSubmit && !isPhoneValid,
                        supportingText = {
                            if (attemptedSubmit && !isPhoneValid) {
                                Text(
                                    "Must be exactly 10 digits starting with 6–9 (e.g. 9876543210)",
                                    color = MaterialTheme.colorScheme.error
                                )
                            }
                        },
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
                    attemptedSubmit = true
                    if (isContactNameValid && isPhoneValid && isPatientNameValid) {
                        val effectivePatient = if (forWhom == "someone_else") patientName.trim() else "Myself"
                        viewModel.confirmBooking(
                            caregiverId = caregiverId,
                            name = contactName.trim(),
                            phone = phone.trim(),
                            slot = selectedSlot,
                            patientName = effectivePatient,
                            relation = if (forWhom == "someone_else") selectedRelation else null
                        )
                    }
                }
            )
        }
    }
}
