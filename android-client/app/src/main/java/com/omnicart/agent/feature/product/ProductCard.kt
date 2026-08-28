package com.omnicart.agent.feature.product

import androidx.compose.foundation.clickable
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AddShoppingCart
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.omnicart.agent.core.model.DecisionResult
import com.omnicart.agent.core.model.Product
import com.omnicart.agent.core.theme.*

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProductCard(
    product: Product,
    decisionResult: DecisionResult?,
    modifier: Modifier = Modifier,
    onClick: () -> Unit = {},
    onAddToCart: ((skuId: String?, skuLabel: String, skuPrice: Double) -> Unit)? = null,
    onAskAgent: (() -> Unit)? = null,
    onScoreDetail: (() -> Unit)? = null,
) {
    // SKU 选择状态
    val skus = product.skus.orEmpty()
    val initialIndex = if (skus.isNotEmpty()) 0 else -1
    var selectedSkuIndex by remember { mutableIntStateOf(initialIndex) }
    val selectedSku = skus.getOrNull(selectedSkuIndex)
    Card(
        onClick = onClick,
        modifier = modifier.fillMaxWidth(),
        shape = CardShape,
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = androidx.compose.foundation.BorderStroke(
            1.dp,
            MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.56f),
        ),
    ) {
        Row(modifier = Modifier.padding(12.dp)) {
            ProductImage(
                imageUrl = product.imageUrls.firstOrNull(),
                contentDescription = product.title,
                productId = product.productId,
                modifier = Modifier.size(width = 108.dp, height = 118.dp),
                cornerRadius = 12.dp,
            )
            Spacer(Modifier.width(12.dp))
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    if (product.brand.isNotBlank()) {
                        Surface(shape = RoundedCornerShape(6.dp), color = MaterialTheme.colorScheme.primaryContainer) {
                            Text(
                                product.brand,
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onPrimaryContainer,
                                fontWeight = FontWeight.SemiBold,
                                maxLines = 1,
                            )
                        }
                        Spacer(Modifier.width(6.dp))
                    }
                    Text(
                        categoryLabel(product.category),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                Text(
                    product.title,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                SkuPreview(product)
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    PriceLabel(price = product.price)
                }
                decisionResult?.let { dr ->
                    val lbl = dr.recommendationLevel.let {
                        when (it) {
                            "strong_recommend" -> "高度匹配"
                            "recommended" -> "较匹配"
                            "worth_considering" -> "有条件匹配"
                            "cautious" -> "有条件匹配"
                            "insufficient_evidence" -> "信息有限"
                            "not_recommended" -> "暂不建议优先"
                            else -> null
                        }
                    }
                    if (lbl != null || dr.evidenceLabel.isNotBlank()) {
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                            dr.recommendationScore?.let { score ->
                                Surface(
                                    shape = RoundedCornerShape(4.dp),
                                    color = MaterialTheme.colorScheme.primaryContainer,
                                ) {
                                    Text(
                                        "欧米指数 ${score.score}",
                                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onPrimaryContainer,
                                        fontWeight = FontWeight.SemiBold,
                                    )
                                }
                            }
                            if (lbl != null) {
                                val lc = when (dr.recommendationLevel) {
                                    "strong_recommend" -> ScoreHigh; "recommended" -> ScoreMedium
                                    "cautious" -> ScoreMedium; "not_recommended" -> ScoreLow; else -> ScoreMedium
                                }
                                Surface(shape = RoundedCornerShape(4.dp), color = lc.copy(alpha = 0.1f)) {
                                    Row(
                                        Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                                        verticalAlignment = Alignment.CenterVertically,
                                    ) {
                                        Icon(Icons.Filled.AutoAwesome, null, Modifier.size(12.dp), tint = lc)
                                        Spacer(Modifier.width(3.dp))
                                        Text(lbl,
                                        style = MaterialTheme.typography.labelSmall, color = lc, fontWeight = FontWeight.SemiBold)
                                    }
                                }
                            }
                            if (dr.evidenceLabel.isNotBlank()) {
                                Text(dr.evidenceLabel,
                                    style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                    decisionResult?.whyItFits?.takeIf { it.isNotBlank() }?.let { reason ->
                        Text(
                            text = reason,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                }
            }
        }
        // SKU 快速选择（可左右滑动）
        if (skus.size > 1) {
            HorizontalDivider(thickness = 0.5.dp, color = MaterialTheme.colorScheme.outlineVariant)
            Row(
                Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState())
                    .padding(horizontal = 12.dp, vertical = 6.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                skus.forEachIndexed { index, sku ->
                    val label = sku.properties?.entries
                        ?.joinToString(" · ") { "${it.key}:${it.value}" }
                        ?: sku.skuId.ifBlank { "默认" }
                    FilterChip(
                        selected = index == selectedSkuIndex,
                        onClick = { selectedSkuIndex = index },
                        label = {
                            Text(
                                label,
                                style = MaterialTheme.typography.labelSmall,
                                maxLines = 1,
                            )
                        },
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier.defaultMinSize(minHeight = 28.dp),
                    )
                }
            }
        }
        HorizontalDivider(thickness = 0.5.dp, color = MaterialTheme.colorScheme.outlineVariant)
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "查看依据",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.primary,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier
                        .clickable { onScoreDetail?.invoke() }
                        .padding(vertical = 8.dp, horizontal = 4.dp),
                )
                if (onAskAgent != null) {
                    OutlinedButton(
                        onClick = onAskAgent,
                        shape = RoundedCornerShape(10.dp),
                        contentPadding = PaddingValues(horizontal = 9.dp, vertical = 5.dp),
                    ) {
                        Icon(Icons.Filled.AutoAwesome, null, Modifier.size(14.dp))
                        Spacer(Modifier.width(3.dp))
                        Text("问欧米", style = MaterialTheme.typography.labelMedium)
                    }
                }
                if (onAddToCart != null) {
                    Button(
                        onClick = {
                            val sku = skus.getOrNull(selectedSkuIndex)
                            val skuId = sku?.skuId?.ifBlank { null }
                            val skuLabel = sku?.properties?.entries
                                ?.joinToString(" · ") { "${it.key}:${it.value}" }
                                ?: ""
                            val skuPrice = sku?.price ?: product.price
                            onAddToCart(skuId, skuLabel, skuPrice)
                        },
                        shape = ButtonShape,
                        contentPadding = PaddingValues(horizontal = 10.dp, vertical = 6.dp),
                    ) {
                        Icon(Icons.Filled.AddShoppingCart, null, Modifier.size(16.dp))
                        Spacer(Modifier.width(3.dp))
                        Text("加购", style = MaterialTheme.typography.labelMedium)
                    }
                }
            }
        }
    }
}

@Composable
private fun SkuPreview(product: Product) {
    val properties = product.skus
        ?.flatMap { it.properties?.entries.orEmpty() }
        ?.groupBy({ it.key }, { it.value })
        ?.mapValues { it.value.distinct().take(3) }
        .orEmpty()

    if (properties.isEmpty() && product.subCategory.isBlank()) return

    Row(
        modifier = Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (product.subCategory.isNotBlank()) {
            Text(
                product.subCategory,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
            )
        }
        properties.entries.take(2).forEach { (key, values) ->
            Text(
                "$key ${values.joinToString("/")}",
                modifier = Modifier
                    .clip(RoundedCornerShape(999.dp))
                    .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.75f))
                    .padding(horizontal = 7.dp, vertical = 2.dp),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

private fun categoryLabel(c: String) = c
