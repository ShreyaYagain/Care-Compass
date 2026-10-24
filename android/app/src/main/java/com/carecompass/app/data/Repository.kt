package com.carecompass.app.data

import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File

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

    suspend fun transcribeAudio(file: File, language: String): Result<TranscribeResponse> {
        return runCatching {
            val reqFile = file.asRequestBody("audio/*".toMediaTypeOrNull())
            val part = MultipartBody.Part.createFormData("audio", file.name, reqFile)
            val langBody = language.toRequestBody("text/plain".toMediaTypeOrNull())
            apiService.transcribeAudio(part, langBody)
        }
    }
}
