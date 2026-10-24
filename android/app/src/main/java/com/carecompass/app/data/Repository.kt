package com.carecompass.app.data

import com.carecompass.app.BuildConfig
import com.carecompass.app.data.cache.HistoryCache
import java.time.Instant
import java.time.temporal.ChronoUnit

class Repository(
    private val apiService: ApiService,
    private val historyCache: HistoryCache? = null,
    private val useMockRepo: Boolean = BuildConfig.USE_MOCK_REPO
) {

    // In-memory store for mock demo
    private val mockHistory = mutableListOf<HistoryDetail>()
    private val mockBookings = mutableListOf<Booking>()

    init {
        initMockData()
    }

    private fun initMockData() {
        try {
            val now = Instant.now()

            // 1. Same-day fever session
            val session1Id = "hist_001"
            val session1Time = now.minus(2, ChronoUnit.HOURS).toString()
            val summary1 = HistorySummary(
                id = session1Id,
                firstMessage = "High fever and persistent cough for 2 days, body feels very hot and weak.",
                viaVoice = false,
                outcome = "same_day",
                careType = "paramedic_home_visit",
                createdAt = session1Time
            )
            val detail1 = HistoryDetail(
                id = session1Id,
                createdAt = session1Time,
                summary = summary1,
                steps = listOf(
                    HistoryStep(
                        type = "user_said",
                        title = "You said",
                        subtitle = "High fever and persistent cough for 2 days, body feels very hot and weak.",
                        isVoice = false
                    ),
                    HistoryStep(
                        type = "follow_up",
                        title = "Is there any difficulty in breathing or chest tightness?",
                        userAnswer = "No"
                    ),
                    HistoryStep(
                        type = "result",
                        title = "Result",
                        careType = "Medic home visit",
                        urgency = "same_day",
                        reasoning = "Moderate acute fever with cough but no breathing distress. Paramedic visit advised today to check vitals, oxygen levels, and start symptomatic treatment."
                    ),
                    HistoryStep(
                        type = "caregivers",
                        title = "Suggested caregivers",
                        suggestedCaregivers = listOf("Medic Amit Kumar", "Nurse Sunita Sharma", "Dr. Rajesh Verma"),
                        chosenCaregiver = "Medic Amit Kumar"
                    ),
                    HistoryStep(
                        type = "booking",
                        title = "Booking",
                        bookingId = "BK_MEDIC_01",
                        bookingDate = "Today, 24 Oct 2026",
                        bookingTime = "4:00 PM – 5:00 PM",
                        chosenCaregiver = "Medic Amit Kumar"
                    )
                )
            )

            // 2. Emergency chest pain session
            val session2Id = "hist_002"
            val session2Time = now.minus(18, ChronoUnit.HOURS).toString()
            val summary2 = HistorySummary(
                id = session2Id,
                firstMessage = "Sudden severe chest pain radiating to left arm and sweating profusely.",
                viaVoice = true,
                outcome = "emergency",
                careType = "emergency_112",
                createdAt = session2Time
            )
            val detail2 = HistoryDetail(
                id = session2Id,
                createdAt = session2Time,
                summary = summary2,
                steps = listOf(
                    HistoryStep(
                        type = "user_said",
                        title = "You said",
                        subtitle = "Sudden severe chest pain radiating to left arm and sweating profusely.",
                        isVoice = true
                    ),
                    HistoryStep(
                        type = "emergency_alert",
                        title = "Emergency steps shown, 112 advised",
                        emergencyText = "Red flag cardiac symptoms detected. National Emergency 112 was called and immediate rest advised."
                    ),
                    HistoryStep(
                        type = "result",
                        title = "Result",
                        careType = "Emergency (112)",
                        urgency = "emergency",
                        reasoning = "Immediate hospital emergency required. Ambulance dispatched."
                    )
                )
            )

            // 3. Home nursing session
            val session3Id = "hist_003"
            val session3Time = now.minus(2, ChronoUnit.DAYS).toString()
            val summary3 = HistorySummary(
                id = session3Id,
                firstMessage = "Need dressing change for surgical wound and evening antibiotic injection.",
                viaVoice = false,
                outcome = "scheduled",
                careType = "home_nursing",
                createdAt = session3Time
            )
            val detail3 = HistoryDetail(
                id = session3Id,
                createdAt = session3Time,
                summary = summary3,
                steps = listOf(
                    HistoryStep(
                        type = "user_said",
                        title = "You said",
                        subtitle = "Need dressing change for surgical wound and evening antibiotic injection.",
                        isVoice = false
                    ),
                    HistoryStep(
                        type = "result",
                        title = "Result",
                        careType = "Home nursing",
                        urgency = "scheduled",
                        reasoning = "Post-operative dressing and IV/IM administration safely managed at home by registered nurse."
                    ),
                    HistoryStep(
                        type = "caregivers",
                        title = "Suggested caregivers",
                        suggestedCaregivers = listOf("Nurse Sunita Sharma", "Nurse Preeti Patel"),
                        chosenCaregiver = "Nurse Sunita Sharma"
                    ),
                    HistoryStep(
                        type = "booking",
                        title = "Booking",
                        bookingId = "BK_NURSE_02",
                        bookingDate = "22 Oct 2026",
                        bookingTime = "11:30 AM – 12:30 PM",
                        chosenCaregiver = "Nurse Sunita Sharma"
                    )
                )
            )

            // 4. Lab test at home session
            val session4Id = "hist_004"
            val session4Time = now.minus(4, ChronoUnit.DAYS).toString()
            val summary4 = HistorySummary(
                id = session4Id,
                firstMessage = "Fasting blood sugar and lipid profile test required for elderly parent.",
                viaVoice = false,
                outcome = "scheduled",
                careType = "lab_test_home",
                createdAt = session4Time
            )
            val detail4 = HistoryDetail(
                id = session4Id,
                createdAt = session4Time,
                summary = summary4,
                steps = listOf(
                    HistoryStep(
                        type = "user_said",
                        title = "You said",
                        subtitle = "Fasting blood sugar and lipid profile test required for elderly parent.",
                        isVoice = false
                    ),
                    HistoryStep(
                        type = "result",
                        title = "Result",
                        careType = "Lab test at home",
                        urgency = "scheduled",
                        reasoning = "Morning phlebotomy collection booked for home visit."
                    ),
                    HistoryStep(
                        type = "caregivers",
                        title = "Suggested caregivers",
                        suggestedCaregivers = listOf("Ramesh Patel", "Vikram Singh"),
                        chosenCaregiver = "Ramesh Patel"
                    )
                )
            )

            // 5. Teleconsultation session
            val session5Id = "hist_005"
            val session5Time = now.minus(6, ChronoUnit.DAYS).toString()
            val summary5 = HistorySummary(
                id = session5Id,
                firstMessage = "Mild skin rash on forearm with slight itching since yesterday evening.",
                viaVoice = false,
                outcome = "needs_more_info",
                careType = "teleconsultation",
                createdAt = session5Time
            )
            val detail5 = HistoryDetail(
                id = session5Id,
                createdAt = session5Time,
                summary = summary5,
                steps = listOf(
                    HistoryStep(
                        type = "user_said",
                        title = "You said",
                        subtitle = "Mild skin rash on forearm with slight itching since yesterday evening.",
                        isVoice = false
                    ),
                    HistoryStep(
                        type = "follow_up",
                        title = "Did you start any new medication or eat unusual food recently?",
                        userAnswer = "Not sure"
                    ),
                    HistoryStep(
                        type = "result",
                        title = "Result",
                        careType = "Doctor teleconsultation",
                        urgency = "scheduled",
                        reasoning = "Non-emergency localized dermatitis. Video consultation with general physician recommended."
                    ),
                    HistoryStep(
                        type = "caregivers",
                        title = "Suggested caregivers",
                        suggestedCaregivers = listOf("Dr. Ananya Rao", "Dr. Rajesh Verma"),
                        chosenCaregiver = "Dr. Ananya Rao"
                    )
                )
            )

            mockHistory.addAll(listOf(detail1, detail2, detail3, detail4, detail5))

            // Initial Bookings
            // Upcoming 1: Home nursing today (2 hours from now)
            val bookStart1 = now.plus(2, ChronoUnit.HOURS).toString()
            val bookEnd1 = now.plus(3, ChronoUnit.HOURS).toString()
            val b1 = Booking(
                id = "BK_001",
                service = "Home nursing",
                careType = "home_nursing",
                patientName = "Papa",
                relation = "Papa",
                caregiver = CaregiverInfo(
                    name = "Nurse Sunita Sharma",
                    role = "Nurse",
                    qualification = "B.Sc Nursing, 8 yrs exp",
                    phone = "9876543210"
                ),
                startTime = bookStart1,
                endTime = bookEnd1,
                address = "Flat 402, Green Glen Layout, Bellandur, Bengaluru",
                status = "confirmed"
            )

            // Upcoming 2: Lab test tomorrow morning
            val bookStart2 = now.plus(1, ChronoUnit.DAYS).truncatedTo(ChronoUnit.DAYS).plus(9, ChronoUnit.HOURS).toString()
            val bookEnd2 = now.plus(1, ChronoUnit.DAYS).truncatedTo(ChronoUnit.DAYS).plus(10, ChronoUnit.HOURS).toString()
            val b2 = Booking(
                id = "BK_002",
                service = "Lab test at home",
                careType = "lab_test_home",
                patientName = "Myself",
                relation = null,
                caregiver = CaregiverInfo(
                    name = "Ramesh Patel",
                    role = "Lab technician",
                    qualification = "DMLT, Certified Phlebotomist",
                    phone = "9812345678"
                ),
                startTime = bookStart2,
                endTime = bookEnd2,
                address = "Flat 402, Green Glen Layout, Bellandur, Bengaluru",
                status = "pending"
            )

            // Upcoming 3: Teleconsultation within 10 minutes (for Join call testing)
            val bookStart3 = now.plus(5, ChronoUnit.MINUTES).toString()
            val bookEnd3 = now.plus(35, ChronoUnit.MINUTES).toString()
            val b3 = Booking(
                id = "BK_003",
                service = "Teleconsultation",
                careType = "teleconsultation",
                patientName = "Mama",
                relation = "Mama",
                caregiver = CaregiverInfo(
                    name = "Dr. Ananya Rao",
                    role = "Doctor",
                    qualification = "MBBS, MD (General Medicine)",
                    phone = "9823456789"
                ),
                startTime = bookStart3,
                endTime = bookEnd3,
                address = null,
                status = "confirmed"
            )

            // Past Booking 1: Completed home visit 3 days ago
            val pastStart1 = now.minus(3, ChronoUnit.DAYS).plus(10, ChronoUnit.HOURS).toString()
            val pastEnd1 = now.minus(3, ChronoUnit.DAYS).plus(11, ChronoUnit.HOURS).toString()
            val bPast1 = Booking(
                id = "BK_PAST_01",
                service = "Home nursing",
                careType = "home_nursing",
                patientName = "Child",
                relation = "Child",
                caregiver = CaregiverInfo(
                    name = "Medic Amit Kumar",
                    role = "Medic",
                    qualification = "Paramedic Diploma, 5 yrs exp",
                    phone = "9834567890"
                ),
                startTime = pastStart1,
                endTime = pastEnd1,
                address = "Flat 402, Green Glen Layout, Bellandur, Bengaluru",
                status = "completed"
            )

            mockBookings.addAll(listOf(b1, b2, b3, bPast1))
        } catch (e: Exception) {
            // Fallback
        }
    }

    suspend fun triage(request: TriageRequest): Result<TriageResponse> {
        return runCatching { apiService.triage(request) }
    }

    suspend fun matchCaregivers(request: MatchRequest): Result<List<MatchedCaregiver>> {
        return runCatching { apiService.matchCaregivers(request) }
    }

    suspend fun getCaregivers(): Result<List<CaregiverProfile>> {
        return runCatching { apiService.getCaregivers() }
    }

    suspend fun createBooking(request: BookingRequest): Result<BookingResponse> {
        if (useMockRepo) {
            val bId = "BK_" + System.currentTimeMillis().toString().takeLast(6)
            val displayName = if (request.relation != null && request.relation.isNotBlank()) {
                request.patientName ?: request.userName
            } else {
                request.userName
            }

            val newBooking = Booking(
                id = bId,
                service = request.service ?: "Home nursing",
                careType = request.careType ?: "home_nursing",
                patientName = displayName,
                relation = request.relation,
                caregiver = CaregiverInfo(
                    name = "Assigned Caregiver",
                    role = "Nurse",
                    qualification = "Registered Nurse",
                    phone = request.phone
                ),
                startTime = Instant.now().plus(1, ChronoUnit.DAYS).toString(),
                endTime = Instant.now().plus(1, ChronoUnit.DAYS).plus(1, ChronoUnit.HOURS).toString(),
                address = request.address,
                status = "confirmed"
            )
            mockBookings.add(0, newBooking)

            return Result.success(
                BookingResponse(
                    bookingId = bId,
                    status = "confirmed",
                    eta = "Tomorrow",
                    caregiverId = request.caregiverId,
                    slot = request.slot,
                    userName = request.userName,
                    phone = request.phone,
                    patientName = request.patientName,
                    relation = request.relation
                )
            )
        }

        return runCatching { apiService.createBooking(request) }
    }

    suspend fun validateTranscript(text: String, language: String): Result<TranscribeResponse> {
        return runCatching {
            apiService.validateTranscript(text, language)
        }
    }

    suspend fun getHistory(limit: Int = 5): Result<List<HistorySummary>> {
        if (useMockRepo) {
            val summaries = mockHistory.mapNotNull { it.summary }.take(limit)
            historyCache?.saveHistorySummaries(summaries)
            return Result.success(summaries)
        }

        return runCatching {
            val remote = apiService.getHistory(limit)
            historyCache?.saveHistorySummaries(remote)
            remote
        }.recoverCatching { err ->
            // Offline fallback from cache
            val cached = historyCache?.getHistorySummaries()
            if (!cached.isNullOrEmpty()) {
                cached
            } else {
                throw err
            }
        }
    }

    suspend fun getHistoryDetail(id: String): Result<HistoryDetail> {
        if (useMockRepo) {
            val item = mockHistory.find { it.id == id }
                ?: mockHistory.firstOrNull()
                ?: HistoryDetail(id = id, createdAt = Instant.now().toString())
            historyCache?.saveHistoryDetail(item)
            return Result.success(item)
        }

        return runCatching {
            val remote = apiService.getHistoryDetail(id)
            historyCache?.saveHistoryDetail(remote)
            remote
        }.recoverCatching { err ->
            val cached = historyCache?.getHistoryDetail(id)
            if (cached != null) {
                cached
            } else {
                throw err
            }
        }
    }

    suspend fun deleteHistory(id: String): Result<Unit> {
        if (useMockRepo) {
            mockHistory.removeAll { it.id == id }
            historyCache?.deleteHistory(id)
            return Result.success(Unit)
        }

        return runCatching {
            apiService.deleteHistory(id)
            historyCache?.deleteHistory(id)
            Unit
        }.recoverCatching {
            // Delete locally if offline
            historyCache?.deleteHistory(id)
            Unit
        }
    }

    suspend fun getBookings(status: String? = null): Result<List<Booking>> {
        if (useMockRepo) {
            val list = if (status == "upcoming") {
                mockBookings.filter { it.status == "confirmed" || it.status == "pending" }
            } else {
                mockBookings.toList()
            }
            return Result.success(list)
        }

        return runCatching {
            apiService.getBookings(status)
        }.recoverCatching { err ->
            // Fallback to in-memory mock if backend route not ready
            if (status == "upcoming") {
                mockBookings.filter { it.status == "confirmed" || it.status == "pending" }
            } else {
                mockBookings.toList()
            }
        }
    }

    suspend fun cancelBooking(id: String): Result<Booking> {
        if (useMockRepo) {
            val idx = mockBookings.indexOfFirst { it.id == id }
            if (idx != -1) {
                val updated = mockBookings[idx].copy(status = "cancelled")
                mockBookings[idx] = updated
                return Result.success(updated)
            }
            return Result.failure(Exception("Booking not found"))
        }

        return runCatching {
            apiService.cancelBooking(id)
        }.recoverCatching {
            val idx = mockBookings.indexOfFirst { it.id == id }
            if (idx != -1) {
                val updated = mockBookings[idx].copy(status = "cancelled")
                mockBookings[idx] = updated
                updated
            } else {
                throw it
            }
        }
    }
}
