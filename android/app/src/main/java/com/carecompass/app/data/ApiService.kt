package com.carecompass.app.data

import android.content.Context
import com.carecompass.app.data.auth.AuthInterceptor
import com.carecompass.app.data.auth.SupabaseAuthManager
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Response
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.*
import java.util.concurrent.TimeUnit

interface ApiService {

    @POST("triage")
    suspend fun triage(@Body request: TriageRequest): TriageResponse

    @POST("match")
    suspend fun matchCaregivers(@Body request: MatchRequest): List<MatchedCaregiver>

    @GET("caregivers")
    suspend fun getCaregivers(): List<CaregiverProfile>

    @POST("book")
    suspend fun createBooking(@Body request: BookingRequest): BookingResponse

    @GET("bookings/{id}")
    suspend fun getBooking(@Path("id") id: String): BookingResponse

    @GET("bookings")
    suspend fun getBookings(@Query("status") status: String? = null): List<Booking>

    @POST("bookings/{id}/cancel")
    suspend fun cancelBooking(@Path("id") id: String): Booking

    @GET("history")
    suspend fun getHistory(@Query("limit") limit: Int = 5): List<HistorySummary>

    @GET("history/{id}")
    suspend fun getHistoryDetail(@Path("id") id: String): HistoryDetail

    @DELETE("history/{id}")
    suspend fun deleteHistory(@Path("id") id: String): Response<Unit>

    @FormUrlEncoded
    @POST("transcribe")
    suspend fun validateTranscript(
        @Field("text") text: String,
        @Field("language") language: String? = null
    ): TranscribeResponse

    companion object {
        private const val BASE_URL = "http://10.0.2.2:8000/"

        fun create(context: Context? = null): ApiService {
            val logging = HttpLoggingInterceptor().apply {
                level = HttpLoggingInterceptor.Level.BODY
            }

            val clientBuilder = OkHttpClient.Builder()
                .addInterceptor(logging)
                .connectTimeout(10, TimeUnit.SECONDS)
                .readTimeout(10, TimeUnit.SECONDS)

            if (context != null) {
                val authManager = SupabaseAuthManager.getInstance(context)
                clientBuilder.addInterceptor(AuthInterceptor(authManager))
            }

            val client = clientBuilder.build()

            return Retrofit.Builder()
                .baseUrl(BASE_URL)
                .client(client)
                .addConverterFactory(GsonConverterFactory.create())
                .build()
                .create(ApiService::class.java)
        }
    }
}
