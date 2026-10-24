package com.carecompass.app.data

import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import java.util.concurrent.TimeUnit

interface ApiService {

    @POST("triage")
    suspend fun triage(@Body request: TriageRequest): TriageResponse

    @GET("caregivers")
    suspend fun getCaregivers(): List<CaregiverProfile>

    @POST("book")
    suspend fun createBooking(@Body request: BookingRequest): BookingResponse

    @GET("bookings/{id}")
    suspend fun getBooking(@Path("id") id: String): BookingResponse

    companion object {
        private const val BASE_URL = "http://10.0.2.2:8000/"

        fun create(): ApiService {
            val logging = HttpLoggingInterceptor().apply {
                level = HttpLoggingInterceptor.Level.BODY
            }

            val client = OkHttpClient.Builder()
                .addInterceptor(logging)
                .connectTimeout(10, TimeUnit.SECONDS)
                .readTimeout(10, TimeUnit.SECONDS)
                .build()

            return Retrofit.Builder()
                .baseUrl(BASE_URL)
                .client(client)
                .addConverterFactory(GsonConverterFactory.create())
                .build()
                .create(ApiService::class.java)
        }
    }
}
