package com.omnicart.agent.feature.product

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.ExpandLess
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.QuestionAnswer
import androidx.compose.material.icons.filled.ShoppingCart
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.omnicart.agent.core.network.AddToCartRequest
import com.omnicart.agent.core.network.ApiClient
import com.omnicart.agent.core.network.ProductDetailResponse
import com.omnicart.agent.core.network.ReviewDto
import com.omnicart.agent.core.network.SkuDto
import com.omnicart.agent.feature.auth.AuthManager
import com.omnicart.agent.core.theme.*
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun ProductDetailScreen(
    productId: String,
    sessionId: String = "",
    userId: String = "",
    onBack: () -> Unit,
    onAskDouzai: (String, String) -> Unit,
) {
    var detail by remember { mutableStateOf<ProductDetailResponse?>(null) }
    var isLoading by remember { mutableStateOf(true) }
    var selectedSkuIndex by remember { mutableIntStateOf(0) }
    var faqExpanded by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val snackbar = remember { SnackbarHostState() }

    LaunchedEffect(productId) {
        isLoading = true
        detail = try {
            ApiClient.api.getProduct(productId)
        } catch (_: Exception) {
            null
        }
        isLoading = false
    }

    Scaffold(
        topBar = {
            DetailTopBar(
                title = detail?.title ?: "商品详情",
                onBack = onBack,
            )
        },
        bottomBar = {
            detail?.let { p ->
                Surface(color = Surface, tonalElevation = 6.dp, shadowElevation = 10.dp) {
                    Row(
                        Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp),
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        OutlinedButton(
                            onClick = { onAskDouzai(productId, p.title) },
                            modifier = Modifier.weight(1f),
                            shape = ButtonShape,
                        ) {
                            Icon(Icons.Default.QuestionAnswer, null, Modifier.size(18.dp))
                            Spacer(Modifier.width(6.dp))
                            Text("问豆仔")
                        }
                        Button(
                            onClick = {
                                scope.launch {
                                    try {
                                        ApiClient.api.addToCart(
                                            item = AddToCartRequest(
                                                productId = productId,
                                                skuId = p.skus.getOrNull(selectedSkuIndex)?.skuId ?: "",
                                                quantity = 1,
                                            ),
                                            userId = userId.ifBlank { AuthManager.effectiveUserId },
                                            sessionId = sessionId,
                                        )
                                        snackbar.showSnackbar("已加入购物车")
                                    } catch (e: Exception) {
                                        snackbar.showSnackbar("加购失败: ${e.message}")
                                    }
                                }
                            },
                            modifier = Modifier.weight(1f),
                            shape = ButtonShape,
                        ) {
                            Icon(Icons.Default.ShoppingCart, null, Modifier.size(18.dp))
                            Spacer(Modifier.width(6.dp))
                            Text("加购物车")
                        }
                    }
                }
            }
        },
        snackbarHost = { SnackbarHost(snackbar) },
        containerColor = Background,
    ) { padding ->
        when {
            isLoading -> Box(
                Modifier.fillMaxSize().padding(padding),
                contentAlignment = Alignment.Center,
            ) {
                CircularProgressIndicator()
            }
            detail == null -> Box(
                Modifier.fillMaxSize().padding(padding),
                contentAlignment = Alignment.Center,
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text("加载失败", color = MaterialTheme.colorScheme.error)
                    Spacer(Modifier.height(8.dp))
                    TextButton(onClick = { isLoading = true }) { Text("重试") }
                }
            }
            else -> {
                val p = detail!!
                Column(
                    Modifier
                        .fillMaxSize()
                        .padding(padding)
                        .verticalScroll(rememberScrollState()),
                ) {
                    ProductHero(p)
                    // 根据选中 SKU 计算有效价格
                    val effectivePrice = p.skus.getOrNull(selectedSkuIndex)?.let { sku ->
                        if (sku.price > 0.0) sku.price else p.price
                    } ?: p.price
                    Column(
                        Modifier.padding(horizontal = 12.dp, vertical = 10.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        ProductInfoCard(p, effectivePrice)
                        SkuSection(
                            skus = p.skus,
                            selectedIndex = selectedSkuIndex,
                            onSelect = { selectedSkuIndex = it },
                        )
                        DescriptionSection(p.marketingDescription)
                        FaqSection(
                            title = "常见问题 (${p.officialFaq.size})",
                            expanded = faqExpanded,
                            onToggle = { faqExpanded = !faqExpanded },
                            items = p.officialFaq.map { it.question to it.answer },
                        )
                        ReviewSection(p.userReviews)
                        Spacer(Modifier.height(12.dp))
                    }
                }
            }
        }
    }
}

