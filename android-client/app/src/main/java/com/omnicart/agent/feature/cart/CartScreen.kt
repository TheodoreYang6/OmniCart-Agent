package com.omnicart.agent.feature.cart

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.background
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.LocalMall
import androidx.compose.material.icons.filled.Remove
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.omnicart.agent.core.theme.*
import com.omnicart.agent.feature.product.ProductImage
import com.omnicart.agent.core.design.OmiLogo

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CartScreen(
    viewModel: CartViewModel = viewModel(),
    refreshKey: Int = 0, sessionId: String = "", conversationId: String = "",
) {
    LaunchedEffect(sessionId, conversationId) { viewModel.setSessionContext(sessionId, conversationId) }
    val uiState by viewModel.uiState.collectAsState()
    val snackbar = remember { SnackbarHostState() }
    LaunchedEffect(refreshKey) { if (refreshKey > 0) viewModel.loadCart() }
    LaunchedEffect(uiState.checkoutMessage) { uiState.checkoutMessage?.let { snackbar.showSnackbar(it); viewModel.dismissCheckoutMessage() } }

    Box(modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        Column(modifier = Modifier.fillMaxSize()) {
        Surface(color = MaterialTheme.colorScheme.surface.copy(alpha = 0.96f), tonalElevation = 0.dp) {
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 14.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                OmiLogo(size = 40.dp, contentDescription = "欧米")
                Spacer(Modifier.width(8.dp))
                Column {
                    Text("购物车", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    Text(
                        if (uiState.items.isNotEmpty()) "${uiState.items.size} 件商品，慢慢比较再决定" else "把心动好物先放进来，慢慢挑",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
        when {
            uiState.isLoading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            uiState.error != null && uiState.items.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(28.dp)) {
                    Icon(Icons.Filled.LocalMall, null, Modifier.size(54.dp), tint = MaterialTheme.colorScheme.primary.copy(alpha = 0.7f))
                    Spacer(Modifier.height(12.dp))
                    Text(uiState.error ?: "暂时无法使用购物车", style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.height(6.dp))
                    Text("登录后，欧米会为你保留加购和订单进度", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            uiState.items.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(Icons.Filled.LocalMall, null, Modifier.size(54.dp), tint = MaterialTheme.colorScheme.primary.copy(alpha = 0.7f))
                    Spacer(Modifier.height(12.dp))
                    Text("购物车还是空的", style = MaterialTheme.typography.titleMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.height(4.dp))
                    Text("去逛逛，或让欧米帮你找找", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            else -> {
                Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = uiState.allSelected, onCheckedChange = { viewModel.toggleSelectAll() })
                    Text("全选", style = MaterialTheme.typography.bodyMedium)
                    Spacer(Modifier.weight(1f))
                    Text("合计 ¥${"%.2f".format(uiState.totalPrice)}", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = PriceRed)
                }
                LazyColumn(contentPadding = PaddingValues(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.weight(1f)) {
                    items(uiState.items, key = { it.id }) { item ->
                        Card(Modifier.fillMaxWidth(), shape = CardShape, colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface), elevation = CardDefaults.cardElevation(defaultElevation = CardElevation)) {
                            Row(Modifier.padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                                Checkbox(checked = item.selected, onCheckedChange = { viewModel.toggleItem(item.id) })
                                Spacer(Modifier.width(8.dp))
                                ProductImage(
                                    imageUrl = item.imageUrl,
                                    contentDescription = item.title,
                                    productId = item.productId,
                                    modifier = Modifier.size(76.dp),
                                    cornerRadius = 10.dp,
                                )
                                Spacer(Modifier.width(10.dp))
                                Column(Modifier.weight(1f)) {
                                    Text(item.title, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold, maxLines = 2)
                                    Text(item.brand, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                    if (item.skuLabel.isNotBlank()) {
                                        Text(
                                            item.skuLabel,
                                            style = MaterialTheme.typography.labelSmall,
                                            color = MaterialTheme.colorScheme.primary,
                                            maxLines = 1,
                                        )
                                    }
                                    Spacer(Modifier.height(4.dp))
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Text("¥${"%.2f".format(item.price)}", style = MaterialTheme.typography.titleSmall, color = PriceRed, fontWeight = FontWeight.Bold)
                                        Spacer(Modifier.weight(1f))
                                        Surface(shape = RoundedCornerShape(999.dp), color = MaterialTheme.colorScheme.surfaceVariant) {
                                            Row(verticalAlignment = Alignment.CenterVertically) {
                                                IconButton(onClick = { viewModel.decreaseQty(item.id) }, modifier = Modifier.size(36.dp)) {
                                                    Icon(Icons.Filled.Remove, null, Modifier.size(18.dp))
                                                }
                                                Text("${item.quantity}", style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
                                                IconButton(onClick = { viewModel.increaseQty(item.id) }, modifier = Modifier.size(36.dp)) {
                                                    Icon(Icons.Filled.Add, null, Modifier.size(18.dp))
                                                }
                                            }
                                        }
                                    }
                                }
                                IconButton(onClick = { viewModel.removeItem(item.id) }) { Icon(Icons.Filled.Delete, "删除", tint = MaterialTheme.colorScheme.error) }
                            }
                        }
                    }
                }
                Surface(color = MaterialTheme.colorScheme.surface, tonalElevation = 4.dp) {
                    Row(
                        Modifier.fillMaxWidth().padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text("已选择 ${uiState.selectedCount} 件", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Text("¥${"%.2f".format(uiState.totalPrice)}", style = MaterialTheme.typography.titleLarge, color = PriceRed, fontWeight = FontWeight.Bold)
                        }
                        Button(onClick = { viewModel.checkout() }, enabled = uiState.selectedCount > 0, shape = ButtonShape) {
                            Text("去结算", style = MaterialTheme.typography.titleSmall)
                        }
                    }
                }
            }
        }
        }
        SnackbarHost(hostState = snackbar, modifier = Modifier.align(Alignment.BottomCenter))
    }
}
