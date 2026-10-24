package com.carecompass.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.carecompass.app.ui.theme.PrimaryBlue

@Composable
fun LanguageToggle(
    selectedLanguage: String,
    onLanguageSelected: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    val languages = listOf("en" to "English", "hi" to "हिंदी", "hinglish" to "Hinglish")

    Row(
        modifier = modifier
            .clip(RoundedCornerShape(20.dp))
            .background(Color(0xFFE5E7EB))
            .padding(3.dp)
    ) {
        languages.forEach { (code, label) ->
            val isSelected = selectedLanguage == code
            val bg = if (isSelected) PrimaryBlue else Color.Transparent
            val textCol = if (isSelected) Color.White else Color(0xFF374151)

            Text(
                text = label,
                fontSize = 14.sp,
                fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium,
                color = textCol,
                maxLines = 1,
                softWrap = false,
                modifier = Modifier
                    .clip(RoundedCornerShape(16.dp))
                    .background(bg)
                    .clickable { onLanguageSelected(code) }
                    .padding(horizontal = 10.dp, vertical = 6.dp)
            )
        }
    }
}
