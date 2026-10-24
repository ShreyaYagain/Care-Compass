package com.carecompass.app.ui.screens

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshContainer
import androidx.compose.material3.pulltorefresh.rememberPullToRefreshState
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.carecompass.app.R
import com.carecompass.app.data.Booking
import com.carecompass.app.ui.components.CommonFooter
import com.carecompass.app.ui.components.LanguageToggle
import com.carecompass.app.ui.theme.AmberWarning
import com.carecompass.app.ui.theme.GreenSafe
import com.carecompass.app.ui.theme.PrimaryBlue
import com.carecompass.app.ui.theme.SurfaceBackground
import com.carecompass.app.ui.theme.TextDark
import com.carecompass.app.ui.theme.TextGray
import com.carecompass.app.util.DateTimeFormatterHelper
import com.carecompass.app.viewmodel.BookingsUiState
import com.carecompass.app.viewmodel.BookingsViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BookingsScreen(
    viewModel: BookingsViewModel,
    selectedLanguage: String,
    onLanguageSelected: (String) -> Unit,
    onBookServiceClick: () -> Unit,
    onRescheduleBooking: (Booking) -> Unit,
    modifier: Modifier = Modifier
) {
    val uiState by viewModel.uiState.collectAsState()
    val context = LocalContext.current

    // Refresh every time the Bookings tab is opened so new bookings appear.
    LaunchedEffect(Unit) {
        viewModel.loadBookings()
    }

    val titleText = when (selectedLanguage) {
        "hi" -> stringResource(R.string.bookings_title_hi)
        "hinglish" -> stringResource(R.string.bookings_title_hinglish)
        else -> stringResource(R.string.bookings_title_en)
    }

    val pullRefreshState = rememberPullToRefreshState()
    if (pullRefreshState.isRefreshing) {
        LaunchedEffect(true) {
            viewModel.loadBookings(isRefresh = true)
        }
    }

    LaunchedEffect(uiState.isRefreshing) {
        if (!uiState.isRefreshing) {
            pullRefreshState.endRefresh()
        }
    }

    // Cancel Booking Dialog
    if (uiState.showCancelConfirmDialog) {
        val dialogTitle = when (selectedLanguage) {
            "hi" -> stringResource(R.string.dialog_cancel_booking_title_hi)
            "hinglish" -> stringResource(R.string.dialog_cancel_booking_title_hinglish)
            else -> stringResource(R.string.dialog_cancel_booking_title_en)
        }
        val dialogMsg = when (selectedLanguage) {
            "hi" -> stringResource(R.string.dialog_cancel_booking_msg_hi)
            "hinglish" -> stringResource(R.string.dialog_cancel_booking_msg_hinglish)
            else -> stringResource(R.string.dialog_cancel_booking_msg_en)
        }
        val confirmText = when (selectedLanguage) {
            "hi" -> stringResource(R.string.btn_cancel_booking_hi)
            "hinglish" -> stringResource(R.string.btn_cancel_booking_hinglish)
            else -> stringResource(R.string.btn_cancel_booking_en)
        }
        val dismissText = when (selectedLanguage) {
            "hi" -> "पीछे हटें"
            "hinglish" -> "Keep booking"
            else -> "Keep booking"
        }

        AlertDialog(
            onDismissRequest = { viewModel.dismissCancelDialog() },
            icon = { Icon(Icons.Default.Cancel, contentDescription = null, tint = Color(0xFFD32F2F)) },
            title = { Text(dialogTitle, fontWeight = FontWeight.Bold, fontSize = 20.sp) },
            text = { Text(dialogMsg, fontSize = 16.sp) },
            confirmButton = {
                Button(
                    onClick = { viewModel.confirmCancel() },
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFD32F2F))
                ) {
                    Text(confirmText, fontSize = 16.sp, fontWeight = FontWeight.Bold)
                }
            },
            dismissButton = {
                OutlinedButton(onClick = { viewModel.dismissCancelDialog() }) {
                    Text(dismissText, fontSize = 16.sp)
                }
            }
        )
    }

    Box(
        modifier = modifier
            .fillMaxSize()
            .background(SurfaceBackground)
            .nestedScroll(pullRefreshState.nestedScrollConnection)
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 16.dp, vertical = 12.dp)
        ) {
            // Top Bar
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 12.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = titleText,
                    fontSize = 24.sp,
                    fontWeight = FontWeight.ExtraBold,
                    color = PrimaryBlue
                )
                LanguageToggle(
                    selectedLanguage = selectedLanguage,
                    onLanguageSelected = onLanguageSelected
                )
            }

            when {
                uiState.isLoading && uiState.upcomingBookings.isEmpty() && uiState.pastBookings.isEmpty() -> {
                    BookingsLoadingSkeleton()
                }

                uiState.errorMessage != null && uiState.upcomingBookings.isEmpty() && uiState.pastBookings.isEmpty() -> {
                    BookingsErrorView(
                        message = uiState.errorMessage ?: "",
                        selectedLanguage = selectedLanguage,
                        onRetry = { viewModel.loadBookings() }
                    )
                }

                uiState.upcomingBookings.isEmpty() && uiState.pastBookings.isEmpty() -> {
                    BookingsEmptyState(
                        selectedLanguage = selectedLanguage,
                        onBookServiceClick = onBookServiceClick
                    )
                }

                else -> {
                    LazyColumn(
                        modifier = Modifier.weight(1f),
                        verticalArrangement = Arrangement.spacedBy(16.dp),
                        contentPadding = PaddingValues(vertical = 8.dp)
                    ) {
                        if (uiState.upcomingBookings.isEmpty()) {
                            item {
                                BookingsEmptyState(
                                    selectedLanguage = selectedLanguage,
                                    onBookServiceClick = onBookServiceClick
                                )
                            }
                        } else {
                            items(uiState.upcomingBookings, key = { it.id }) { booking ->
                                BookingCard(
                                    booking = booking,
                                    isPast = false,
                                    selectedLanguage = selectedLanguage,
                                    onCallCaregiver = { phone ->
                                        val dialIntent = Intent(Intent.ACTION_DIAL, Uri.parse("tel:$phone"))
                                        context.startActivity(dialIntent)
                                    },
                                    onReschedule = { onRescheduleBooking(booking) },
                                    onCancel = { viewModel.promptCancel(booking) }
                                )
                            }
                        }

                        // Past Bookings Section (Collapsed by default)
                        if (uiState.pastBookings.isNotEmpty()) {
                            item {
                                val pastTitle = when (selectedLanguage) {
                                    "hi" -> stringResource(R.string.past_bookings_title_hi)
                                    "hinglish" -> stringResource(R.string.past_bookings_title_hinglish)
                                    else -> stringResource(R.string.past_bookings_title_en)
                                }

                                Surface(
                                    shape = RoundedCornerShape(12.dp),
                                    color = Color.White,
                                    border = BorderStroke(1.dp, Color(0xFFE2E8F0)),
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .clickable { viewModel.togglePastExpanded() }
                                ) {
                                    Row(
                                        modifier = Modifier
                                            .fillMaxWidth()
                                            .padding(horizontal = 16.dp, vertical = 14.dp),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Row(verticalAlignment = Alignment.CenterVertically) {
                                            Icon(
                                                imageVector = Icons.Default.History,
                                                contentDescription = null,
                                                tint = TextGray,
                                                modifier = Modifier.size(20.dp)
                                            )
                                            Spacer(modifier = Modifier.width(8.dp))
                                            Text(
                                                text = "$pastTitle (${uiState.pastBookings.size})",
                                                fontSize = 17.sp,
                                                fontWeight = FontWeight.Bold,
                                                color = TextDark
                                            )
                                        }

                                        Icon(
                                            imageVector = if (uiState.isPastExpanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore,
                                            contentDescription = if (uiState.isPastExpanded) "Collapse" else "Expand",
                                            tint = TextGray
                                        )
                                    }
                                }
                            }

                            if (uiState.isPastExpanded) {
                                items(uiState.pastBookings, key = { it.id }) { booking ->
                                    BookingCard(
                                        booking = booking,
                                        isPast = true,
                                        selectedLanguage = selectedLanguage,
                                        onCallCaregiver = {},
                                        onReschedule = {},
                                        onCancel = {}
                                    )
                                }
                            }
                        }

                        item {
                            CommonFooter(selectedLanguage = selectedLanguage)
                        }
                    }
                }
            }
        }

        PullToRefreshContainer(
            state = pullRefreshState,
            modifier = Modifier.align(Alignment.TopCenter),
            containerColor = Color.White,
            contentColor = PrimaryBlue
        )
    }
}

