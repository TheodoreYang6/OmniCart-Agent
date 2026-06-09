package com.omnicart.agent.feature.preference

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.omnicart.agent.core.network.ApiClient
import com.omnicart.agent.core.network.ParseRequest
import com.omnicart.agent.core.network.PreferenceEntryDto
import com.omnicart.agent.core.network.PreferenceSaveRequest
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class PreferenceUiState(
    val inputText: String = "",
    // 解析预览
    val isParsing: Boolean = false,
    val parsedEntry: PreferenceEntryDto? = null,
    val parseError: String? = null,
    // 保存
    val isSaving: Boolean = false,
    val saveMessage: String? = null,
    // 已保存条目列表
    val entries: List<PreferenceEntryDto> = emptyList(),
    val isLoadingEntries: Boolean = false,
    val entriesError: String? = null,
    // 删除
    val isDeleting: Boolean = false,
)

class PreferenceViewModel : ViewModel() {

    private val _uiState = MutableStateFlow(PreferenceUiState())
    val uiState: StateFlow<PreferenceUiState> = _uiState.asStateFlow()

    // ---- 加载列表 ----

    fun loadEntries(userId: String) {
        if (userId.isBlank()) return
        _uiState.update { it.copy(isLoadingEntries = true) }
        viewModelScope.launch {
            try {
                val resp = ApiClient.api.getPreferenceEntries(userId)
                _uiState.update { it.copy(isLoadingEntries = false, entries = resp.entries) }
            } catch (e: Exception) {
                _uiState.update { it.copy(isLoadingEntries = false, entriesError = e.message) }
            }
        }
    }

    // ---- 输入 ----

    fun onInputChange(text: String) {
        _uiState.update { it.copy(inputText = text, parsedEntry = null, parseError = null, saveMessage = null) }
    }

    // ---- 解析（预览，不存库） ----

    fun parse(userId: String) {
        val text = _uiState.value.inputText.trim()
        if (text.isBlank() || userId.isBlank()) return
        _uiState.update { it.copy(isParsing = true, parseError = null, parsedEntry = null) }
        viewModelScope.launch {
            try {
                val resp = ApiClient.api.parsePreference(ParseRequest(userId, text))
                if (resp.ok && resp.parsed != null) {
                    _uiState.update { it.copy(isParsing = false, parsedEntry = resp.parsed) }
                } else {
                    _uiState.update { it.copy(isParsing = false, parseError = resp.error ?: "解析失败") }
                }
            } catch (e: Exception) {
                _uiState.update { it.copy(isParsing = false, parseError = e.message) }
            }
        }
    }

    // ---- 保存 ----

    fun save(userId: String) {
        val text = _uiState.value.inputText.trim()
        if (text.isBlank() || userId.isBlank()) return
        _uiState.update { it.copy(isSaving = true, saveMessage = null) }
        viewModelScope.launch {
            try {
                val resp = ApiClient.api.savePreferenceEntry(PreferenceSaveRequest(userId, text))
                if (resp.ok) {
                    _uiState.update {
                        it.copy(
                            isSaving = false,
                            saveMessage = "已保存",
                            inputText = "",
                            parsedEntry = null,
                        )
                    }
                    loadEntries(userId)
                } else {
                    _uiState.update {
                        it.copy(isSaving = false, saveMessage = resp.error ?: "保存失败")
                    }
                }
            } catch (e: Exception) {
                _uiState.update { it.copy(isSaving = false, saveMessage = e.message) }
            }
        }
    }

    // ---- 删除条目 ----

    fun deleteEntry(userId: String, entryId: String) {
        if (userId.isBlank() || entryId.isBlank()) return
        _uiState.update { it.copy(isDeleting = true) }
        viewModelScope.launch {
            try {
                ApiClient.api.deletePreferenceEntry(entryId, userId)
                loadEntries(userId)
            } catch (e: Exception) {
                _uiState.update { it.copy(isDeleting = false, entriesError = e.message) }
            }
        }
    }

    // ---- 清除消息 ----

    fun dismissSaveMessage() {
        _uiState.update { it.copy(saveMessage = null) }
    }
}
