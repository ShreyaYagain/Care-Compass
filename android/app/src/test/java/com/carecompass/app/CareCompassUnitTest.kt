package com.carecompass.app

import com.carecompass.app.data.*
import com.carecompass.app.util.DateTimeFormatterHelper
import com.carecompass.app.viewmodel.BookingViewModel
import com.carecompass.app.viewmodel.BookingsViewModel
import com.carecompass.app.viewmodel.CareService
import com.carecompass.app.viewmodel.HistoryViewModel
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import java.time.Instant
import java.time.temporal.ChronoUnit

@OptIn(ExperimentalCoroutinesApi::class)
class CareCompassUnitTest {

    private val testDispatcher = StandardTestDispatcher()

    @Before
    fun setUp() {
        Dispatchers.setMain(testDispatcher)
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun testDateTimeFormatterHelper_dayBadgeAndFormatting() {
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
            val now = Instant.now()
            val todayIso = now.toString()
            val tomorrowIso = now.plus(1, ChronoUnit.DAYS).toString()

            val badgeTodayEn = DateTimeFormatterHelper.getDayBadge(todayIso, "en")
            val badgeTodayHi = DateTimeFormatterHelper.getDayBadge(todayIso, "hi")
            val badgeTomorrowEn = DateTimeFormatterHelper.getDayBadge(tomorrowIso, "en")

            assertEquals("Today", badgeTodayEn)
            assertEquals("आज", badgeTodayHi)
            assertEquals("Tomorrow", badgeTomorrowEn)

            val formattedRange = DateTimeFormatterHelper.formatBookingDateRange(
                todayIso,
                now.plus(1, ChronoUnit.HOURS).toString()
            )
            assertTrue(formattedRange.contains("to"))
        }
    }

    @Test
    fun testDateTimeFormatterHelper_within15Minutes() {
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
            val now = Instant.now()
            // 5 minutes from now -> within 15 min
            val startNear = now.plus(5, ChronoUnit.MINUTES).toString()
            val endNear = now.plus(35, ChronoUnit.MINUTES).toString()
            assertTrue(DateTimeFormatterHelper.isWithin15MinutesOfStart(startNear, endNear))

            // 60 minutes from now -> not within 15 min
            val startFar = now.plus(60, ChronoUnit.MINUTES).toString()
            val endFar = now.plus(90, ChronoUnit.MINUTES).toString()
            assertFalse(DateTimeFormatterHelper.isWithin15MinutesOfStart(startFar, endFar))
        }
    }

    @Test
    fun testHistoryViewModel_loadsHistoryAndDetail() = runTest {
        val repository = Repository(ApiService.create(), useMockRepo = true)
        val historyViewModel = HistoryViewModel(repository)

        testDispatcher.scheduler.advanceUntilIdle()

        val state = historyViewModel.uiState.value
        assertFalse(state.isLoading)
        assertTrue(state.historyItems.isNotEmpty())
        assertEquals(5, state.historyItems.size)

        // Select first item
        val firstId = state.historyItems.first().id
        historyViewModel.selectHistoryItem(firstId)
        testDispatcher.scheduler.advanceUntilIdle()

        val detailState = historyViewModel.uiState.value
        assertNotNull(detailState.selectedDetail)
        assertEquals(firstId, detailState.selectedDetail?.id)
        assertTrue(detailState.selectedDetail?.steps?.isNotEmpty() == true)

        // Delete flow
        historyViewModel.promptDelete(firstId)
        assertTrue(historyViewModel.uiState.value.showDeleteConfirmDialog)

        var deletedCalled = false
        historyViewModel.confirmDelete { deletedCalled = true }
        testDispatcher.scheduler.advanceUntilIdle()

        assertTrue(deletedCalled)
        assertEquals(4, historyViewModel.uiState.value.historyItems.size)
    }

    @Test
    fun testBookingsViewModel_loadsAndCancels() = runTest {
        val repository = Repository(ApiService.create(), useMockRepo = true)
        val bookingsViewModel = BookingsViewModel(repository)

        testDispatcher.scheduler.advanceUntilIdle()

        val state = bookingsViewModel.uiState.value
        assertFalse(state.isLoading)
        assertTrue(state.upcomingBookings.isNotEmpty())

        val upcomingCountBefore = state.upcomingBookings.size
        val pastCountBefore = state.pastBookings.size

        val toCancel = state.upcomingBookings.first()
        bookingsViewModel.promptCancel(toCancel)
        assertTrue(bookingsViewModel.uiState.value.showCancelConfirmDialog)

        bookingsViewModel.confirmCancel()
        testDispatcher.scheduler.advanceUntilIdle()

        val updatedState = bookingsViewModel.uiState.value
        assertEquals(upcomingCountBefore - 1, updatedState.upcomingBookings.size)
        assertEquals(pastCountBefore + 1, updatedState.pastBookings.size)
        assertEquals("cancelled", updatedState.pastBookings.first().status)
    }

    @Test
    fun testBookingViewModel_happyPath_confirmsBooking() = runTest {
        val repository = Repository(ApiService.create(), useMockRepo = true)
        val viewModel = BookingViewModel(repository)

        viewModel.startNewBooking()
        // Seam that reaches step 3 without a network call: a caregiver is chosen.
        viewModel.openStep3ForReschedule(
            caregiver = MatchedCaregiver(
                caregiverId = "CG_001",
                score = 0.95,
                reason = "test",
                name = "Mohit Gupta",
                role = "doctor",
                qualification = "MBBS",
                freeFrom = "09:00",
                freeUntil = "18:00"
            ),
            service = CareService.TELECONSULTATION,
            initialPatientName = "Rohan",
            initialRelation = null
        )
        viewModel.selectDate(0)
        viewModel.selectSlot("10:00-11:00")
        viewModel.updatePatientDetails("Rohan", "9876543210", "Noida Sec 18")
        viewModel.setForWhom("myself")

        var confirmed: BookingResponse? = null
        viewModel.confirmBooking { confirmed = it }
        testDispatcher.scheduler.advanceUntilIdle()

        val state = viewModel.uiState.value
        assertNull(state.errorMessage)
        assertEquals(4, state.currentStep)
        assertNotNull(state.bookingResponse)
        assertNotNull(confirmed)
        assertTrue(confirmed!!.bookingId.isNotBlank())

        // The request must carry an ISO start/end time and the mapped care type.
        val saved = repository.lastBookingRequest
        assertNotNull(saved)
        assertEquals("teleconsultation", saved!!.careType)
        assertNotNull(saved.startTime)
        assertNotNull(saved.endTime)
    }

    @Test
    fun testCareService_fromCareType_mapsAllTypes() {
        assertEquals(CareService.HOME_NURSING, CareService.fromCareType("home_nursing"))
        assertEquals(CareService.HOME_NURSING, CareService.fromCareType("paramedic_home_visit"))
        assertEquals(CareService.LAB_TEST_HOME, CareService.fromCareType("lab_test_home"))
        assertEquals(CareService.TELECONSULTATION, CareService.fromCareType("teleconsultation"))
        assertEquals(CareService.HOME_NURSING, CareService.fromCareType(null))
    }

    @Test
    fun testBuildBookingIso_producesIsoFormat() {
        val iso = DateTimeFormatterHelper.buildBookingIso(1, 10, 0)
        assertTrue(iso.matches(Regex("\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z")))
    }
}
