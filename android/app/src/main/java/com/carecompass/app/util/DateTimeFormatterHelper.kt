package com.carecompass.app.util

import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.ZonedDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

object DateTimeFormatterHelper {

    private val kolkataZoneId: ZoneId = try {
        ZoneId.systemDefault()
    } catch (e: Exception) {
        ZoneId.of("Asia/Kolkata")
    }

    /**
     * Parse ISO-8601 string (e.g. 2026-10-24T10:30:00Z) to ZonedDateTime in device zone
     */
    fun parseIsoToZoned(isoString: String): ZonedDateTime? {
        return try {
            val instant = Instant.parse(isoString)
            instant.atZone(kolkataZoneId)
        } catch (e: Exception) {
            try {
                val odt = OffsetDateTime.parse(isoString)
                odt.atZoneSameInstant(kolkataZoneId)
            } catch (e2: Exception) {
                null
            }
        }
    }

    /**
     * Format a session date/time for History list (e.g. "Today, 3:40 PM", "Yesterday, 8:15 PM", "20 Oct, 9:00 AM")
     */
    fun formatHistoryTime(isoString: String, lang: String = "en"): String {
        val zdt = parseIsoToZoned(isoString)
        if (zdt != null) {
            val now = ZonedDateTime.now(kolkataZoneId)
            val isToday = zdt.toLocalDate() == now.toLocalDate()
            val isYesterday = zdt.toLocalDate() == now.toLocalDate().minusDays(1)

            val timePattern = DateTimeFormatter.ofPattern("h:mm a", Locale.ENGLISH)
            val formattedTime = zdt.format(timePattern)

            return when {
                isToday -> when (lang) {
                    "hi" -> "आज, $formattedTime"
                    "hinglish" -> "Today, $formattedTime"
                    else -> "Today, $formattedTime"
                }
                isYesterday -> when (lang) {
                    "hi" -> "कल, $formattedTime"
                    "hinglish" -> "Kal, $formattedTime"
                    else -> "Yesterday, $formattedTime"
                }
                else -> {
                    val datePattern = DateTimeFormatter.ofPattern("d MMM, h:mm a", Locale.ENGLISH)
                    zdt.format(datePattern)
                }
            }
        }

        // Fallback for non-ISO or parse error
        return isoString
    }

    /**
     * Format booking date/time: e.g. "Sat, 24 Oct 2026 - 4:00 PM to 5:00 PM"
     */
    fun formatBookingDateRange(startIso: String, endIso: String): String {
        val startZdt = parseIsoToZoned(startIso)
        val endZdt = parseIsoToZoned(endIso)

        if (startZdt != null && endZdt != null) {
            val datePart = startZdt.format(DateTimeFormatter.ofPattern("EEE, d MMM yyyy", Locale.ENGLISH))
            val startTimePart = startZdt.format(DateTimeFormatter.ofPattern("h:mm a", Locale.ENGLISH))
            val endTimePart = endZdt.format(DateTimeFormatter.ofPattern("h:mm a", Locale.ENGLISH))
            return "$datePart - $startTimePart to $endTimePart"
        }

        return "$startIso to $endIso"
    }

    /**
     * Returns "Today", "Tomorrow", or null
     */
    fun getDayBadge(startIso: String, lang: String = "en"): String? {
        val startZdt = parseIsoToZoned(startIso) ?: return null
        val now = ZonedDateTime.now(kolkataZoneId)
        val isToday = startZdt.toLocalDate() == now.toLocalDate()
        val isTomorrow = startZdt.toLocalDate() == now.toLocalDate().plusDays(1)

        return when {
            isToday -> when (lang) {
                "hi" -> "आज"
                "hinglish" -> "Today"
                else -> "Today"
            }
            isTomorrow -> when (lang) {
                "hi" -> "कल"
                "hinglish" -> "Tomorrow"
                else -> "Tomorrow"
            }
            else -> null
        }
    }

    /**
     * Returns true if current time is within 15 minutes before the start time, or during the call
     */
    fun isWithin15MinutesOfStart(startIso: String, endIso: String): Boolean {
        val startZdt = parseIsoToZoned(startIso) ?: return false
        val endZdt = parseIsoToZoned(endIso) ?: return false
        val now = ZonedDateTime.now(kolkataZoneId)
        val fifteenMinsBefore = startZdt.minusMinutes(15)
        return now.isAfter(fifteenMinsBefore) && now.isBefore(endZdt)
    }

    /**
     * Checks if booking is past
     */
    fun isPastBooking(endIso: String): Boolean {
        val endZdt = parseIsoToZoned(endIso) ?: return false
        val now = ZonedDateTime.now(kolkataZoneId)
        return now.isAfter(endZdt)
    }

    /**
     * Builds an ISO-8601 timestamp (yyyy-MM-dd'T'HH:mm:ss'Z') for a booking slot.
     * Uses the device's local wall-clock time so it lines up with the caregiver's
     * local free window on the backend.
     */
    fun buildBookingIso(dayOffset: Int, hour: Int, minute: Int, plusMinutes: Int = 0): String {
        val zdt = ZonedDateTime.now(kolkataZoneId)
            .plusDays(dayOffset.toLong())
            .withHour(hour)
            .withMinute(minute)
            .withSecond(0)
            .withNano(0)
            .plusMinutes(plusMinutes.toLong())
        return zdt.format(DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss'Z'"))
    }
}