@Composable
fun BookingCard(
    booking: Booking,
    isPast: Boolean,
    selectedLanguage: String,
    onCallCaregiver: (String) -> Unit,
    onReschedule: () -> Unit,
    onCancel: () -> Unit,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val isTeleconsultation = booking.service.contains("tele", ignoreCase = true) ||
            booking.careType.contains("tele", ignoreCase = true)

    val serviceIcon: ImageVector = when {
        booking.service.contains("lab", ignoreCase = true) || booking.careType.contains("lab", ignoreCase = true) -> Icons.Default.Science
        isTeleconsultation -> Icons.Default.VideoCall
        else -> Icons.Default.MedicalServices
    }

    val (statusLabel, statusColor, statusBg) = when (booking.status.lowercase()) {
        "confirmed" -> Triple(
            when (selectedLanguage) {
                "hi" -> stringResource(R.string.status_confirmed_hi)
                "hinglish" -> stringResource(R.string.status_confirmed_hinglish)
                else -> stringResource(R.string.status_confirmed_en)
            },
            GreenSafe,
            Color(0xFFE8F5E9)
        )
        "pending" -> Triple(
            when (selectedLanguage) {
                "hi" -> stringResource(R.string.status_pending_hi)
                "hinglish" -> stringResource(R.string.status_pending_hinglish)
                else -> stringResource(R.string.status_pending_en)
            },
            AmberWarning,
            Color(0xFFFFF3E0)
        )
        "cancelled" -> Triple(
            "Cancelled",
            Color(0xFFB91C1C),
            Color(0xFFFFEBEE)
        )
        else -> Triple(
            "Completed",
            Color(0xFF4B5563),
            Color(0xFFF3F4F6)
        )
    }

    val dayBadge = DateTimeFormatterHelper.getDayBadge(booking.startTime, selectedLanguage)
    val formattedDateTime = DateTimeFormatterHelper.formatBookingDateRange(booking.startTime, booking.endTime)
    val isNearCallTime = isTeleconsultation && DateTimeFormatterHelper.isWithin15MinutesOfStart(booking.startTime, booking.endTime)

    val forWhomText = if (!booking.relation.isNullOrBlank()) {
        "For: ${booking.patientName} (${booking.relation})"
    } else if (booking.patientName.isNotBlank() && !booking.patientName.equals("Myself", ignoreCase = true)) {
        "For: ${booking.patientName}"
    } else {
        "For: Myself"
    }

    val cardAlpha = if (isPast) 0.85f else 1.0f
    val cardBg = if (isPast) Color(0xFFFAFAFA) else Color.White

    Card(
        modifier = modifier
            .fillMaxWidth()
            .alpha(cardAlpha)
            .clip(RoundedCornerShape(16.dp)),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = cardBg),
        elevation = CardDefaults.cardElevation(defaultElevation = if (isPast) 1.dp else 3.dp),
        border = BorderStroke(1.dp, if (isPast) Color(0xFFE2E8F0) else Color(0xFFCBD5E1))
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(18.dp)
        ) {
            // Service line with Icon and Status chip
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.weight(1f)
                ) {
                    Surface(
                        shape = RoundedCornerShape(8.dp),
                        color = PrimaryBlue.copy(alpha = 0.1f),
                        modifier = Modifier.size(36.dp)
                    ) {
                        Box(contentAlignment = Alignment.Center) {
                            Icon(
                                imageVector = serviceIcon,
                                contentDescription = null,
                                tint = PrimaryBlue,
                                modifier = Modifier.size(20.dp)
                            )
                        }
                    }
                    Spacer(modifier = Modifier.width(10.dp))
                    Text(
                        text = booking.service,
                        fontSize = 19.sp,
                        fontWeight = FontWeight.Bold,
                        color = TextDark
                    )
                }

                // Status chip
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = statusBg
                ) {
                    Text(
                        text = statusLabel,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Bold,
                        color = statusColor,
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp)
                    )
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // FOR WHOM line
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = Icons.Default.Person,
                    contentDescription = null,
                    tint = PrimaryBlue,
                    modifier = Modifier.size(18.dp)
                )
                Spacer(modifier = Modifier.width(6.dp))
                Text(
                    text = forWhomText,
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Bold,
                    color = PrimaryBlue
                )
            }

            Spacer(modifier = Modifier.height(10.dp))

            // Caregiver Info: Name, Role, Qualification
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(10.dp))
                    .background(Color(0xFFF8FAFC))
                    .padding(12.dp)
            ) {
                Text(
                    text = "${booking.caregiver.name} · ${booking.caregiver.role}",
                    fontSize = 16.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = TextDark
                )
                if (booking.caregiver.qualification.isNotBlank()) {
                    Spacer(modifier = Modifier.height(2.dp))
                    Text(
                        text = booking.caregiver.qualification,
                        fontSize = 14.sp,
                        color = TextGray
                    )
                }
            }

            Spacer(modifier = Modifier.height(14.dp))

            // Date & Time: Big and Bold, with Today/Tomorrow badge
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    imageVector = Icons.Default.Schedule,
                    contentDescription = null,
                    tint = TextDark,
                    modifier = Modifier.size(20.dp)
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = formattedDateTime,
                    fontSize = 18.sp,
                    fontWeight = FontWeight.ExtraBold,
                    color = TextDark,
                    modifier = Modifier.weight(1f)
                )

                if (dayBadge != null) {
                    Spacer(modifier = Modifier.width(6.dp))
                    Surface(
                        shape = RoundedCornerShape(6.dp),
                        color = PrimaryBlue
                    ) {
                        Text(
                            text = dayBadge,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                            color = Color.White,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 3.dp)
                        )
                    }
                }
            }

            // Address line (hidden for teleconsultation)
            if (!isTeleconsultation && !booking.address.isNullOrBlank()) {
                Spacer(modifier = Modifier.height(10.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.Top
                ) {
                    Icon(
                        imageVector = Icons.Default.Place,
                        contentDescription = null,
                        tint = TextGray,
                        modifier = Modifier.size(18.dp).padding(top = 2.dp)
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(
                        text = booking.address,
                        fontSize = 15.sp,
                        color = TextDark,
                        lineHeight = 20.sp
                    )
                }
            }

            // For teleconsultation: Join call button if within 15 mins of start
            if (isTeleconsultation && !isPast) {
                Spacer(modifier = Modifier.height(12.dp))
                if (isNearCallTime) {
                    val joinCallText = when (selectedLanguage) {
                        "hi" -> stringResource(R.string.btn_join_call_hi)
                        "hinglish" -> stringResource(R.string.btn_join_call_hinglish)
                        else -> stringResource(R.string.btn_join_call_en)
                    }
                    Button(
                        onClick = {
                            val callUri = Uri.parse("https://meet.google.com/new")
                            val callIntent = Intent(Intent.ACTION_VIEW, callUri)
                            context.startActivity(callIntent)
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = GreenSafe),
                        shape = RoundedCornerShape(12.dp),
                        modifier = Modifier.fillMaxWidth().height(56.dp)
                    ) {
                        Icon(Icons.Default.VideoCall, contentDescription = null, tint = Color.White)
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(joinCallText, fontSize = 18.sp, fontWeight = FontWeight.Bold, color = Color.White)
                    }
                } else {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(Icons.Default.VideoCall, contentDescription = null, tint = TextGray, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(6.dp))
                        Text(
                            text = "Video call link opens 15 mins before start time",
                            fontSize = 14.sp,
                            color = TextGray
                        )
                    }
                }
            }

            // Action Buttons (Only for Upcoming bookings)
            if (!isPast) {
                Spacer(modifier = Modifier.height(16.dp))
                HorizontalDivider(color = Color(0xFFE2E8F0))
                Spacer(modifier = Modifier.height(14.dp))

                val callCaregiverText = when (selectedLanguage) {
                    "hi" -> stringResource(R.string.btn_call_caregiver_hi)
                    "hinglish" -> stringResource(R.string.btn_call_caregiver_hinglish)
                    else -> stringResource(R.string.btn_call_caregiver_en)
                }
                val rescheduleText = when (selectedLanguage) {
                    "hi" -> stringResource(R.string.btn_reschedule_hi)
                    "hinglish" -> stringResource(R.string.btn_reschedule_hinglish)
                    else -> stringResource(R.string.btn_reschedule_en)
                }
                val cancelText = when (selectedLanguage) {
                    "hi" -> stringResource(R.string.btn_cancel_booking_hi)
                    "hinglish" -> stringResource(R.string.btn_cancel_booking_hinglish)
                    else -> stringResource(R.string.btn_cancel_booking_en)
                }

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    // Call Caregiver
                    Button(
                        onClick = { onCallCaregiver(booking.caregiver.phone) },
                        modifier = Modifier.weight(1f).height(56.dp),
                        shape = RoundedCornerShape(10.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = PrimaryBlue),
                        contentPadding = PaddingValues(horizontal = 6.dp)
                    ) {
                        Icon(Icons.Default.Call, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(4.dp))
                        Text(callCaregiverText, fontSize = 14.sp, fontWeight = FontWeight.Bold, maxLines = 1)
                    }

                    // Reschedule
                    OutlinedButton(
                        onClick = onReschedule,
                        modifier = Modifier.weight(1f).height(56.dp),
                        shape = RoundedCornerShape(10.dp),
                        border = BorderStroke(1.5.dp, PrimaryBlue),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = PrimaryBlue),
                        contentPadding = PaddingValues(horizontal = 6.dp)
                    ) {
                        Icon(Icons.Default.EditCalendar, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(4.dp))
                        Text(rescheduleText, fontSize = 14.sp, fontWeight = FontWeight.Bold, maxLines = 1)
                    }

                    // Cancel
                    OutlinedButton(
                        onClick = onCancel,
                        modifier = Modifier.weight(0.9f).height(56.dp),
                        shape = RoundedCornerShape(10.dp),
                        border = BorderStroke(1.5.dp, Color(0xFFEF4444)),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = Color(0xFFDC2626)),
                        contentPadding = PaddingValues(horizontal = 6.dp)
                    ) {
                        Icon(Icons.Default.Close, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(4.dp))
                        Text(cancelText, fontSize = 14.sp, fontWeight = FontWeight.Bold, maxLines = 1)
                    }
                }
            }
        }
    }
}

