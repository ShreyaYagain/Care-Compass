package com.carecompass.app.ui.screens

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChatBubbleOutline
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.MedicalServices
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshContainer
import androidx.compose.material3.pulltorefresh.rememberPullToRefreshState
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.carecompass.app.R
import com.carecompass.app.data.HistorySummary
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
import com.carecompass.app.util.DateTimeFormatterHelper
import com.carecompass.app.viewmodel.HistoryUiState
import com.carecompass.app.viewmodel.HistoryViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HistoryScreen(
    viewModel: HistoryViewModel,
    selectedLanguage: String,
    onLanguageSelected: (String) -> Unit,
    onSelectHistoryItem: (String) -> Unit,
    onNavigateHome: () -> Unit,
    modifier: Modifier = Modifier
) {
    val uiState by viewModel.uiState.collectAsState()

    val titleText = when (selectedLanguage) {
        "hi" -> stringResource(R.string.history_title_hi)
        "hinglish" -> stringResource(R.string.history_title_hinglish)
        else -> stringResource(R.string.history_title_en)
    }

    val pullRefreshState = rememberPullToRefreshState()
    if (pullRefreshState.isRefreshing) {
        LaunchedEffect(true) {
            viewModel.loadHistory(isRefresh = true)
        }
    }

    LaunchedEffect(uiState.isRefreshing) {
        if (!uiState.isRefreshing) {
            pullRefreshState.endRefresh()
        }
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
                uiState.isLoading && uiState.historyItems.isEmpty() -> {
                    // Loading Skeletons
                    HistoryLoadingSkeleton()
                }

                uiState.errorMessage != null && uiState.historyItems.isEmpty() -> {
                    // Friendly Error with Retry
                    HistoryErrorView(
                        message = uiState.errorMessage ?: "",
                        selectedLanguage = selectedLanguage,
                        onRetry = { viewModel.loadHistory() }
                    )
                }

                uiState.historyItems.isEmpty() -> {
                    // Empty State
                    HistoryEmptyState(
                        selectedLanguage = selectedLanguage,
                        onNavigateHome = onNavigateHome
                    )
                }

                else -> {
                    // List of 5 Recent Sessions
                    LazyColumn(
                        modifier = Modifier.weight(1f),
                        verticalArrangement = Arrangement.spacedBy(14.dp),
                        contentPadding = PaddingValues(vertical = 8.dp)
                    ) {
                        items(uiState.historyItems, key = { it.id }) { item ->
                            HistoryCard(
                                item = item,
                                selectedLanguage = selectedLanguage,
                                onClick = { onSelectHistoryItem(item.id) }
                            )
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
fun HistoryCard(
    item: HistorySummary,
    selectedLanguage: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    val (chipText, chipTextColor, chipBgColor) = when (item.outcome.lowercase()) {
        "emergency" -> Triple(
            when (selectedLanguage) {
                "hi" -> stringResource(R.string.outcome_emergency_hi)
                "hinglish" -> stringResource(R.string.outcome_emergency_hinglish)
                else -> stringResource(R.string.outcome_emergency_en)
            },
            Color(0xFFD32F2F),
            Color(0xFFFFEBEE)
        )
        "same_day", "sameday" -> Triple(
            when (selectedLanguage) {
                "hi" -> stringResource(R.string.outcome_sameday_hi)
                "hinglish" -> stringResource(R.string.outcome_sameday_hinglish)
                else -> stringResource(R.string.outcome_sameday_en)
            },
            Color(0xFFE65100),
            Color(0xFFFFF3E0)
        )
        "scheduled" -> Triple(
            when (selectedLanguage) {
                "hi" -> stringResource(R.string.outcome_scheduled_hi)
                "hinglish" -> stringResource(R.string.outcome_scheduled_hinglish)
                else -> stringResource(R.string.outcome_scheduled_en)
            },
            PrimaryBlue,
            Color(0xFFE8F0FE)
        )
        else -> Triple(
            when (selectedLanguage) {
                "hi" -> stringResource(R.string.outcome_needs_info_hi)
                "hinglish" -> stringResource(R.string.outcome_needs_info_hinglish)
                else -> stringResource(R.string.outcome_needs_info_en)
            },
            Color(0xFF616161),
            Color(0xFFF1F5F9)
        )
    }

    val plainCareType = when (item.careType.lowercase()) {
        "home_nursing" -> "Home nursing"
        "paramedic_home_visit" -> "Medic home visit"
        "lab_test_home" -> "Lab test at home"
        "teleconsultation" -> "Doctor teleconsultation"
        "emergency_112" -> "Emergency (112)"
        else -> item.careType.replace("_", " ").replaceFirstChar { it.uppercase() }
    }

    val formattedTime = DateTimeFormatterHelper.formatHistoryTime(item.createdAt, selectedLanguage)

    Card(
        modifier = modifier
            .fillMaxWidth()
            .clickable { onClick() },
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        border = BorderStroke(1.dp, Color(0xFFE2E8F0))
    ) {
        Column(
            modifier = Modifier.padding(18.dp)
        ) {
            // First line: User's first message (max 2 lines, min 18sp)
            Text(
                text = item.firstMessage,
                fontSize = 18.sp,
                fontWeight = FontWeight.SemiBold,
                color = TextDark,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis,
                lineHeight = 24.sp
            )

            Spacer(modifier = Modifier.height(14.dp))

            // Row with outcome chip, care type, and date/time
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.weight(1f, fill = false)
                ) {
                    // Coloured outcome chip
                    Surface(
                        shape = RoundedCornerShape(8.dp),
                        color = chipBgColor
                    ) {
                        Text(
                            text = chipText,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Bold,
                            color = chipTextColor,
                            modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp)
                        )
                    }

                    // Care type in plain words
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            imageVector = Icons.Default.MedicalServices,
                            contentDescription = null,
                            tint = PrimaryBlue,
                            modifier = Modifier.size(16.dp)
                        )
                        Spacer(modifier = Modifier.width(4.dp))
                        Text(
                            text = plainCareType,
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Medium,
                            color = TextDark,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                }

                Spacer(modifier = Modifier.width(8.dp))

                // Date & Time
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(
                        imageVector = Icons.Default.Schedule,
                        contentDescription = null,
                        tint = TextGray,
                        modifier = Modifier.size(15.dp)
                    )
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(
                        text = formattedTime,
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Medium,
                        color = TextGray
                    )
                }
            }
        }
    }
}

@Composable
private fun HistoryLoadingSkeleton() {
    Column(
        modifier = Modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        repeat(4) {
            Card(
                modifier = Modifier.fillMaxWidth().height(110.dp),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = Color.White),
                border = BorderStroke(1.dp, Color(0xFFE2E8F0))
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth(0.85f)
                            .height(20.dp)
                            .clip(RoundedCornerShape(6.dp))
                            .background(Color(0xFFE2E8F0))
                    )
                    Spacer(modifier = Modifier.height(10.dp))
                    Box(
                        modifier = Modifier
                            .fillMaxWidth(0.5f)
                            .height(16.dp)
                            .clip(RoundedCornerShape(6.dp))
                            .background(Color(0xFFF1F5F9))
                    )
                    Spacer(modifier = Modifier.height(14.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Box(
                            modifier = Modifier
                                .width(80.dp)
                                .height(22.dp)
                                .clip(RoundedCornerShape(6.dp))
                                .background(Color(0xFFE2E8F0))
                        )
                        Box(
                            modifier = Modifier
                                .width(100.dp)
                                .height(22.dp)
                                .clip(RoundedCornerShape(6.dp))
                                .background(Color(0xFFF1F5F9))
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun HistoryErrorView(
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
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
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
private fun HistoryEmptyState(
    selectedLanguage: String,
    onNavigateHome: () -> Unit
) {
    val emptyText = when (selectedLanguage) {
        "hi" -> stringResource(R.string.history_empty_title_hi)
        "hinglish" -> stringResource(R.string.history_empty_title_hinglish)
        else -> stringResource(R.string.history_empty_title_en)
    }

    val homeBtnText = when (selectedLanguage) {
        "hi" -> stringResource(R.string.btn_start_home_hi)
        "hinglish" -> stringResource(R.string.btn_start_home_hinglish)
        else -> stringResource(R.string.btn_start_home_en)
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
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
                    imageVector = Icons.Default.ChatBubbleOutline,
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
            textAlign = TextAlign.Center,
            lineHeight = 28.sp
        )

        Spacer(modifier = Modifier.height(24.dp))

        Button(
            onClick = onNavigateHome,
            colors = ButtonDefaults.buttonColors(containerColor = PrimaryBlue),
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier.height(56.dp)
        ) {
            Icon(Icons.Default.Home, contentDescription = homeBtnText)
            Spacer(modifier = Modifier.width(8.dp))
            Text(homeBtnText, fontSize = 18.sp, fontWeight = FontWeight.Bold)
        }
    }
}
