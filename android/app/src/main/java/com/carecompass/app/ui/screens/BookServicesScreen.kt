package com.carecompass.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Call
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.MedicalServices
import androidx.compose.material.icons.filled.Science
import androidx.compose.material.icons.filled.VideoCall
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.carecompass.app.R
import com.carecompass.app.ui.components.LanguageToggle
import com.carecompass.app.ui.theme.EmergencyRed
import com.carecompass.app.ui.theme.PrimaryBlue
import com.carecompass.app.ui.theme.SurfaceBackground
import com.carecompass.app.ui.theme.TextGray
import com.carecompass.app.viewmodel.BookingViewModel
import com.carecompass.app.viewmodel.CareService

@Composable
fun BookServicesScreen(
    selectedLanguage: String,
    onLanguageSelected: (String) -> Unit,
    onSelectService: (CareService) -> Unit,
    onEmergencyClick: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    val titleText = when (selectedLanguage) {
        "hi" -> stringResource(R.string.book_service_title_hi)
        "hinglish" -> stringResource(R.string.book_service_title_hinglish)
        else -> stringResource(R.string.book_service_title_en)
    }

    val subtitleText = when (selectedLanguage) {
        "hi" -> stringResource(R.string.book_service_subtitle_hi)
        "hinglish" -> stringResource(R.string.book_service_subtitle_hinglish)
        else -> stringResource(R.string.book_service_subtitle_en)
    }

    val emergencyLinkText = when (selectedLanguage) {
        "hi" -> stringResource(R.string.call_112_link_hi)
        "hinglish" -> stringResource(R.string.call_112_link_hinglish)
        else -> stringResource(R.string.call_112_link_en)
    }

    val disclaimerText = when (selectedLanguage) {
        "hi" -> stringResource(R.string.medical_disclaimer_hi)
        "hinglish" -> stringResource(R.string.medical_disclaimer_hinglish)
        else -> stringResource(R.string.medical_disclaimer_en)
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(SurfaceBackground)
            .padding(16.dp)
            .verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        // Top Bar: Back Arrow, Title, Language Toggle
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
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
                modifier = Modifier.weight(1f).padding(horizontal = 8.dp)
            )

            LanguageToggle(
                selectedLanguage = selectedLanguage,
                onLanguageSelected = onLanguageSelected
            )
        }

        Spacer(modifier = Modifier.height(6.dp))

        // Subtitle
        Text(
            text = subtitleText,
            fontSize = 16.sp,
            color = TextGray,
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 8.dp)
        )

        Spacer(modifier = Modifier.height(24.dp))

        // Card 0: Doctor home visit
        ServiceCard(
            title = stringResource(CareService.DOCTOR_HOME_VISIT.getTitle(selectedLanguage)),
            description = stringResource(CareService.DOCTOR_HOME_VISIT.getDesc(selectedLanguage)),
            icon = Icons.Default.Home,
            onClick = { onSelectService(CareService.DOCTOR_HOME_VISIT) }
        )

        Spacer(modifier = Modifier.height(16.dp))

        // Card 1: Home Nursing
        ServiceCard(
            title = stringResource(CareService.HOME_NURSING.getTitle(selectedLanguage)),
            description = stringResource(CareService.HOME_NURSING.getDesc(selectedLanguage)),
            icon = Icons.Default.MedicalServices,
            onClick = { onSelectService(CareService.HOME_NURSING) }
        )

        Spacer(modifier = Modifier.height(16.dp))

        // Card 2: Lab test at home
        ServiceCard(
            title = stringResource(CareService.LAB_TEST_HOME.getTitle(selectedLanguage)),
            description = stringResource(CareService.LAB_TEST_HOME.getDesc(selectedLanguage)),
            icon = Icons.Default.Science,
            onClick = { onSelectService(CareService.LAB_TEST_HOME) }
        )

        Spacer(modifier = Modifier.height(16.dp))

        // Card 3: Doctor teleconsultation
        ServiceCard(
            title = stringResource(CareService.TELECONSULTATION.getTitle(selectedLanguage)),
            description = stringResource(CareService.TELECONSULTATION.getDesc(selectedLanguage)),
            icon = Icons.Default.VideoCall,
            onClick = { onSelectService(CareService.TELECONSULTATION) }
        )

        Spacer(modifier = Modifier.height(28.dp))

        // Emergency Call 112 Button (full red with white text)
        Button(
            onClick = { onEmergencyClick() },
            modifier = Modifier
                .fillMaxWidth()
                .height(54.dp),
            shape = RoundedCornerShape(12.dp),
            colors = ButtonDefaults.buttonColors(containerColor = EmergencyRed, contentColor = Color.White)
        ) {
            Icon(
                imageVector = Icons.Default.Call,
                contentDescription = null,
                tint = Color.White
            )
            Spacer(modifier = Modifier.width(8.dp))
            Text(
                text = emergencyLinkText,
                fontSize = 16.sp,
                fontWeight = FontWeight.Bold,
                color = Color.White
            )
        }

        Spacer(modifier = Modifier.height(32.dp))

        // Footer disclaimer
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
private fun ServiceCard(
    title: String,
    description: String,
    icon: ImageVector,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier
            .fillMaxWidth()
            .heightIn(min = 96.dp)
            .clickable { onClick() },
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = PrimaryBlue),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(18.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = Color.White.copy(alpha = 0.18f),
                modifier = Modifier.size(54.dp)
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(
                        imageVector = icon,
                        contentDescription = title,
                        tint = Color.White,
                        modifier = Modifier.size(30.dp)
                    )
                }
            }

            Spacer(modifier = Modifier.width(16.dp))

            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = title,
                    fontSize = 19.sp,
                    fontWeight = FontWeight.Bold,
                    color = Color.White
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = description,
                    fontSize = 15.sp,
                    color = Color.White.copy(alpha = 0.9f),
                    lineHeight = 20.sp
                )
            }
        }
    }
}
