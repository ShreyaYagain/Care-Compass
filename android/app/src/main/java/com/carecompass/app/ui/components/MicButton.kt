package com.carecompass.app.ui.components

import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.carecompass.app.ui.theme.EmergencyRed
import com.carecompass.app.ui.theme.PrimaryBlue
import com.carecompass.app.util.MicState

@Composable
fun MicButton(
    state: MicState,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    elapsedSeconds: Int = 0,
    level: Float = 0f
) {
    val infiniteTransition = rememberInfiniteTransition(label = "pulse")
    val pulseScale by infiniteTransition.animateFloat(
        initialValue = 1f,
        targetValue = if (state == MicState.LISTENING) 1.25f else 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(800, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "scale"
    )
    val pulseAlpha by infiniteTransition.animateFloat(
        initialValue = 0.5f,
        targetValue = if (state == MicState.LISTENING) 0.1f else 0f,
        animationSpec = infiniteRepeatable(
            animation = tween(800, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse
        ),
        label = "alpha"
    )

    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Box(
            contentAlignment = Alignment.Center,
            modifier = Modifier.size(104.dp)
        ) {
            if (state == MicState.LISTENING) {
                Box(
                    modifier = Modifier
                        .size(96.dp)
                        .scale(pulseScale)
                        .clip(CircleShape)
                        .background(EmergencyRed.copy(alpha = pulseAlpha))
                )
            }

            val bgColor = when (state) {
                MicState.LISTENING -> EmergencyRed
                MicState.PROCESSING -> Color(0xFFFB8C00) // Amber / Orange
                MicState.IDLE -> PrimaryBlue
            }

            Box(
                modifier = Modifier
                    .size(80.dp)
                    .shadow(8.dp, CircleShape)
                    .clip(CircleShape)
                    .background(bgColor)
                    .clickable(onClick = onClick),
                contentAlignment = Alignment.Center
            ) {
                when (state) {
                    MicState.PROCESSING -> {
                        CircularProgressIndicator(
                            color = Color.White,
                            strokeWidth = 3.dp,
                            modifier = Modifier.size(36.dp)
                        )
                    }
                    MicState.LISTENING -> {
                        Icon(
                            imageVector = Icons.Default.Stop,
                            contentDescription = "Stop Listening",
                            tint = Color.White,
                            modifier = Modifier.size(40.dp)
                        )
                    }
                    MicState.IDLE -> {
                        Icon(
                            imageVector = Icons.Default.Mic,
                            contentDescription = "Microphone",
                            tint = Color.White,
                            modifier = Modifier.size(42.dp)
                        )
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(6.dp))

        val labelText = when (state) {
            MicState.LISTENING -> "Listening… tap to stop"
            MicState.PROCESSING -> "Processing voice…"
            MicState.IDLE -> "Tap & Speak"
        }
        val labelColor = when (state) {
            MicState.LISTENING -> EmergencyRed
            MicState.PROCESSING -> Color(0xFFFB8C00)
            MicState.IDLE -> PrimaryBlue
        }

        Text(
            text = labelText,
            fontSize = 18.sp,
            fontWeight = FontWeight.Bold,
            color = labelColor
        )

        if (state == MicState.LISTENING) {
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = formatElapsed(elapsedSeconds),
                fontSize = 15.sp,
                fontWeight = FontWeight.SemiBold,
                color = Color(0xFF616161)
            )
            Spacer(modifier = Modifier.height(6.dp))
            LevelIndicator(level = level, modifier = Modifier.width(120.dp))
        }
    }
}

private fun formatElapsed(seconds: Int): String {
    val s = seconds.coerceAtLeast(0)
    return "%d:%02d".format(s / 60, s % 60)
}

/** A simple 9-bar level meter; rms dB is roughly -2..10, normalised to 0..1. */
@Composable
private fun LevelIndicator(level: Float, modifier: Modifier = Modifier) {
    val normalized = (((level + 2f) / 12f)).coerceIn(0f, 1f)
    Row(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(3.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        val bars = 9
        for (i in 0 until bars) {
            val threshold = (i + 1).toFloat() / bars
            val active = normalized >= threshold
            Box(
                modifier = Modifier
                    .weight(1f)
                    .height(if (active) 14.dp else 6.dp)
                    .clip(RoundedCornerShape(2.dp))
                    .background(if (active) EmergencyRed else Color(0xFFE0E0E0))
            )
        }
    }
}
