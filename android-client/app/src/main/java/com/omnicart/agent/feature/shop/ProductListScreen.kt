package com.omnicart.agent.feature.shop

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.omnicart.agent.feature.product.ProductCard
import com.omnicart.agent.feature.product.ProductDetailSheet

val CATEGORY_OPTIONS = listOf(
    null to "全部",
    "数码电子" to "数码电子",
    "美妆护肤" to "美妆护肤",
    "服饰运动" to "服饰运动",
    "食品饮料" to "食品饮料",
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProductListScreen(
    viewModel: ProductListViewModel = viewModel(),
) {
    val uiState by viewModel.uiState.collectAsState()

    Column(modifier = Modifier.fillMaxSize()) {
        // 顶栏
        Surface(color = MaterialTheme.colorScheme.surface, tonalElevation = 1.dp) {
            Text(
                "商品展示 · ${uiState.totalCount}件",
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
            )
        }

        Column(modifier = Modifier.fillMaxSize()) {
            // 品类筛选 Tabs
            ScrollableTabRow(
                selectedTabIndex = CATEGORY_OPTIONS.indexOfFirst { it.first == uiState.selectedCategory },
                edgePadding = 16.dp,
            ) {
                CATEGORY_OPTIONS.forEach { (cat, label) ->
                    Tab(
                        selected = uiState.selectedCategory == cat,
                        onClick = { viewModel.selectCategory(cat) },
                        text = { Text(label, style = MaterialTheme.typography.labelMedium) },
                    )
                }
            }

            when {
                uiState.isLoading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
                uiState.error != null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(uiState.error ?: "加载失败", color = MaterialTheme.colorScheme.error)
                        Spacer(Modifier.height(8.dp))
                        TextButton(onClick = { viewModel.loadProducts() }) { Text("重试") }
                    }
                }
                else -> LazyColumn(
                    contentPadding = PaddingValues(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    items(uiState.products, key = { it.productId }) { product ->
                        ProductCard(
                            product = product,
                            decisionResult = null,
                            onClick = { viewModel.onProductClick(product.productId) },
                        )
                    }
                }
            }

            // 详情弹窗
            if (uiState.selectedProduct != null) {
                ProductDetailSheet(
                    product = uiState.selectedProduct!!,
                    decisionResult = null,
                    evidenceList = uiState.selectedProduct?.ragKnowledge?.let { rk ->
                        rk.userReviews?.map { r ->
                            mapOf("source_type" to "review", "content" to r.content, "confidence" to (r.rating / 5.0))
                        } ?: emptyList()
                    } ?: emptyList(),
                    traceSteps = emptyList(),
                    harnessReport = emptyMap(),
                    onDismiss = { viewModel.onDismissDetail() },
                )
            }
        }
    }
}
