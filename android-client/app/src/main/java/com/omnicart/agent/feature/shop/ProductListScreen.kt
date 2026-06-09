package com.omnicart.agent.feature.shop

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Storefront
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
    sessionId: String = "",
    userId: String = "",
    onProductClick: (String) -> Unit = {},
) {
    val uiState by viewModel.uiState.collectAsState()

    Column(modifier = Modifier.fillMaxSize()) {
        Surface(color = MaterialTheme.colorScheme.surface, tonalElevation = 1.dp) {
            Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Filled.Storefront, null, tint = MaterialTheme.colorScheme.primary)
                    Spacer(Modifier.width(8.dp))
                    Column(Modifier.weight(1f)) {
                        Text("精选好物", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                        Text(
                            "已为你收录 ${uiState.totalCount} 件可比价、可追溯商品",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                Spacer(Modifier.height(12.dp))
                Surface(
                    shape = RoundedCornerShape(999.dp),
                    color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.7f),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Row(Modifier.padding(horizontal = 14.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Filled.Search, null, Modifier.size(18.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                        Spacer(Modifier.width(8.dp))
                        Text(
                            "去豆仔页输入需求，获取 AI 个性化推荐",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }
        }
        Column(modifier = Modifier.fillMaxSize()) {
            ScrollableTabRow(
                selectedTabIndex = CATEGORY_OPTIONS.indexOfFirst { it.first == uiState.selectedCategory },
                edgePadding = 16.dp,
            ) {
                CATEGORY_OPTIONS.forEach { (cat, label) ->
                    Tab(selected = uiState.selectedCategory == cat, onClick = { viewModel.selectCategory(cat) },
                        text = { Text(label, style = MaterialTheme.typography.labelMedium) })
                }
            }
            when {
                uiState.isLoading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        CircularProgressIndicator()
                        Spacer(Modifier.height(12.dp))
                        Text("正在整理商品货架...", color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                uiState.error != null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(uiState.error ?: "加载失败", color = MaterialTheme.colorScheme.error)
                        Spacer(Modifier.height(8.dp))
                        TextButton(onClick = { viewModel.loadProducts() }) { Text("重试") }
                    }
                }
                else -> LazyColumn(contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    items(uiState.products, key = { it.productId }) { product ->
                        ProductCard(
                            product = product, decisionResult = null,
                            onClick = { onProductClick(product.productId) },
                            onScoreDetail = { viewModel.onProductClick(product.productId) },
                        )
                    }
                }
            }
        }

        // 评分详情弹窗
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
