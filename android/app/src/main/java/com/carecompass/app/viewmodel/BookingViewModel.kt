package com.carecompass.app.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.carecompass.app.R
import com.carecompass.app.data.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Calendar
import java.util.Date
import java.util.Locale

enum class CareService(
    val careType: String,
    val titleEnRes: Int,
    val titleHiRes: Int,
    val titleHinglishRes: Int,
    val descEnRes: Int,
    val descHiRes: Int,
    val descHinglishRes: Int,
    val isHomeVisit: Boolean
) {
    HOME_NURSING(
        careType = "home_nursing",
        titleEnRes = R.string.service_nursing_title_en,
        titleHiRes = R.string.service_nursing_title_hi,
        titleHinglishRes = R.string.service_nursing_title_hinglish,
        descEnRes = R.string.service_nursing_desc_en,
        descHiRes = R.string.service_nursing_desc_hi,
        descHinglishRes = R.string.service_nursing_desc_hinglish,
        isHomeVisit = true
    ),
    LAB_TEST_HOME(
        careType = "lab_test_home",
        titleEnRes = R.string.service_lab_title_en,
        titleHiRes = R.string.service_lab_title_hi,
        titleHinglishRes = R.string.service_lab_title_hinglish,
        descEnRes = R.string.service_lab_desc_en,
        descHiRes = R.string.service_lab_desc_hi,
        descHinglishRes = R.string.service_lab_desc_hinglish,
        isHomeVisit = true
    ),
    TELECONSULTATION(
        careType = "teleconsultation",
        titleEnRes = R.string.service_tele_title_en,
        titleHiRes = R.string.service_tele_title_hi,
        titleHinglishRes = R.string.service_tele_title_hinglish,
        descEnRes = R.string.service_tele_desc_en,
        descHiRes = R.string.service_tele_desc_hi,
        descHinglishRes = R.string.service_tele_desc_hinglish,
        isHomeVisit = false
    );

    fun getTitle(lang: String): Int = when (lang) {
        "hi" -> titleHiRes
        "hinglish" -> titleHinglishRes
        else -> titleEnRes
    }

    fun getDesc(lang: String): Int = when (lang) {
        "hi" -> descHiRes
        "hinglish" -> descHinglishRes
        else -> descEnRes
    }

    companion object {
        fun fromCareType(careType: String?): CareService = when (careType) {
            "lab_test_home" -> LAB_TEST_HOME
            "teleconsultation" -> TELECONSULTATION
            else -> HOME_NURSING // home_nursing, paramedic_home_visit, null fallback
        }
    }
}

data class DateItem(
    val dayOffset: Int,
    val dayLabel: String,
    val dateNumber: String,
    val monthLabel: String,
    val formattedDate: String,
    val isToday: Boolean
)

data class TimeSlotItem(
    val slotKey: String,
    val displayLabel: String,
    val isPast: Boolean,
    val isBooked: Boolean
)

data class BookingUiState(
    val service: CareService? = null,
    val currentStep: Int = 1, // 1: Reason, 2: Caregivers, 3: Date & Time, 4: Confirmed
    val reason: String = "",
    val followUpQuestion: String? = null,
    val followUpOptions: List<String> = emptyList(),
    val triageResponse: TriageResponse? = null,
    val caregivers: List<MatchedCaregiver> = emptyList(),
    val selectedCaregiver: MatchedCaregiver? = null,
    val selectedDateOffset: Int = 0,
    val selectedSlot: String? = null,
    val forWhom: String = "myself", // "myself" or "someone_else"
    val userName: String = "Rohan Gupta",
    val patientName: String = "",
    val relation: String? = null, // "Papa", "Mama", "Child", "Other"
    val phone: String = "9876543210",
    val address: String = "B-402, Green Glen Layout, Outer Ring Road",
    val bookingResponse: BookingResponse? = null,
    val isLoading: Boolean = false,
    val errorMessage: String? = null,
    val isMatchedEmpty: Boolean = false
)

