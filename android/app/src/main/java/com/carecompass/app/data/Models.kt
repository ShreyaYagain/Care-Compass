package com.carecompass.app.data

import com.google.gson.annotations.SerializedName

data class Location(
    @SerializedName("lat") val lat: Double,
    @SerializedName("lng") val lng: Double
)

data class ChatMessage(
    @SerializedName("role") val role: String,
    @SerializedName("text") val text: String
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
    @SerializedName("factors") val factors: Map<String, Double>? = null
)

data class EmergencyInfo(
    @SerializedName("call_numbers") val callNumbers: List<String> = listOf("112", "102"),
    @SerializedName("steps") val steps: List<String> = emptyList()
)

data class TriageRequest(
    @SerializedName("user_input") val userInput: String,
    @SerializedName("language") val language: String = "auto",
    @SerializedName("location") val location: Location? = null,
    @SerializedName("conversation_history") val conversationHistory: List<ChatMessage> = emptyList(),
    @SerializedName("patient") val patient: PatientProfile? = null
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
    @SerializedName("emergency") val emergency: EmergencyInfo? = null
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
