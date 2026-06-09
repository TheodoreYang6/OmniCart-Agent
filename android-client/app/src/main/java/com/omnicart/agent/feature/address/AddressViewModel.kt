package com.omnicart.agent.feature.address

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.omnicart.agent.core.network.AddressCreateRequest
import com.omnicart.agent.core.network.AddressItem
import com.omnicart.agent.core.network.AddressUpdateRequest
import com.omnicart.agent.core.network.ApiClient
import com.omnicart.agent.feature.auth.AuthManager
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class AddressUiState(
    val addresses: List<AddressItem> = emptyList(),
    val isLoading: Boolean = false,
    val errorMessage: String? = null,
    val editingAddress: AddressItem? = null, // 非 null 时显示编辑对话框
    val showAddDialog: Boolean = false,
)

class AddressViewModel : ViewModel() {

    private val _uiState = MutableStateFlow(AddressUiState())
    val uiState: StateFlow<AddressUiState> = _uiState.asStateFlow()

    fun loadAddresses() {
        _uiState.update { it.copy(isLoading = true) }
        viewModelScope.launch {
            try {
                val result = ApiClient.api.getAddresses(userId = AuthManager.effectiveUserId)
                _uiState.update { it.copy(isLoading = false, addresses = result.addresses) }
            } catch (e: Exception) {
                _uiState.update { it.copy(isLoading = false, errorMessage = "加载失败: ${e.message}") }
            }
        }
    }

    fun showAddDialog() {
        _uiState.update { it.copy(showAddDialog = true) }
    }

    fun dismissAddDialog() {
        _uiState.update { it.copy(showAddDialog = false) }
    }

    fun startEdit(address: AddressItem) {
        _uiState.update { it.copy(editingAddress = address) }
    }

    fun dismissEdit() {
        _uiState.update { it.copy(editingAddress = null) }
    }

    fun saveAddress(name: String, phone: String, province: String, city: String,
                    district: String, detail: String, isDefault: Boolean, editId: String? = null) {
        if (name.isBlank() || phone.isBlank()) {
            _uiState.update { it.copy(errorMessage = "请填写姓名和电话") }
            return
        }
        _uiState.update { it.copy(isLoading = true, errorMessage = null) }
        viewModelScope.launch {
            try {
                if (editId != null) {
                    ApiClient.api.updateAddress(editId, AddressUpdateRequest(
                        name = name, phone = phone, province = province, city = city,
                        district = district, detail = detail, isDefault = isDefault,
                    ), userId = AuthManager.effectiveUserId)
                } else {
                    ApiClient.api.createAddress(AddressCreateRequest(
                        name = name, phone = phone, province = province, city = city,
                        district = district, detail = detail, isDefault = isDefault,
                    ), userId = AuthManager.effectiveUserId)
                }
                _uiState.update { it.copy(showAddDialog = false, editingAddress = null) }
                loadAddresses()
            } catch (e: Exception) {
                _uiState.update { it.copy(isLoading = false, errorMessage = "保存失败: ${e.message}") }
            }
        }
    }

    fun deleteAddress(addressId: String) {
        viewModelScope.launch {
            try {
                ApiClient.api.deleteAddress(addressId, userId = AuthManager.effectiveUserId)
                loadAddresses()
            } catch (e: Exception) {
                _uiState.update { it.copy(errorMessage = "删除失败: ${e.message}") }
            }
        }
    }

    fun clearError() {
        _uiState.update { it.copy(errorMessage = null) }
    }
}
