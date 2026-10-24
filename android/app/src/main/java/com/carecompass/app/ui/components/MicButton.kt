package com.carecompass.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material3.Icon
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.carecompass.app.ui.theme.PrimaryBlue

@Composable
fun MicButton(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    isListening: Boolean = false
) {
    val bgColor = if (isListening) Color(0xFFE53935) else PrimaryBlue

    Box(
        modifier = modifier
            .size(88.dp)
            .shadow(8.dp, CircleShape)
            .clip(CircleShape)
            .background(bgColor)
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center
    ) {
        Icon(
            imageVector = Icons.Default.Mic,
            contentDescription = "Microphone",
            tint = Color.White,
            modifier = Modifier.size(44.dp)
        )
    }
}
