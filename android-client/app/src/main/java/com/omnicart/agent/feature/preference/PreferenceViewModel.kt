package com.omnicart.agent.feature.preference

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.omnicart.agent.core.network.ApiClient
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class PreferenceUiState(
    val category: String = "",
    val budgetMax: String = "",
    val budgetMin: String = "",
    val scenario: String = "",
    val mustTags: String = "",
    val isLoading: Boolean = false,
    val saved: Boolean = false,
    val errorMessage: String? = null,
)

class PreferenceViewModel : ViewModel() {

    private val _uiState = MutableStateFlow(PreferenceUiState())
    val uiState: StateFlow<PreferenceUiState> = _uiState.asStateFlow()

    fun loadPreferences(sessionId: String) {
        _uiState.update { it.copy(isLoading = true) }
        viewModelScope.launch {
            try {
                val result = ApiClient.api.getPreferences(sessionId)
                val prefs = result["preferences"] as? Map<*, *> ?: emptyMap<String, Any?>()
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        category = prefs["category"] as? String ?: "",
                        budgetMax = prefs["budget_max"]?.toString() ?: "",
                        budgetMin = prefs["budget_min"]?.toString() ?: "",
                        scenario = prefs["scenario"] as? String ?: "",
                        mustTags = (prefs["must_tags"] as? List<*>)?.joinToString("，") ?: "",
                    )
                }
            } catch (e: Exception) {
                _uiState.update { it.copy(isLoading = false, errorMessage = e.message) }
            }
        }
    }

    fun savePreferences(sessionId: String) {
        val s = _uiState.value
        _uiState.update { it.copy(isLoading = true, errorMessage = null) }
        viewModelScope.launch {
            try {
                ApiClient.api.updatePreferences(
                    sessionId = sessionId,
                    body = mapOf(
                        "category" to s.category,
                        "budget_max" to (s.budgetMax.toDoubleOrNull()),
                        "budget_min" to (s.budgetMin.toDoubleOrNull()),
                        "scenario" to s.scenario,
                        "must_tags" to s.mustTags.split("，", ",").map { it.trim() }.filter { it.isNotBlank() },
                    ).filterValues { v -> v != null && v != "" }
                )
                _uiState.update { it.copy(isLoading = false, saved = true) }
            } catch (e: Exception) {
                _uiState.update { it.copy(isLoading = false, errorMessage = e.message) }
            }
        }
    }

    fun onCategoryChange(c: String) { _uiState.update { it.copy(category = c, saved = false) } }
    fun onBudgetMaxChange(v: String) { _uiState.update { it.copy(budgetMax = v, saved = false) } }
    fun onBudgetMinChange(v: String) { _uiState.update { it.copy(budgetMin = v, saved = false) } }
    fun onScenarioChange(v: String) { _uiState.update { it.copy(scenario = v, saved = false) } }
    fun onMustTagsChange(v: String) { _uiState.update { it.copy(mustTags = v, saved = false) } }
    fun dismissSaved() { _uiState.update { it.copy(saved = false) } }
}
