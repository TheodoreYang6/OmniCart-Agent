package com.omnicart.agent.feature.product

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ImageNotSupported
import androidx.compose.ui.text.font.FontWeight
import coil.compose.SubcomposeAsyncImage
import com.omnicart.agent.core.config.AppConfig
import com.omnicart.agent.core.theme.AiBlueContainer
import com.omnicart.agent.core.theme.PriceRed

@Composable
fun ProductImage(
    imageUrl: String?,
    contentDescription: String?,
    modifier: Modifier = Modifier,
    cornerRadius: Dp = 12.dp,
    contentScale: ContentScale = ContentScale.Crop,
) {
    val resolved = resolveUrl(imageUrl)
    SubcomposeAsyncImage(
        model = resolved,
        contentDescription = contentDescription,
        modifier = modifier.clip(RoundedCornerShape(cornerRadius)),
        contentScale = contentScale,
        loading = { ImagePlaceholder(modifier = Modifier.fillMaxSize()) },
        error = { ImagePlaceholder(modifier = Modifier.fillMaxSize(), isError = true) },
    )
}

@Composable
fun ImagePlaceholder(modifier: Modifier = Modifier, isError: Boolean = false) {
    Box(
        modifier = modifier.background(
            Brush.linearGradient(
                listOf(Color(0xFFFAFBFF), AiBlueContainer)
            )
        ),
        contentAlignment = Alignment.Center,
    ) {
        if (isError) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Icon(
                    imageVector = Icons.Filled.ImageNotSupported,
                    contentDescription = null,
                    tint = Color(0xFFB0B4BC),
                    modifier = Modifier.size(28.dp),
                )
                Text(
                    "暂无图片",
                    style = MaterialTheme.typography.labelSmall,
                    color = Color(0xFF8A8F99),
                    textAlign = TextAlign.Center,
                )
            }
        } else {
            CircularProgressIndicator(modifier = Modifier.size(24.dp), strokeWidth = 2.dp, color = Color(0xFFBDBDBD))
        }
    }
}

/** 价格标签 — 电商风格 ¥符号小 + 整数大 */
@Composable
fun PriceLabel(price: Double, modifier: Modifier = Modifier, textStyle: androidx.compose.ui.text.TextStyle = MaterialTheme.typography.titleMedium) {
    Text(
        text = "¥${"%.2f".format(price)}",
        style = textStyle,
        color = PriceRed,
        fontWeight = FontWeight.Bold,
        modifier = modifier,
    )
}

/** 星级评分条 */
@Composable
fun StarRating(rating: Double, reviewCount: Int = 0, modifier: Modifier = Modifier) {
    val starColor = when {
        rating >= 4.0 -> Color(0xFFFFB300)
        rating >= 3.0 -> Color(0xFFFF9800)
        else -> Color(0xFF9E9E9E)
    }
    androidx.compose.foundation.layout.Row(modifier = modifier, verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
        Text("★", style = MaterialTheme.typography.bodyMedium, color = starColor)
        Text(String.format(" %.1f", rating), style = MaterialTheme.typography.bodySmall, fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold)
        if (reviewCount > 0) {
            Text(" ($reviewCount)", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

private fun resolveUrl(path: String?): String? {
    if (path.isNullOrBlank()) return null
    return if (path.startsWith("http")) path else AppConfig.BASE_URL.trimEnd('/') + "/" + path.trimStart('/')
}
