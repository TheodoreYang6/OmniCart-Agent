package com.omnicart.agent.feature.cart

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CartScreen(
    viewModel: CartViewModel = viewModel(),
    refreshKey: Int = 0,
) {
    val uiState by viewModel.uiState.collectAsState()
    val snackbarHostState = remember { SnackbarHostState() }

    // 每次点击购物车 Tab 时刷新数据
    LaunchedEffect(refreshKey) {
        if (refreshKey > 0) viewModel.loadCart()
    }

    // 结算成功提示
    LaunchedEffect(uiState.checkoutMessage) {
        uiState.checkoutMessage?.let {
            snackbarHostState.showSnackbar(it)
            viewModel.dismissCheckoutMessage()
        }
    }

    Box(modifier = Modifier.fillMaxSize()) {
        Column(modifier = Modifier.fillMaxSize()) {
            // 顶栏
            Surface(color = MaterialTheme.colorScheme.surface, tonalElevation = 1.dp) {
                Text(
                    "购物车",
                    style = MaterialTheme.typography.titleMedium,
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
                )
            }
            Column(modifier = Modifier.fillMaxSize()) {
                when {
                    uiState.isLoading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator()
                    }
                    uiState.error != null && uiState.items.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(uiState.error ?: "加载失败", color = MaterialTheme.colorScheme.error)
                            Spacer(Modifier.height(8.dp))
                            TextButton(onClick = { viewModel.loadCart() }) { Text("重试") }
                        }
                    }
                    uiState.items.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text("🛒", style = MaterialTheme.typography.headlineLarge)
                            Spacer(Modifier.height(8.dp))
                            Text("购物车是空的", style = MaterialTheme.typography.bodyLarge, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Text("去豆仔智能让豆仔帮你推荐商品吧", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                    else -> {
                        // 全选栏
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Checkbox(
                                checked = uiState.allSelected,
                                onCheckedChange = { viewModel.toggleSelectAll() },
                            )
                            Text("全选", style = MaterialTheme.typography.bodyMedium)
                            Spacer(Modifier.weight(1f))
                            Text(
                                "合计: ¥${"%.2f".format(uiState.totalPrice)}",
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.primary,
                            )
                        }

                        LazyColumn(
                            contentPadding = PaddingValues(horizontal = 16.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp),
                            modifier = Modifier.weight(1f),
                        ) {
                            items(uiState.items, key = { it.id }) { item ->
                                Card(
                                    modifier = Modifier.fillMaxWidth(),
                                    shape = RoundedCornerShape(12.dp),
                                ) {
                                    Row(
                                        modifier = Modifier.padding(12.dp),
                                        verticalAlignment = Alignment.CenterVertically,
                                    ) {
                                        Checkbox(
                                            checked = item.selected,
                                            onCheckedChange = { viewModel.toggleItem(item.id) },
                                        )
                                        Spacer(Modifier.width(8.dp))
                                        Column(modifier = Modifier.weight(1f)) {
                                            Text(item.title, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, maxLines = 2)
                                            Text(item.brand, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                            Row(verticalAlignment = Alignment.CenterVertically) {
                                                Text("¥${"%.2f".format(item.price)}", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Bold)
                                                Spacer(Modifier.width(12.dp))
                                                IconButton(onClick = { viewModel.decreaseQty(item.id) }, modifier = Modifier.size(28.dp)) {
                                                    Text("−", style = MaterialTheme.typography.titleMedium)
                                                }
                                                Text("${item.quantity}", style = MaterialTheme.typography.bodyMedium)
                                                IconButton(onClick = { viewModel.increaseQty(item.id) }, modifier = Modifier.size(28.dp)) {
                                                    Text("+", style = MaterialTheme.typography.titleMedium)
                                                }
                                            }
                                        }
                                        IconButton(onClick = { viewModel.removeItem(item.id) }) {
                                            Icon(Icons.Filled.Delete, "删除", tint = MaterialTheme.colorScheme.error)
                                        }
                                    }
                                }
                            }
                        }

                        // 结算按钮
                        Button(
                            onClick = { viewModel.checkout() },
                            modifier = Modifier.fillMaxWidth().padding(16.dp),
                            enabled = uiState.selectedCount > 0,
                        ) {
                            Text("结算 (${uiState.selectedCount}件)")
                        }
                    }
                }
            }
        }
        SnackbarHost(
            hostState = snackbarHostState,
            modifier = Modifier.align(Alignment.BottomCenter)
        )
    }
}
