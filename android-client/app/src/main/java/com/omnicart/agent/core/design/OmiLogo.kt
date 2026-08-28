package com.omnicart.agent.core.design

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.omnicart.agent.R

/** 根据欧米应用内主题选取品牌资源，而不是读取系统主题。 */
@Composable
fun omiLogoResource(): Int = if (MaterialTheme.colorScheme.background.luminance() < 0.5f) {
    R.drawable.omi_logo_dark
} else {
    R.drawable.omi_logo_light
}

/** Shared brand mark. */
@Composable
fun OmiLogo(
    size: Dp,
    modifier: Modifier = Modifier,
    contentDescription: String? = null,
) {
    Surface(
        modifier = modifier
            .size(size)
            .clip(RoundedCornerShape(size * 0.28f)),
        shape = RoundedCornerShape(size * 0.28f),
        color = MaterialTheme.colorScheme.surface,
        shadowElevation = 0.dp,
    ) {
        Box(Modifier.fillMaxSize().padding(1.dp)) {
            Image(
                painter = painterResource(omiLogoResource()),
                contentDescription = contentDescription,
                modifier = Modifier.fillMaxSize(),
                contentScale = ContentScale.Crop,
            )
        }
    }
}
