package com.carecompass.app.data

class Repository(private val apiService: ApiService) {

    suspend fun triage(request: TriageRequest): Result<TriageResponse> {
        return runCatching { apiService.triage(request) }
    }

    suspend fun getCaregivers(): Result<List<CaregiverProfile>> {
        return runCatching { apiService.getCaregivers() }
    }

    suspend fun createBooking(request: BookingRequest): Result<BookingResponse> {
        return runCatching { apiService.createBooking(request) }
    }
}
