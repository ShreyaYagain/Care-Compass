package com.carecompass.app.data

import com.google.gson.annotations.SerializedName

data class Location(
    @SerializedName("lat") val lat: Double,
    @SerializedName("lng") val lng: Double
)

data class ChatMessage(
    @SerializedName("role") val role: String,
    @SerializedName("content") val content: String? = null,
    @SerializedName("text") val text: String? = null
)

data class PatientProfile(
    @SerializedName("relation") val relation: String? = null,
    @SerializedName("age") val age: Int? = null,
    @SerializedName("sex") val sex: String? = null,
    @SerializedName("conditions") val conditions: List<String> = emptyList(),
    @SerializedName("pregnant") val pregnant: Boolean = false
)

data class MatchedCaregiver(
    @SerializedName("caregiver_id") val caregiverId: String,
    @SerializedName("score") val score: Double,
    @SerializedName("reason") val reason: String,
    @SerializedName("factors") val factors: Map<String, Double>? = null,
    @SerializedName("name") val name: String? = null,
    @SerializedName("role") val role: String? = null,
    @SerializedName("qualification") val qualification: String? = null,
    @SerializedName("languages") val languages: List<String> = emptyList(),
    @SerializedName("rating") val rating: Double? = null,
    @SerializedName("free_from") val freeFrom: String? = null,
    @SerializedName("free_until") val freeUntil: String? = null,
    @SerializedName("distance_km") val distanceKm: Double? = null
)

data class EmergencyInfo(
    @SerializedName("call_numbers") val callNumbers: List<String> = listOf("112", "102"),
    @SerializedName("steps") val steps: List<String> = emptyList()
)

data class ContextUsedInfo(
    @SerializedName("season") val season: String? = null,
    @SerializedName("weather") val weather: String? = null,
    @SerializedName("aqi") val aqi: Double? = null,
    @SerializedName("tags") val tags: List<String> = emptyList(),
    @SerializedName("reason") val reason: String? = null
)

data class TriageRequest(
    @SerializedName("user_input") val userInput: String,
    @SerializedName("language") val language: String = "auto",
    @SerializedName("location") val location: Location? = null,
    @SerializedName("conversation_history") val conversationHistory: List<ChatMessage> = emptyList(),
    @SerializedName("patient") val patient: PatientProfile? = null,
    @SerializedName("client_time") val clientTime: String? = null,
    @SerializedName("context_consent") val contextConsent: Boolean = true
)

data class TriageResponse(
    @SerializedName("follow_up_question") val followUpQuestion: String? = null,
    @SerializedName("follow_up_options") val followUpOptions: List<String> = emptyList(),
    @SerializedName("care_type") val careType: String? = null,
    @SerializedName("urgency") val urgency: String? = null,
    @SerializedName("red_flags") val redFlags: List<String> = emptyList(),
    @SerializedName("reasoning") val reasoning: String? = null,
    @SerializedName("confidence") val confidence: Double? = null,
    @SerializedName("matched_caregivers") val matchedCaregivers: List<MatchedCaregiver> = emptyList(),
    @SerializedName("emergency_steps") val emergencySteps: List<String> = emptyList(),
    @SerializedName("emergency") val emergency: EmergencyInfo? = null,
    @SerializedName("context_used") val contextUsed: ContextUsedInfo? = null
)

data class CaregiverProfile(
    @SerializedName("id") val id: String,
    @SerializedName("name") val name: String,
    @SerializedName("role") val role: String,
    @SerializedName("specialty") val specialty: String? = null,
    @SerializedName("skills") val skills: List<String> = emptyList(),
    @SerializedName("lat") val lat: Double,
    @SerializedName("lng") val lng: Double,
    @SerializedName("languages") val languages: List<String> = emptyList(),
    @SerializedName("availability_slots") val availabilitySlots: List<String> = emptyList(),
    @SerializedName("rating") val rating: Double = 4.5,
    @SerializedName("review_count") val reviewCount: Int = 10,
    @SerializedName("home_visit") val homeVisit: Boolean = true
)

data class BookingRequest(
    @SerializedName("caregiver_id") val caregiverId: String,
    @SerializedName("slot") val slot: String,
    @SerializedName("user_name") val userName: String,
    @SerializedName("phone") val phone: String,
    @SerializedName("triage_summary") val triageSummary: String? = null
)

data class BookingResponse(
    @SerializedName("booking_id") val bookingId: String,
    @SerializedName("status") val status: String,
    @SerializedName("eta") val eta: String? = null,
    @SerializedName("caregiver_id") val caregiverId: String,
    @SerializedName("slot") val slot: String,
    @SerializedName("user_name") val userName: String,
    @SerializedName("phone") val phone: String
)

data class TranscribeResponse(
    @SerializedName("text") val text: String = "",
    @SerializedName("language") val language: String = "en"
)
