package com.carecompass.app.data.auth

import kotlinx.coroutines.runBlocking
import okhttp3.Interceptor
import okhttp3.Response

class AuthInterceptor(private val authManager: SupabaseAuthManager) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val originalRequest = chain.request()

        // Attach Authorization header if token is present
        val token = runBlocking { authManager.getAccessToken() }
        val authenticatedRequest = if (!token.isNullOrBlank()) {
            originalRequest.newBuilder()
                .header("Authorization", "Bearer $token")
                .build()
        } else {
            originalRequest
        }

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
}