@Composable
private fun BookingsLoadingSkeleton() {
    Column(
        modifier = Modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        repeat(3) {
            Card(
                modifier = Modifier.fillMaxWidth().height(160.dp),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = Color.White),
                border = BorderStroke(1.dp, Color(0xFFE2E8F0))
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    Box(modifier = Modifier.fillMaxWidth(0.6f).height(24.dp).clip(RoundedCornerShape(6.dp)).background(Color(0xFFE2E8F0)))
                    Spacer(modifier = Modifier.height(14.dp))
                    Box(modifier = Modifier.fillMaxWidth(0.4f).height(18.dp).clip(RoundedCornerShape(6.dp)).background(Color(0xFFF1F5F9)))
                    Spacer(modifier = Modifier.height(14.dp))
                    Box(modifier = Modifier.fillMaxWidth(0.8f).height(22.dp).clip(RoundedCornerShape(6.dp)).background(Color(0xFFE2E8F0)))
                }
            }
        }
    }
}

@Composable
private fun BookingsErrorView(
    message: String,
    selectedLanguage: String,
    onRetry: () -> Unit
) {
    val retryText = when (selectedLanguage) {
        "hi" -> stringResource(R.string.btn_retry_hi)
        "hinglish" -> stringResource(R.string.btn_retry_hinglish)
        else -> stringResource(R.string.btn_retry_en)
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text(
            text = message,
            fontSize = 18.sp,
            color = Color(0xFF374151),
            textAlign = TextAlign.Center,
            lineHeight = 24.sp
        )
        Spacer(modifier = Modifier.height(20.dp))
        Button(
            onClick = onRetry,
            colors = ButtonDefaults.buttonColors(containerColor = PrimaryBlue),
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier.height(56.dp)
        ) {
            Icon(Icons.Default.Refresh, contentDescription = retryText)
            Spacer(modifier = Modifier.width(8.dp))
            Text(retryText, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun BookingsEmptyState(
    selectedLanguage: String,
    onBookServiceClick: () -> Unit
) {
    val emptyText = when (selectedLanguage) {
        "hi" -> stringResource(R.string.bookings_empty_title_hi)
        "hinglish" -> stringResource(R.string.bookings_empty_title_hinglish)
        else -> stringResource(R.string.bookings_empty_title_en)
    }

    val bookBtnText = when (selectedLanguage) {
        "hi" -> stringResource(R.string.btn_book_service_hi)
        "hinglish" -> stringResource(R.string.btn_book_service_hinglish)
        else -> stringResource(R.string.btn_book_service_en)
    }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 36.dp, horizontal = 20.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Surface(
            shape = RoundedCornerShape(24.dp),
            color = PrimaryBlue.copy(alpha = 0.08f),
            modifier = Modifier.size(110.dp)
        ) {
            Box(contentAlignment = Alignment.Center) {
                Icon(
                    imageVector = Icons.Default.CalendarMonth,
                    contentDescription = null,
                    tint = PrimaryBlue,
                    modifier = Modifier.size(60.dp)
                )
            }
        }

        Spacer(modifier = Modifier.height(20.dp))

        Text(
            text = emptyText,
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold,
            color = TextDark,
            textAlign = TextAlign.Center
        )

        Spacer(modifier = Modifier.height(24.dp))

        Button(
            onClick = onBookServiceClick,
            colors = ButtonDefaults.buttonColors(containerColor = PrimaryBlue),
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier.height(56.dp)
        ) {
            Icon(Icons.Default.MedicalServices, contentDescription = bookBtnText)
            Spacer(modifier = Modifier.width(8.dp))
            Text(bookBtnText, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        }
    }
}
