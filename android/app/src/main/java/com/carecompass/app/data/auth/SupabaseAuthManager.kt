package com.carecompass.app.data.auth

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import com.carecompass.app.BuildConfig
import io.github.jan.supabase.SupabaseClient
import io.github.jan.supabase.auth.Auth
import io.github.jan.supabase.auth.auth
import io.github.jan.supabase.createSupabaseClient
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.UUID

class SupabaseAuthManager(private val context: Context) {

    private val prefs: SharedPreferences by lazy {
        try {
            val masterKey = MasterKey.Builder(context)
                .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                .build()
            EncryptedSharedPreferences.create(
                context,
                "carecompass_secure_auth",
                masterKey,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
            )
        } catch (e: Exception) {
            Log.w("SupabaseAuth", "EncryptedSharedPreferences unavailable, falling back to private prefs", e)
            context.getSharedPreferences("carecompass_auth_prefs", Context.MODE_PRIVATE)
        }
    }

    private val supabase: SupabaseClient by lazy {
        createSupabaseClient(
            supabaseUrl = BuildConfig.SUPABASE_URL,
            supabaseKey = BuildConfig.SUPABASE_ANON_KEY
        ) {
            install(Auth)
        }
    }

    companion object {
        private const val KEY_ACCESS_TOKEN = "supabase_access_token"
        private const val KEY_REFRESH_TOKEN = "supabase_refresh_token"
        private const val KEY_USER_ID = "supabase_user_id"
        private const val KEY_EXPIRES_AT = "supabase_token_expires_at"

        @Volatile
        private var INSTANCE: SupabaseAuthManager? = null

        fun getInstance(context: Context): SupabaseAuthManager {
            return INSTANCE ?: synchronized(this) {
                INSTANCE ?: SupabaseAuthManager(context.applicationContext).also { INSTANCE = it }
            }
        }
    }

    /**
     * True only when a real Supabase project is configured. When false, we skip
     * all network sign-in attempts (which would otherwise hang the request) and
     * use the local demo token. The backend accepts any token in dev mode.
     */
    private val supabaseConfigured: Boolean
        get() = BuildConfig.SUPABASE_URL.isNotBlank() &&
            BuildConfig.SUPABASE_URL != "https://mock.supabase.co" &&
            BuildConfig.SUPABASE_ANON_KEY.isNotBlank() &&
            BuildConfig.SUPABASE_ANON_KEY != "mock-anon-key-carecompass-2026"

    suspend fun getUserId(): String = withContext(Dispatchers.IO) {
        var uid = prefs.getString(KEY_USER_ID, null)
        if (uid.isNullOrBlank()) {
            ensureSession()
            uid = prefs.getString(KEY_USER_ID, null) ?: UUID.randomUUID().toString().also {
                prefs.edit().putString(KEY_USER_ID, it).apply()
            }
        }
        uid
    }

    suspend fun getAccessToken(): String? = withContext(Dispatchers.IO) {
        val expiresAt = prefs.getLong(KEY_EXPIRES_AT, 0L)
        val now = System.currentTimeMillis()
        val currentToken = prefs.getString(KEY_ACCESS_TOKEN, null)

        if (currentToken.isNullOrBlank() || now >= expiresAt - 30_000L) {
            // Expired or missing -> refresh or sign in anonymously
            refreshToken() ?: ensureSession()
        } else {
            currentToken
        }
    }

    suspend fun ensureSession(): String? = withContext(Dispatchers.IO) {
        if (supabaseConfigured) {
            try {
                // Check if we can sign in anonymously via Supabase Auth
                supabase.auth.signInAnonymously()
                val session = supabase.auth.currentSessionOrNull()
                if (session != null) {
                    val token = session.accessToken
                    val refreshToken = session.refreshToken
                    val userId = session.user?.id ?: UUID.randomUUID().toString()
                    val expiresAt = System.currentTimeMillis() + (session.expiresIn * 1000L)

                    saveSession(token, refreshToken, userId, expiresAt)
                    return@withContext token
                }
            } catch (e: Exception) {
                Log.e("SupabaseAuth", "Supabase anonymous sign-in failed, checking stored session or fallback", e)
            }
        }

        // Fallback for offline or mock environment: generate stable user ID and demo JWT token
        val storedToken = prefs.getString(KEY_ACCESS_TOKEN, null)
        if (!storedToken.isNullOrBlank()) {
            return@withContext storedToken
        }

        var uid = prefs.getString(KEY_USER_ID, null)
        if (uid.isNullOrBlank()) {
            uid = "user_${UUID.randomUUID().hexString()}"
            prefs.edit().putString(KEY_USER_ID, uid).apply()
        }
        val fallbackToken = "demo_token_${uid}_${System.currentTimeMillis()}"
        saveSession(fallbackToken, "demo_refresh_$uid", uid, System.currentTimeMillis() + 86400_000L)
        fallbackToken
    }

    suspend fun refreshToken(): String? = withContext(Dispatchers.IO) {
        if (!supabaseConfigured) {
            return@withContext null
        }
        try {
            supabase.auth.refreshCurrentSession()
            val session = supabase.auth.currentSessionOrNull()
            if (session != null) {
                val token = session.accessToken
                val refreshToken = session.refreshToken
                val userId = session.user?.id ?: getUserId()
                val expiresAt = System.currentTimeMillis() + (session.expiresIn * 1000L)

                saveSession(token, refreshToken, userId, expiresAt)
                return@withContext token
            }
        } catch (e: Exception) {
            Log.w("SupabaseAuth", "Failed to refresh Supabase session: ${e.message}")
        }
        null
    }

    private fun saveSession(accessToken: String, refreshToken: String, userId: String, expiresAt: Long) {
        prefs.edit()
            .putString(KEY_ACCESS_TOKEN, accessToken)
            .putString(KEY_REFRESH_TOKEN, refreshToken)
            .putString(KEY_USER_ID, userId)
            .putLong(KEY_EXPIRES_AT, expiresAt)
            .apply()
    }

    private fun UUID.hexString(): String = this.toString().replace("-", "")
}
