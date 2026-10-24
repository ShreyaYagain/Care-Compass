package com.carecompass.app.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.carecompass.app.data.ModuleField
import com.carecompass.app.ui.components.BigButton
import com.carecompass.app.ui.theme.PrimaryBlue
import com.carecompass.app.viewmodel.TriageUiState
import com.carecompass.app.viewmodel.TriageViewModel

@Composable
fun ModuleCardScreen(
    viewModel: TriageViewModel,
    uiState: TriageUiState,
    modifier: Modifier = Modifier
) {
    val card = uiState.moduleCard
    val answers = remember(card) { mutableStateMapOf<String, String>() }
    val optionalText = remember(card) { mutableStateMapOf<String, String>() }

    Column(
        modifier = modifier
            .fillMaxSize()
            .background(Color(0xFFF8F9FA))
            .padding(16.dp)
            .verticalScroll(rememberScrollState())
    ) {
        Text(
            text = card?.label ?: "Follow-up",
            fontSize = 22.sp,
            fontWeight = FontWeight.Bold,
            color = Color(0xFF212121)
        )

        Text(
            text = "Please answer the quick questions below to help find the right care.",
            fontSize = 14.sp,
            color = Color(0xFF757575),
            modifier = Modifier.padding(top = 4.dp, bottom = 16.dp)
        )

        card?.fields?.forEach { field ->
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 6.dp),
                shape = RoundedCornerShape(12.dp),
                colors = CardDefaults.cardColors(containerColor = Color.White),
                elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
            ) {
                Box(modifier = Modifier.padding(16.dp)) {
                    when {
                        field.type == "slider010" -> SliderField(field, answers)
                        field.type == "choice_opt" -> ChoiceField(field, answers, optionalText, allowOther = true)
                        else -> ChoiceField(field, answers, optionalText, allowOther = false)
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(16.dp))

        // Required fields must be answered; informational fields (e.g. meds) are optional
        val requiredFilled = card != null && card.fields.all { it.informational || answers.containsKey(it.id) }

        BigButton(
            text = "Continue",
            enabled = !uiState.isLoading && requiredFilled,
            onClick = {
                card?.let {
                    val merged = mutableMapOf<String, String>()
                    merged.putAll(answers)
                    optionalText.forEach { (k, v) ->
                        if (v.isNotBlank()) merged[k] = v
                    }
                    viewModel.submitModuleAnswers(it.moduleId, merged)
                }
            }
        )

        if (uiState.isLoading) {
            Spacer(modifier = Modifier.height(12.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.Center
            ) {
                CircularProgressIndicator(color = PrimaryBlue)
            }
        }
    }
}

@Composable
private fun SliderField(field: ModuleField, answers: MutableMap<String, String>) {
    var value by remember(field) {
        val initial = answers[field.id]?.toFloatOrNull() ?: 5f
        answers[field.id] = initial.toInt().toString()
        mutableStateOf(initial)
    }
    Column(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = field.question,
                fontSize = 16.sp,
                fontWeight = FontWeight.SemiBold,
                color = Color(0xFF212121),
                modifier = Modifier.weight(1f)
            )
            if (field.informational) {
                Text(
                    text = "Optional",
                    fontSize = 12.sp,
                    color = Color(0xFF757575)
                )
            }
        }
        Spacer(modifier = Modifier.height(12.dp))
        Slider(
            value = value,
            onValueChange = {
                value = it
                answers[field.id] = it.toInt().toString()
            },
            valueRange = 0f..10f,
            steps = 9
        )
        val band = when (value.toInt()) {
            in 0..3 -> field.bands?.get("low") ?: "Mild (1-3)"
            in 4..6 -> field.bands?.get("mid") ?: "Moderate (4-6)"
            else -> field.bands?.get("high") ?: "Severe (7-10)"
        }
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text("0", fontSize = 12.sp, color = Color.Gray)
            Text("${value.toInt()}/10 · $band", fontSize = 14.sp, fontWeight = FontWeight.Bold, color = PrimaryBlue)
            Text("10", fontSize = 12.sp, color = Color.Gray)
        }
    }
}

@Composable
private fun ChoiceField(
    field: ModuleField,
    answers: MutableMap<String, String>,
    optionalText: MutableMap<String, String>,
    allowOther: Boolean
) {
    val selected = answers[field.id]
    Column(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = field.question,
                fontSize = 16.sp,
                fontWeight = FontWeight.SemiBold,
                color = Color(0xFF212121),
                modifier = Modifier.weight(1f)
            )
            if (field.informational) {
                Text(
                    text = "Doctor info only",
                    fontSize = 12.sp,
                    color = Color(0xFF757575)
                )
            }
        }
        Spacer(modifier = Modifier.height(10.dp))
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            field.options.forEach { opt ->
                val isSel = selected == opt
                FilterChip(
                    selected = isSel,
                    onClick = {
                        if (isSel && field.informational) {
                            answers.remove(field.id)
                        } else {
                            answers[field.id] = opt
                        }
                    },
                    label = { Text(opt, fontSize = 15.sp) },
                    leadingIcon = if (isSel) {
                        { Icon(Icons.Default.Check, contentDescription = null, modifier = Modifier.size(16.dp)) }
                    } else null,
                    colors = FilterChipDefaults.filterChipColors(
                        selectedContainerColor = PrimaryBlue,
                        selectedLabelColor = Color.White
                    )
                )
            }
        }
        if (allowOther && selected == "Other") {
            Spacer(modifier = Modifier.height(8.dp))
            OutlinedTextField(
                value = optionalText[field.id] ?: "",
                onValueChange = { optionalText[field.id] = it },
                placeholder = { Text("Specify medicine/spray/balm") },
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(10.dp)
            )
        }
    }
}
