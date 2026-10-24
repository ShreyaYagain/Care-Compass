package com.carecompass.app.data.cache

import android.content.Context
import android.content.SharedPreferences
import com.carecompass.app.data.HistoryDetail
import com.carecompass.app.data.HistorySummary
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken

class HistoryCache(context: Context) {

    private val prefs: SharedPreferences = context.getSharedPreferences("carecompass_history_cache", Context.MODE_PRIVATE)
    private val gson = Gson()

    companion object {
        private const val KEY_HISTORY_SUMMARIES = "cached_history_summaries"
        private const val PREFIX_DETAIL = "cached_history_detail_"
    }

    fun saveHistorySummaries(items: List<HistorySummary>) {
        val json = gson.toJson(items)
        prefs.edit().putString(KEY_HISTORY_SUMMARIES, json).apply()
    }

    fun getHistorySummaries(): List<HistorySummary> {
        val json = prefs.getString(KEY_HISTORY_SUMMARIES, null) ?: return emptyList()
        return try {
            val type = object : TypeToken<List<HistorySummary>>() {}.type
            gson.fromJson(json, type) ?: emptyList()
        } catch (e: Exception) {
            emptyList()
        }
    }

    fun saveHistoryDetail(detail: HistoryDetail) {
        val json = gson.toJson(detail)
        prefs.edit().putString(PREFIX_DETAIL + detail.id, json).apply()
    }

    fun getHistoryDetail(id: String): HistoryDetail? {
        val json = prefs.getString(PREFIX_DETAIL + id, null) ?: return null
        return try {
            gson.fromJson(json, HistoryDetail::class.java)
        } catch (e: Exception) {
            null
        }
    }

    fun deleteHistory(id: String) {
        // Remove detail
        prefs.edit().remove(PREFIX_DETAIL + id).apply()
        // Update cached summaries
        val current = getHistorySummaries().filter { it.id != id }
        saveHistorySummaries(current)
    }
}
