package com.omnicart.agent.feature.order

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.omnicart.agent.core.network.ApiClient
import com.omnicart.agent.core.network.OrderDto
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class OrderUiState(
    val orders: List<OrderDto> = emptyList(),
    val isLoading: Boolean = false,
    val error: String? = null,
)

class OrderViewModel : ViewModel() {
    private val _uiState = MutableStateFlow(OrderUiState(isLoading = true))
    val uiState: StateFlow<OrderUiState> = _uiState.asStateFlow()

    fun loadOrders(userId: String) {
        if (userId.isBlank()) return
        _uiState.update { it.copy(isLoading = true, error = null) }
        viewModelScope.launch {
            try {
                val resp = ApiClient.api.getOrders(userId)
                _uiState.update { it.copy(isLoading = false, orders = resp.orders) }
            } catch (e: Exception) {
                _uiState.update { it.copy(isLoading = false, error = e.message) }
            }
        }
    }
}
