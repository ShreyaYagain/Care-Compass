package com.carecompass.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.carecompass.app.data.ApiService
import com.carecompass.app.data.Repository
import com.carecompass.app.data.auth.SupabaseAuthManager
import com.carecompass.app.data.cache.HistoryCache
import com.carecompass.app.ui.navigation.CareCompassNavGraph
import com.carecompass.app.ui.theme.CareCompassTheme
import com.carecompass.app.viewmodel.BookingViewModel
import com.carecompass.app.viewmodel.BookingsViewModel
import com.carecompass.app.viewmodel.HistoryViewModel
import com.carecompass.app.viewmodel.TriageViewModel
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Ensure Supabase anonymous authentication on first launch
        val authManager = SupabaseAuthManager.getInstance(applicationContext)
        CoroutineScope(Dispatchers.IO).launch {
            authManager.ensureSession()
        }

        setContent {
            val historyCache = remember { HistoryCache(applicationContext) }
            val apiService = remember { ApiService.create(applicationContext) }
            val repository = remember { Repository(apiService, historyCache) }

            val triageViewModel = remember { TriageViewModel(repository) }
            val bookingViewModel = remember { BookingViewModel(repository) }
            val historyViewModel = remember { HistoryViewModel(repository) }
            val bookingsViewModel = remember { BookingsViewModel(repository) }

            CareCompassTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    val prefs = remember { applicationContext.getSharedPreferences("care_compass_prefs", android.content.Context.MODE_PRIVATE) }
                    var showFirstRun by remember {
                        mutableStateOf(!prefs.getBoolean("first_run_seen", false))
                    }
                    if (showFirstRun) {
                        AlertDialog(
                            onDismissRequest = {
                                showFirstRun = false
                                prefs.edit().putBoolean("first_run_seen", true).apply()
                            },
                            icon = {
                                Icon(
                                    Icons.Default.Info,
                                    contentDescription = null,
                                    tint = MaterialTheme.colorScheme.primary
                                )
                            },
                            title = { Text("Welcome to CareCompass") },
                            text = {
                                Text(
                                    applicationContext.getString(R.string.app_disclaimer_en) +
                                        "\n\n" + applicationContext.getString(R.string.app_disclaimer_hinglish)
                                )
                            },
                            confirmButton = {
                                TextButton(onClick = {
                                    showFirstRun = false
                                    prefs.edit().putBoolean("first_run_seen", true).apply()
                                }) { Text("Got it") }
                            }
                        )
                    }
                    CareCompassNavGraph(
                        triageViewModel = triageViewModel,
                        bookingViewModel = bookingViewModel,
                        historyViewModel = historyViewModel,
                        bookingsViewModel = bookingsViewModel
                    )
                }
            }
        }
    }
}
