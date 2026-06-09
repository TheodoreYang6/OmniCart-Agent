package com.omnicart.agent.feature.cart

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.omnicart.agent.core.network.AddToCartRequest
import com.omnicart.agent.core.network.ApiClient
import com.omnicart.agent.core.network.CartItemResponse
import com.omnicart.agent.core.network.CheckoutRequest
import com.omnicart.agent.core.network.UpdateCartRequest
import com.omnicart.agent.feature.auth.AuthManager
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class CartItemUi(
    val id: String,
    val productId: String,
    val title: String,
    val brand: String,
    val price: Double,
    val imageUrl: String,
    val quantity: Int,
    val selected: Boolean,
    val skuLabel: String = "",
)

data class CartUiState(
    val items: List<CartItemUi> = emptyList(),
    val selectedCount: Int = 0,
    val totalPrice: Double = 0.0,
    val allSelected: Boolean = true,
    val isLoading: Boolean = false,
    val checkoutMessage: String? = null,
    val error: String? = null,
)

class CartViewModel : ViewModel() {
    private val _uiState = MutableStateFlow(CartUiState(isLoading = true))
    val uiState: StateFlow<CartUiState> = _uiState.asStateFlow()

    // P0-6: session/conversation context for behavior event recording
    private var sessionId: String = ""
    private var conversationId: String = ""

    fun setSessionContext(sessionId: String, conversationId: String) {
        this.sessionId = sessionId
        this.conversationId = conversationId
    }

    init {
        loadCart()
    }

    private val userId: String get() = AuthManager.effectiveUserId

    fun loadCart() {
        _uiState.update { it.copy(isLoading = true, error = null) }
        viewModelScope.launch {
            try {
                val response = ApiClient.api.getCart(
                    userId = userId, sessionId = sessionId, conversationId = conversationId)
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        items = response.items.map { it.toUi() },
                    )
                }
                updateStats()
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(isLoading = false, error = e.message ?: "加载购物车失败")
                }
            }
        }
    }

    fun toggleItem(id: String) {
        val item = _uiState.value.items.find { it.id == id } ?: return
        _uiState.update { state ->
            state.copy(items = state.items.map { if (it.id == id) it.copy(selected = !it.selected) else it })
        }
        updateStats()
        viewModelScope.launch {
            try {
                ApiClient.api.updateCartItem(id, UpdateCartRequest(selected = !item.selected),
                    userId = userId, sessionId = sessionId, conversationId = conversationId)
            } catch (e: Exception) {
                _uiState.update { it.copy(error = "操作失败: ${e.message}") }
            }
        }
    }

    fun toggleSelectAll() {
        val newVal = !_uiState.value.allSelected
        _uiState.update { state ->
            state.copy(items = state.items.map { it.copy(selected = newVal) }, allSelected = newVal)
        }
        updateStats()
        viewModelScope.launch {
            try {
                ApiClient.api.selectAllCart(selected = newVal,
                    userId = userId, sessionId = sessionId, conversationId = conversationId)
            } catch (e: Exception) {
                _uiState.update { it.copy(error = "操作失败: ${e.message}") }
            }
        }
    }

    fun increaseQty(id: String) {
        val item = _uiState.value.items.find { it.id == id } ?: return
        val newQty = item.quantity + 1
        _uiState.update { state ->
            state.copy(items = state.items.map { if (it.id == id) it.copy(quantity = newQty) else it })
        }
        updateStats()
        viewModelScope.launch {
            try {
                ApiClient.api.updateCartItem(id, UpdateCartRequest(quantity = newQty),
                    userId = userId, sessionId = sessionId, conversationId = conversationId)
            } catch (e: Exception) {
                _uiState.update { it.copy(error = "操作失败: ${e.message}") }
            }
        }
    }

    fun decreaseQty(id: String) {
        val item = _uiState.value.items.find { it.id == id } ?: return
        if (item.quantity <= 1) return
        val newQty = item.quantity - 1
        _uiState.update { state ->
            state.copy(items = state.items.map { if (it.id == id) it.copy(quantity = newQty) else it })
        }
        updateStats()
        viewModelScope.launch {
            try {
                ApiClient.api.updateCartItem(id, UpdateCartRequest(quantity = newQty),
                    userId = userId, sessionId = sessionId, conversationId = conversationId)
            } catch (e: Exception) {
                _uiState.update { it.copy(error = "操作失败: ${e.message}") }
            }
        }
    }

    fun removeItem(id: String) {
        _uiState.update { state -> state.copy(items = state.items.filter { it.id != id }) }
        updateStats()
        viewModelScope.launch {
            try {
                ApiClient.api.removeCartItem(id, userId = userId, sessionId = sessionId, conversationId = conversationId)
            } catch (e: Exception) {
                _uiState.update { it.copy(error = "删除失败: ${e.message}") }
            }
        }
    }

    fun checkout() {
        val selectedIds = _uiState.value.items.filter { it.selected }.map { it.id }
        if (selectedIds.isEmpty()) return
        viewModelScope.launch {
            try {
                val response = ApiClient.api.checkout(
                    CheckoutRequest(userId = userId, itemIds = selectedIds, sessionId = sessionId, conversationId = conversationId))
                _uiState.update { state ->
                    state.copy(
                        items = state.items.filter { !it.selected },
                        checkoutMessage = response.message,
                    )
                }
                updateStats()
            } catch (e: Exception) {
                _uiState.update { it.copy(error = e.message ?: "结算失败") }
            }
        }
    }

    fun dismissCheckoutMessage() {
        _uiState.update { it.copy(checkoutMessage = null) }
    }

    private fun updateStats() {
        val items = _uiState.value.items
        val selected = items.filter { it.selected }
        _uiState.update {
            it.copy(
                selectedCount = selected.size,
                totalPrice = selected.sumOf { item -> item.price * item.quantity },
                allSelected = items.isNotEmpty() && items.all { it.selected },
            )
        }
    }
}

private fun CartItemResponse.toUi() = CartItemUi(
    id = cartItemId,
    productId = productId,
    title = title,
    brand = brand,
    price = price,
    imageUrl = imageUrl,
    quantity = quantity,
    selected = selected,
    skuLabel = skuLabel,
)
