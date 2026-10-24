package com.carecompass.app.ui.components

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.carecompass.app.R

@Composable
fun CommonFooter(
    selectedLanguage: String,
    modifier: Modifier = Modifier
) {
    val disclaimerText = when (selectedLanguage) {
        "hi" -> stringResource(R.string.medical_disclaimer_hi)
        "hinglish" -> stringResource(R.string.medical_disclaimer_hinglish)
        else -> stringResource(R.string.medical_disclaimer_en)
    }

    Text(
        text = disclaimerText,
        fontSize = 14.sp,
        fontWeight = FontWeight.Normal,
        color = Color(0xFF757575),
        textAlign = TextAlign.Center,
        lineHeight = 20.sp,
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 20.dp)
    )
}