class BookingViewModel(
    private val repository: Repository = Repository(ApiService.create())
) : ViewModel() {

    private val _uiState = MutableStateFlow(BookingUiState())
    val uiState: StateFlow<BookingUiState> = _uiState.asStateFlow()

    fun setForWhom(target: String) {
        _uiState.value = _uiState.value.copy(
            forWhom = target,
            patientName = if (target == "myself") _uiState.value.userName else _uiState.value.patientName,
            relation = if (target == "myself") null else _uiState.value.relation
        )
    }

    fun setRelation(relation: String?) {
        _uiState.value = _uiState.value.copy(relation = relation)
    }

    fun setPatientName(name: String) {
        _uiState.value = _uiState.value.copy(patientName = name)
    }

    fun setPhone(phone: String) {
        _uiState.value = _uiState.value.copy(phone = phone)
    }

    fun setAddress(address: String) {
        _uiState.value = _uiState.value.copy(address = address)
    }

    fun openStep3ForReschedule(
        caregiver: MatchedCaregiver,
        service: CareService,
        initialPatientName: String,
        initialRelation: String?
    ) {
        val forWhom = if (initialRelation != null || (initialPatientName.isNotBlank() && initialPatientName != "Myself")) "someone_else" else "myself"
        _uiState.value = BookingUiState(
            service = service,
            currentStep = 3,
            selectedCaregiver = caregiver,
            forWhom = forWhom,
            patientName = if (forWhom == "someone_else") initialPatientName else _uiState.value.userName,
            relation = initialRelation,
            phone = _uiState.value.phone,
            address = _uiState.value.address
        )
    }

    fun selectService(service: CareService) {
        _uiState.value = BookingUiState(
            service = service,
            currentStep = 1,
            forWhom = _uiState.value.forWhom,
            userName = _uiState.value.userName,
            patientName = _uiState.value.patientName,
            relation = _uiState.value.relation,
            phone = _uiState.value.phone,
            address = _uiState.value.address
        )
    }

    fun startNewBooking() {
        _uiState.value = BookingUiState()
    }

    fun setReason(text: String) {
        _uiState.value = _uiState.value.copy(reason = text, errorMessage = null)
    }

    fun appendReason(chipText: String) {
        val current = _uiState.value.reason.trim()
        val updated = if (current.isEmpty()) {
            chipText
        } else if (current.contains(chipText, ignoreCase = true)) {
            current
        } else {
            "$current, $chipText"
        }
        _uiState.value = _uiState.value.copy(reason = updated, errorMessage = null)
    }

    fun submitReason(
        lang: String,
        location: Location?,
        onEmergency: (TriageResponse) -> Unit
    ) {
        val trimmed = _uiState.value.reason.trim()
        if (trimmed.isBlank()) {
            return
        }

        _uiState.value = _uiState.value.copy(isLoading = true, errorMessage = null)

        viewModelScope.launch {
            // The AI/ML triage decides the care type; the patient is never asked to pick a service.
            val req = TriageRequest(
                userInput = trimmed,
                language = lang,
                location = location,
                contextConsent = true
            )

            repository.triage(req).fold(
                onSuccess = { resp ->
                    val isEmergency = resp.emergency != null ||
                            resp.redFlags.isNotEmpty() ||
                            resp.careType == "emergency_112"

                    if (isEmergency) {
                        _uiState.value = _uiState.value.copy(
                            isLoading = false,
                            triageResponse = resp
                        )
                        onEmergency(resp)
                        return@fold
                    }

                    if (!resp.followUpQuestion.isNullOrBlank()) {
                        _uiState.value = _uiState.value.copy(
                            isLoading = false,
                            triageResponse = resp,
                            followUpQuestion = resp.followUpQuestion,
                            followUpOptions = resp.followUpOptions.ifEmpty { listOf("Yes", "No", "Not sure") }
                        )
                        return@fold
                    }

                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        triageResponse = resp,
                        service = CareService.fromCareType(resp.careType),
                        currentStep = 2
                    )
                    loadCaregivers(lang, location)
                },
                onFailure = { err ->
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        errorMessage = err.localizedMessage ?: "Connection error. Please try again."
                    )
                }
            )
        }
    }

    fun answerFollowUp(
        answer: String,
        lang: String,
        location: Location?,
        onEmergency: (TriageResponse) -> Unit
    ) {
        val updatedReason = "${_uiState.value.reason} ($answer)"
        _uiState.value = _uiState.value.copy(
            reason = updatedReason,
            followUpQuestion = null,
            followUpOptions = emptyList()
        )
        submitReason(lang, location, onEmergency)
    }

    fun loadCaregivers(lang: String, location: Location?) {
        val service = _uiState.value.service
        val triageResp = _uiState.value.triageResponse

        _uiState.value = _uiState.value.copy(isLoading = true, errorMessage = null)

        viewModelScope.launch {
            val matchReq = MatchRequest(
                careType = triageResp?.careType ?: service?.careType ?: "home_nursing",
                urgency = triageResp?.urgency ?: "scheduled",
                location = location,
                language = lang
            )

            repository.matchCaregivers(matchReq).fold(
                onSuccess = { matchedList ->
                    val top3 = matchedList.take(3)
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        caregivers = top3,
                        selectedCaregiver = top3.firstOrNull(),
                        isMatchedEmpty = top3.isEmpty()
                    )
                },
                onFailure = { err ->
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        errorMessage = err.localizedMessage ?: "Failed to find caregivers. Please retry."
                    )
                }
            )
        }
    }

    fun switchToTeleconsultation(lang: String, location: Location?) {
        _uiState.value = _uiState.value.copy(
            service = CareService.TELECONSULTATION,
            triageResponse = null,
            isMatchedEmpty = false,
            caregivers = emptyList(),
            selectedCaregiver = null
        )
        loadCaregivers(lang, location)
    }

    fun selectCaregiver(caregiver: MatchedCaregiver) {
        _uiState.value = _uiState.value.copy(selectedCaregiver = caregiver)
    }

    fun goToStep3() {
        if (_uiState.value.selectedCaregiver != null) {
            _uiState.value = _uiState.value.copy(currentStep = 3)
        }
    }

    fun selectDate(offset: Int) {
        _uiState.value = _uiState.value.copy(selectedDateOffset = offset, selectedSlot = null)
    }

    fun selectSlot(slot: String) {
        _uiState.value = _uiState.value.copy(selectedSlot = slot)
    }

    fun updatePatientDetails(name: String, phone: String, address: String) {
        _uiState.value = _uiState.value.copy(
            patientName = name,
            phone = phone,
            address = address
        )
    }

    fun confirmBooking(onSuccess: (BookingResponse) -> Unit) {
        val state = _uiState.value
        val caregiver = state.selectedCaregiver ?: return
        val slot = state.selectedSlot ?: return

        val dates = getNext14Days()
        val chosenDate = dates.getOrNull(state.selectedDateOffset)?.formattedDate ?: "Today"
        val fullSlotString = "$chosenDate, $slot"

        val summary = buildString {
            append("Service: ${state.service?.careType ?: "general"}")
            append(" | Reason: ${state.reason}")
            if (state.service?.isHomeVisit == true) {
                append(" | Address: ${state.address}")
            }
        }

        _uiState.value = state.copy(isLoading = true, errorMessage = null)

        viewModelScope.launch {
            val effectivePatientName = if (state.forWhom == "someone_else") {
                state.patientName.trim().ifBlank { "Someone else" }
            } else {
                "Myself"
            }
            val effectiveRelation = if (state.forWhom == "someone_else") state.relation else null

            val req = BookingRequest(
                caregiverId = caregiver.caregiverId,
                slot = fullSlotString,
                userName = state.userName.trim(),
                phone = state.phone.trim(),
                triageSummary = summary,
                patientName = effectivePatientName,
                relation = effectiveRelation,
                service = when (state.service) {
                    CareService.HOME_NURSING -> "Home nursing"
                    CareService.LAB_TEST_HOME -> "Lab test at home"
                    CareService.TELECONSULTATION -> "Teleconsultation"
                    else -> "Home nursing"
                },
                careType = state.service?.careType ?: "home_nursing",
                address = if (state.service?.isHomeVisit == true) state.address else null
            )

            repository.createBooking(req).fold(
                onSuccess = { bResp ->
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        bookingResponse = bResp,
                        currentStep = 4 // Confirmed
                    )
                    onSuccess(bResp)
                },
                onFailure = { err ->
                    _uiState.value = _uiState.value.copy(
                        isLoading = false,
                        errorMessage = err.localizedMessage ?: "Booking failed. Please try again."
                    )
                }
            )
        }
    }

    fun goBack(onExitBooking: () -> Unit) {
        val current = _uiState.value.currentStep
        when {
            current == 4 -> onExitBooking()
            current > 1 -> _uiState.value = _uiState.value.copy(currentStep = current - 1)
            else -> onExitBooking()
        }
    }

    fun reset() {
        _uiState.value = BookingUiState()
    }

    companion object {
        fun getNext14Days(): List<DateItem> {
            val list = mutableListOf<DateItem>()
            val cal = Calendar.getInstance()
            val dayFormat = SimpleDateFormat("EEE", Locale.getDefault())
            val monthFormat = SimpleDateFormat("MMM", Locale.getDefault())
            val fullFormat = SimpleDateFormat("EEE, dd MMM yyyy", Locale.getDefault())

            for (i in 0 until 14) {
                val calCopy = cal.clone() as Calendar
                calCopy.add(Calendar.DAY_OF_YEAR, i)
                val isToday = (i == 0)
                val dayLabel = when (i) {
                    0 -> "Today"
                    1 -> "Tomorrow"
                    else -> dayFormat.format(calCopy.time)
                }
                val dateNum = calCopy.get(Calendar.DAY_OF_MONTH).toString()
                val monthLabel = monthFormat.format(calCopy.time)
                val full = fullFormat.format(calCopy.time)

                list.add(
                    DateItem(
                        dayOffset = i,
                        dayLabel = dayLabel,
                        dateNumber = dateNum,
                        monthLabel = monthLabel,
                        formattedDate = full,
                        isToday = isToday
                    )
                )
            }
            return list
        }

        fun generate1HourSlots(
            freeFrom: String,
            freeUntil: String,
            isToday: Boolean
        ): List<TimeSlotItem> {
            fun parseHour(t: String): Int {
                val parts = t.split(":")
                return parts.getOrNull(0)?.trim()?.toIntOrNull() ?: 9
            }

            val startH = parseHour(freeFrom).coerceIn(0, 23)
            val endH = parseHour(freeUntil).coerceIn(startH + 1, 24)

            val currentCal = Calendar.getInstance()
            val currentHour = currentCal.get(Calendar.HOUR_OF_DAY)
            val currentMinute = currentCal.get(Calendar.MINUTE)

            val slots = mutableListOf<TimeSlotItem>()

            for (h in startH until endH) {
                val nextH = h + 1
                val h12Start = if (h == 0) 12 else if (h > 12) h - 12 else h
                val ampmStart = if (h < 12) "AM" else "PM"

                val h12End = if (nextH == 0) 12 else if (nextH > 12) nextH - 12 else nextH
                val ampmEnd = if (nextH < 12) "AM" else "PM"

                val display = String.format("%d:00 %s – %d:00 %s", h12Start, ampmStart, h12End, ampmEnd)
                val key = String.format("%02d:00-%02d:00", h, nextH)

                // If today and slot end hour is in the past, disable it
                val isPast = isToday && (h < currentHour || (h == currentHour && currentMinute > 30))
                val isBooked = (h == startH + 1) // Mock 1 booked slot for realistic slot display

                slots.add(
                    TimeSlotItem(
                        slotKey = key,
                        displayLabel = display,
                        isPast = isPast,
                        isBooked = isBooked
                    )
                )
            }

            if (slots.isEmpty()) {
                slots.add(
                    TimeSlotItem(
                        slotKey = "10:00-11:00",
                        displayLabel = "10:00 AM – 11:00 AM",
                        isPast = false,
                        isBooked = false
                    )
                )
            }

            return slots
        }
    }
}
