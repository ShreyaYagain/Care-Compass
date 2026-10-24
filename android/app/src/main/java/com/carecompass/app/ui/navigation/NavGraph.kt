package com.carecompass.app.ui.navigation

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavType
import androidx.navigation.compose.*
import androidx.navigation.navArgument
import androidx.navigation.navigation
import com.carecompass.app.data.MatchedCaregiver
import com.carecompass.app.ui.components.CareCompassBottomBar
import com.carecompass.app.ui.components.NavigationTab
import com.carecompass.app.ui.screens.*
import com.carecompass.app.viewmodel.*

@Composable
fun CareCompassNavGraph(
    triageViewModel: TriageViewModel,
    bookingViewModel: BookingViewModel,
    historyViewModel: HistoryViewModel,
    bookingsViewModel: BookingsViewModel,
    modifier: Modifier = Modifier
) {
    val navController = rememberNavController()
    val triageUiState by triageViewModel.uiState.collectAsState()
    val selectedLanguage = triageUiState.selectedLanguage

    val navBackStackEntry by navController.currentBackStackEntryAsState()
    val currentRoute = navBackStackEntry?.destination?.route

    // Determine current selected tab
    val currentTab = when {
        currentRoute?.startsWith("history") == true -> NavigationTab.HISTORY
        currentRoute?.startsWith("bookings") == true -> NavigationTab.BOOKINGS
        else -> NavigationTab.HOME
    }

    // Requirement: Show bar on Home, History, History detail, and Bookings ONLY.
    // HIDE it on Emergency screen, follow-up chat, and 3-step booking flow.
    val isBottomBarVisible = when {
        currentRoute == "home" -> true
        currentRoute == "history" -> true
        currentRoute?.startsWith("history_detail") == true -> true
        currentRoute == "bookings" -> true
        else -> false
    }

    // Keep destination in sync when TriageViewModel triggers navigation
    LaunchedEffect(triageUiState.destination) {
        when (val dest = triageUiState.destination) {
            is ScreenDestination.Emergency -> {
                if (currentRoute != "emergency") {
                    navController.navigate("emergency")
                }
            }
            is ScreenDestination.Chat -> {
                if (currentRoute != "chat") {
                    navController.navigate("chat")
                }
            }
            is ScreenDestination.Result -> {
                if (currentRoute != "result") {
                    navController.navigate("result")
                }
            }
            is ScreenDestination.Booking -> {
                navController.navigate("booking/${dest.caregiverId}")
            }
            is ScreenDestination.BookingFlow -> {
                if (currentRoute != "booking_flow") {
                    navController.navigate("booking_flow")
                }
            }
            is ScreenDestination.BookServices -> {
                if (currentRoute != "book_services") {
                    navController.navigate("book_services")
                }
            }
            is ScreenDestination.Home -> {
                // If on sub-screens of home, return to home
                if (currentRoute in listOf("chat", "emergency", "result", "booking/{caregiverId}", "booking_flow")) {
                    navController.navigate("home") {
                        popUpTo("home") { inclusive = false }
                    }
                }
            }
            else -> {}
        }
    }

    Scaffold(
        modifier = modifier.fillMaxSize(),
        bottomBar = {
            if (isBottomBarVisible) {
                CareCompassBottomBar(
                    selectedTab = currentTab,
                    onTabSelected = { tab ->
                        val targetGraph = when (tab) {
                            NavigationTab.HOME -> "home_graph"
                            NavigationTab.HISTORY -> "history_graph"
                            NavigationTab.BOOKINGS -> "bookings_graph"
                        }
                        navController.navigate(targetGraph) {
                            popUpTo(navController.graph.findStartDestination().id) {
                                saveState = true
                            }
                            launchSingleTop = true
                            restoreState = true
                        }
                    },
                    selectedLanguage = selectedLanguage
                )
            }
        }
    ) { innerPadding ->
        NavHost(
            navController = navController,
            startDestination = "home_graph",
            modifier = Modifier.padding(innerPadding)
        ) {
            // Nested Graph 1: HOME TAB
            navigation(startDestination = "home", route = "home_graph") {
                composable("home") {
                    HomeScreen(
                        viewModel = triageViewModel,
                        uiState = triageUiState,
                        onBookServices = {
                            bookingViewModel.startNewBooking()
                            triageViewModel.navigateToBookServices()
                        }
                    )
                }

                composable("book_services") {
                    BookServicesScreen(
                        selectedLanguage = selectedLanguage,
                        onLanguageSelected = { triageViewModel.setLanguage(it) },
                        onSelectService = { service ->
                            bookingViewModel.selectService(service)
                            triageViewModel.navigateToBookingFlow()
                        },
                        onEmergencyClick = {
                            triageViewModel.navigateToEmergency()
                        },
                        onBack = {
                            triageViewModel.navigateToHome()
                        }
                    )
                }

                composable("chat") {
                    ChatScreen(
                        viewModel = triageViewModel,
                        uiState = triageUiState
                    )
                }

                composable("emergency") {
                    EmergencyScreen(
                        uiState = triageUiState,
                        onReset = {
                            triageViewModel.reset()
                            navController.navigate("home") {
                                popUpTo("home") { inclusive = true }
                            }
                        }
                    )
                }

                composable("result") {
                    ResultScreen(
                        uiState = triageUiState,
                        onBookCaregiver = { cgId ->
                            triageViewModel.startBooking(cgId)
                        },
                        onStartOver = {
                            triageViewModel.reset()
                            navController.navigate("home") {
                                popUpTo("home") { inclusive = true }
                            }
                        }
                    )
                }

                composable(
                    route = "booking/{caregiverId}",
                    arguments = listOf(navArgument("caregiverId") { type = NavType.StringType })
                ) { backStackEntry ->
                    val caregiverId = backStackEntry.arguments?.getString("caregiverId") ?: ""
                    BookingScreen(
                        caregiverId = caregiverId,
                        viewModel = triageViewModel,
                        uiState = triageUiState,
                        onDone = {
                            triageViewModel.reset()
                            navController.navigate("home") {
                                popUpTo("home") { inclusive = true }
                            }
                        }
                    )
                }

                composable("booking_flow") {
                    BookingFlowScreen(
                        viewModel = bookingViewModel,
                        selectedLanguage = selectedLanguage,
                        onLanguageSelected = { triageViewModel.setLanguage(it) },
                        userLocation = triageUiState.userLocation,
                        onEmergency = { resp ->
                            triageViewModel.navigateToEmergency(resp)
                        },
                        onBack = {
                            bookingViewModel.goBack {
                                triageViewModel.navigateToHome()
                            }
                        },
                        onDone = {
                            bookingViewModel.reset()
                            triageViewModel.navigateToHome()
                        }
                    )
                }
            }

            // Nested Graph 2: HISTORY TAB
            navigation(startDestination = "history", route = "history_graph") {
                composable("history") {
                    HistoryScreen(
                        viewModel = historyViewModel,
                        selectedLanguage = selectedLanguage,
                        onLanguageSelected = { triageViewModel.setLanguage(it) },
                        onSelectHistoryItem = { id ->
                            historyViewModel.selectHistoryItem(id)
                            navController.navigate("history_detail/$id")
                        },
                        onNavigateHome = {
                            navController.navigate("home_graph") {
                                popUpTo(navController.graph.findStartDestination().id) {
                                    saveState = true
                                }
                                launchSingleTop = true
                                restoreState = true
                            }
                        }
                    )
                }

                composable(
                    route = "history_detail/{id}",
                    arguments = listOf(navArgument("id") { type = NavType.StringType })
                ) {
                    HistoryDetailScreen(
                        viewModel = historyViewModel,
                        selectedLanguage = selectedLanguage,
                        onLanguageSelected = { triageViewModel.setLanguage(it) },
                        onBack = {
                            historyViewModel.clearSelectedDetail()
                            navController.popBackStack()
                        },
                        onViewInBookings = {
                            // Switch to Bookings tab
                            navController.navigate("bookings_graph") {
                                popUpTo(navController.graph.findStartDestination().id) {
                                    saveState = true
                                }
                                launchSingleTop = true
                                restoreState = true
                            }
                        }
                    )
                }
            }

            // Nested Graph 3: BOOKINGS TAB
            navigation(startDestination = "bookings", route = "bookings_graph") {
                composable("bookings") {
                    BookingsScreen(
                        viewModel = bookingsViewModel,
                        selectedLanguage = selectedLanguage,
                        onLanguageSelected = { triageViewModel.setLanguage(it) },
                        onBookServiceClick = {
                            // Start a new AI-decided booking (no service selection)
                            bookingViewModel.startNewBooking()
                            triageViewModel.navigateToBookingFlow()
                        },
                        onRescheduleBooking = { booking ->
                            val service = when {
                                booking.service.contains("lab", ignoreCase = true) || booking.careType.contains("lab", ignoreCase = true) -> CareService.LAB_TEST_HOME
                                booking.service.contains("tele", ignoreCase = true) || booking.careType.contains("tele", ignoreCase = true) -> CareService.TELECONSULTATION
                                else -> CareService.HOME_NURSING
                            }

                            val matchedCaregiver = MatchedCaregiver(
                                caregiverId = "CG_${booking.caregiver.name.hashCode()}",
                                score = 0.95,
                                reason = "Previous assigned caregiver",
                                name = booking.caregiver.name,
                                role = booking.caregiver.role,
                                qualification = booking.caregiver.qualification
                            )

                            bookingViewModel.openStep3ForReschedule(
                                caregiver = matchedCaregiver,
                                service = service,
                                initialPatientName = booking.patientName,
                                initialRelation = booking.relation
                            )
                            triageViewModel.navigateToBookingFlow()
                        }
                    )
                }
            }
        }
    }
}
