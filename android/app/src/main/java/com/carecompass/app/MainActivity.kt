package com.carecompass.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.remember
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
