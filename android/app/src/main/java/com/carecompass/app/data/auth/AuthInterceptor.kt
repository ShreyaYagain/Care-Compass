package com.carecompass.app.data.auth

import kotlinx.coroutines.runBlocking
import okhttp3.Interceptor
import okhttp3.Response

class AuthInterceptor(private val authManager: SupabaseAuthManager) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val originalRequest = chain.request()

        // Attach Authorization header (token) and the per-device history key.
        // DEVICE_ID_HEADER is the single definition shared with the backend.
        val (token, deviceId) = runBlocking {
            authManager.getAccessToken() to authManager.getUserId()
        }

        val builder = originalRequest.newBuilder()
        if (!token.isNullOrBlank()) {
            builder.header("Authorization", "Bearer $token")
        }
        if (deviceId.isNotBlank()) {
            builder.header(DEVICE_ID_HEADER, deviceId)
        }
        val authenticatedRequest = builder.build()

        val response = chain.proceed(authenticatedRequest)

        // If 401 Unauthorized, attempt token refresh once
        if (response.code == 401) {
            response.close()
            val refreshedToken = runBlocking { authManager.refreshToken() }
            if (!refreshedToken.isNullOrBlank()) {
                val newRequest = originalRequest.newBuilder()
                    .header("Authorization", "Bearer $refreshedToken")
                    .build()
                return chain.proceed(newRequest)
            }
        }

        return response
    }

    companion object {
        /** History key header: must match app/config.py HISTORY_KEY_HEADER. */
        const val DEVICE_ID_HEADER = "X-Device-Id"
    }
}
