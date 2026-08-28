package com.omnicart.agent.feature.shop

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.omnicart.agent.core.model.Product
import com.omnicart.agent.core.network.ApiClient
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ProductListUiState(
    val products: List<Product> = emptyList(),
    val selectedCategory: String? = null,
    val isLoading: Boolean = false,
    val error: String? = null,
    val selectedProduct: Product? = null,
    val totalCount: Int = 0,
)

class ProductListViewModel : ViewModel() {
    private val _uiState = MutableStateFlow(ProductListUiState(isLoading = true))
    val uiState: StateFlow<ProductListUiState> = _uiState.asStateFlow()

    init { loadProducts() }

    fun loadProducts(category: String? = null) {
        _uiState.update { it.copy(isLoading = true, error = null) }
        viewModelScope.launch {
            try {
                val response = ApiClient.api.getProducts(
                    category = category,
                    page = 1,
                    pageSize = 50,
                )
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        products = response.items,
                        totalCount = response.total,
                    )
                }
            } catch (_: Exception) {
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        error = "暂时连不上欧米服务，请确认电脑端服务已启动且手机与电脑在同一 Wi‑Fi。",
                    )
                }
            }
        }
    }

    fun selectCategory(category: String?) {
        _uiState.update { it.copy(selectedCategory = category) }
        loadProducts(category)
    }

    fun onProductClick(productId: String) {
        val product = _uiState.value.products.find { it.productId == productId }
        _uiState.update { it.copy(selectedProduct = product) }
    }

    fun onDismissDetail() {
        _uiState.update { it.copy(selectedProduct = null) }
    }
}
