package com.omnicart.agent.feature.product

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil.compose.AsyncImage
import com.omnicart.agent.core.config.AppConfig
import com.omnicart.agent.core.model.DecisionResult
import com.omnicart.agent.core.model.Product
import com.omnicart.agent.core.theme.RiskTagBg
import com.omnicart.agent.core.theme.RiskTagText
import com.omnicart.agent.core.theme.ScoreHigh
import com.omnicart.agent.core.theme.ScoreLow
import com.omnicart.agent.core.theme.ScoreMedium

@Composable
fun ProductCard(
    product: Product,
    decisionResult: DecisionResult?,
    modifier: Modifier = Modifier,
    onClick: () -> Unit = {},
    onAddToCart: (() -> Unit)? = null,
) {
    Card(
        onClick = onClick,
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface
        )
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(modifier = Modifier.fillMaxWidth()) {
                AsyncImage(
                    model = resolveImageUrl(product.imageUrls.firstOrNull()),
                    contentDescription = product.title,
                    modifier = Modifier
                        .size(88.dp)
                        .clip(RoundedCornerShape(8.dp)),
                    contentScale = ContentScale.Crop
                )

                Spacer(modifier = Modifier.width(12.dp))

                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = product.title,
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis
                    )

                    Spacer(modifier = Modifier.height(2.dp))

                    Text(
                        text = "${product.brand} · ${categoryLabel(product.category)}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )

                    Spacer(modifier = Modifier.height(6.dp))

                    Text(
                        text = "¥${product.price}",
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.primary,
                        fontWeight = FontWeight.Bold
                    )

                    Spacer(modifier = Modifier.height(4.dp))

                    specRow(product)
                }
            }

            decisionResult?.let { result ->
                Spacer(modifier = Modifier.height(10.dp))
                HorizontalDivider(
                    thickness = 0.5.dp,
                    color = MaterialTheme.colorScheme.outlineVariant
                )
                Spacer(modifier = Modifier.height(8.dp))

                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            text = "综合评分",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        if (result.recommendationReason.isNotEmpty()) {
                            Spacer(modifier = Modifier.width(6.dp))
                            Text(
                                text = "— ${result.recommendationReason}",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                maxLines = 1,
                                overflow = TextOverflow.Ellipsis,
                                modifier = Modifier.weight(1f, fill = false)
                            )
                        }
                    }

                    Spacer(modifier = Modifier.width(8.dp))

                    val score = result.displayScore
                    val scoreColor = when {
                        score >= 8.0 -> ScoreHigh
                        score >= 6.0 -> ScoreMedium
                        else -> ScoreLow
                    }
                    Surface(
                        shape = RoundedCornerShape(6.dp),
                        color = scoreColor.copy(alpha = 0.12f)
                    ) {
                        Text(
                            text = "${result.displayScore}",
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 2.dp),
                            style = MaterialTheme.typography.titleMedium,
                            color = scoreColor,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }

                if (result.riskFactors.isNotEmpty()) {
                    Spacer(modifier = Modifier.height(6.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        result.riskFactors.forEach { risk ->
                            Surface(
                                color = RiskTagBg,
                                shape = RoundedCornerShape(4.dp)
                            ) {
                                Text(
                                    text = "⚠ $risk",
                                    modifier = Modifier.padding(
                                        horizontal = 6.dp,
                                        vertical = 2.dp
                                    ),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = RiskTagText
                                )
                            }
                        }
                    }
                }

                Spacer(modifier = Modifier.height(6.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        text = "查看详情 →",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    if (onAddToCart != null) {
                        Surface(
                            onClick = onAddToCart,
                            shape = RoundedCornerShape(8.dp),
                            color = MaterialTheme.colorScheme.primary,
                        ) {
                            Text(
                                text = "加入购物车",
                                modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
                                style = MaterialTheme.typography.labelMedium,
                                color = MaterialTheme.colorScheme.onPrimary,
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun specRow(product: Product) {
    val items = mutableListOf<String>()

    if (product.subCategory.isNotBlank()) {
        items.add(product.subCategory)
    }

    val skus = product.skus
    if (!skus.isNullOrEmpty()) {
        val prices = skus.map { it.price }
        val minP = prices.minOrNull() ?: 0.0
        val maxP = prices.maxOrNull() ?: 0.0
        if (minP < maxP) {
            items.add("¥${minP.toInt()}-¥${maxP.toInt()}")
        }
        items.add("${skus.size}个规格")
    }

    val reviews = product.ragKnowledge?.userReviews
    if (!reviews.isNullOrEmpty()) {
        val avgRating = reviews.map { it.rating }.average()
        items.add("${String.format("%.1f", avgRating)}分(${reviews.size}评)")
    }

    if (items.isNotEmpty()) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            items.take(3).forEach { item ->
                Text(
                    text = item,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

private fun categoryLabel(category: String): String = when (category) {
    "美妆护肤" -> "美妆护肤"
    "数码电子" -> "数码电子"
    "服饰运动" -> "服饰运动"
    "食品饮料" -> "食品饮料"
    else -> category
}

private fun resolveImageUrl(path: String?): String? {
    if (path.isNullOrBlank()) return null
    return if (path.startsWith("http")) path
    else AppConfig.BASE_URL.trimEnd('/') + "/" + path.trimStart('/')
}
