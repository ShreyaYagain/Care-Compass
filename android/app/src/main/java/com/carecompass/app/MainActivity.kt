package com.carecompass.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import com.carecompass.app.ui.navigation.CareCompassNavGraph
import com.carecompass.app.ui.theme.CareCompassTheme
import com.carecompass.app.viewmodel.TriageViewModel

class MainActivity : ComponentActivity() {

    private val viewModel: TriageViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            CareCompassTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    CareCompassNavGraph(viewModel = viewModel)
                }
            }
        }
    }
}