@Composable
private fun ProductHero(product: ProductDetailResponse) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .height(220.dp)
            .background(
                Brush.verticalGradient(
                    listOf(PrimaryContainer, Background)
                )
            )
            .padding(horizontal = 16.dp, vertical = 10.dp),
        contentAlignment = Alignment.Center,
    ) {
        Surface(
            modifier = Modifier.fillMaxSize(),
            shape = RoundedCornerShape(20.dp),
            color = Surface.copy(alpha = 0.82f),
            tonalElevation = 1.dp,
        ) {
            ProductImage(
                imageUrl = product.imageUrls.firstOrNull(),
                contentDescription = product.title,
                modifier = Modifier.fillMaxSize().padding(10.dp),
                cornerRadius = 18.dp,
                contentScale = ContentScale.Fit,
            )
        }
    }
}

@Composable
private fun DetailTopBar(
    title: String,
    onBack: () -> Unit,
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = Surface,
        shadowElevation = 1.dp,
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .height(56.dp)
                .padding(horizontal = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onBack) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, "返回")
            }
            Text(
                title,
                modifier = Modifier.weight(1f),
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.width(8.dp))
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun ProductInfoCard(product: ProductDetailResponse, displayPrice: Double = product.price) {
    Surface(shape = RoundedCornerShape(16.dp), color = Surface, tonalElevation = 1.dp) {
        Column(Modifier.fillMaxWidth().padding(14.dp)) {
            Row(verticalAlignment = Alignment.Bottom) {
                Text("¥", style = MaterialTheme.typography.titleMedium, color = PriceRed, fontWeight = FontWeight.Bold)
                Text(
                    "%.2f".format(displayPrice),
                    style = MaterialTheme.typography.headlineSmall,
                    color = PriceRed,
                    fontWeight = FontWeight.Bold,
                )
                Spacer(Modifier.weight(1f))
                product.reviewSummary?.let { summary ->
                    if (summary.totalCount > 0) {
                        Surface(shape = RoundedCornerShape(999.dp), color = AiBlueContainer) {
                            Row(
                                Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Icon(Icons.Filled.Star, null, Modifier.size(14.dp), tint = Primary)
                                Spacer(Modifier.width(3.dp))
                                Text(
                                    "%.1f · ${summary.totalCount}评".format(summary.avgRating),
                                    style = MaterialTheme.typography.labelMedium,
                                    color = AiBlue,
                                    fontWeight = FontWeight.SemiBold,
                                )
                            }
                        }
                    }
                }
            }
            Spacer(Modifier.height(8.dp))
            Text(product.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(8.dp))
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                listOf(product.brand, product.category, product.subCategory).filter { it.isNotBlank() }.forEach { tag ->
                    Surface(shape = RoundedCornerShape(999.dp), color = SurfaceVariant) {
                        Text(tag, Modifier.padding(horizontal = 9.dp, vertical = 4.dp), style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
            product.reviewSummary?.let { summary ->
                if (summary.totalCount > 0) {
                    Spacer(Modifier.height(10.dp))
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        SoftTag("${summary.positiveCount} 条好评", ScoreHigh)
                        if (summary.negativeCount > 0) SoftTag("${summary.negativeCount} 条差评", ScoreLow)
                        summary.riskTags.take(4).forEach { SoftTag(it, RiskText) }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun SkuSection(
    skus: List<SkuDto>,
    selectedIndex: Int,
    onSelect: (Int) -> Unit,
) {
    if (skus.isEmpty()) return
    DetailSection(title = "选择规格") {
        FlowRow(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            skus.forEachIndexed { index, sku ->
                val label = sku.properties.entries
                    .joinToString(" · ") { "${it.key}: ${it.value}" }
                    .ifBlank { sku.skuId.ifBlank { "默认规格" } }
                FilterChip(
                    selected = index == selectedIndex,
                    onClick = { onSelect(index) },
                    label = {
                        Text(
                            label,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                            style = MaterialTheme.typography.labelMedium,
                        )
                    },
                    leadingIcon = if (index == selectedIndex) {
                        { Icon(Icons.Filled.CheckCircle, null, Modifier.size(16.dp)) }
                    } else null,
                    shape = RoundedCornerShape(12.dp),
                    modifier = Modifier.defaultMinSize(minHeight = 38.dp),
                )
            }
        }
    }
}

@Composable
private fun DescriptionSection(description: String) {
    if (description.isBlank()) return
    DetailSection(title = "商品介绍") {
        Text(description, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun FaqSection(
    title: String,
    expanded: Boolean,
    onToggle: () -> Unit,
    items: List<Pair<String, String>>,
) {
    if (items.isEmpty()) return
    DetailSection(
        title = title,
        trailing = {
            IconButton(onClick = onToggle, modifier = Modifier.size(32.dp)) {
                Icon(if (expanded) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore, null)
            }
        },
        onTitleClick = onToggle,
    ) {
        if (expanded) {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items.forEach { (question, answer) ->
                    Surface(shape = RoundedCornerShape(12.dp), color = SurfaceVariant.copy(alpha = 0.55f)) {
                        Column(Modifier.padding(12.dp)) {
                            Text("Q: $question", style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
                            Spacer(Modifier.height(4.dp))
                            Text(answer, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
        } else {
            Text("展开查看官方 FAQ、兼容性与使用建议", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun ReviewSection(reviews: List<ReviewDto>) {
    if (reviews.isEmpty()) return
    DetailSection(title = "用户评论 (${reviews.size})") {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            reviews.take(6).forEach { review ->
                Surface(shape = RoundedCornerShape(12.dp), color = SurfaceVariant.copy(alpha = 0.45f)) {
                    Column(Modifier.padding(12.dp)) {
                        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                            Text(review.nickname, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
                            Spacer(Modifier.weight(1f))
                            Text(
                                "★ ${review.rating}",
                                style = MaterialTheme.typography.labelMedium,
                                color = when {
                                    review.rating >= 4 -> ScoreHigh
                                    review.rating <= 2 -> ScoreLow
                                    else -> ScoreMedium
                                },
                                fontWeight = FontWeight.Bold,
                            )
                        }
                        Spacer(Modifier.height(4.dp))
                        Text(review.content, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}

@Composable
private fun DetailSection(
    title: String,
    trailing: @Composable (() -> Unit)? = null,
    onTitleClick: (() -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    Surface(shape = RoundedCornerShape(16.dp), color = Surface, tonalElevation = 1.dp) {
        Column(Modifier.fillMaxWidth().padding(14.dp)) {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .then(if (onTitleClick != null) Modifier.clickable { onTitleClick() } else Modifier),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                trailing?.invoke()
            }
            Spacer(Modifier.height(10.dp))
            content()
        }
    }
}

@Composable
private fun SoftTag(text: String, color: androidx.compose.ui.graphics.Color) {
    Surface(shape = RoundedCornerShape(999.dp), color = color.copy(alpha = 0.10f)) {
        Text(
            text,
            Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
            style = MaterialTheme.typography.labelSmall,
            color = color,
            fontWeight = FontWeight.SemiBold,
        )
    }
}
