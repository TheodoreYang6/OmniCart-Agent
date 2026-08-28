package com.omnicart.agent.feature.chat

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.slideInHorizontally
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import com.omnicart.agent.core.design.omiLogoResource

enum class BubbleType { User, Assistant }

@Composable
fun MessageBubble(
    text: String,
    type: BubbleType,
    modifier: Modifier = Modifier,
    visible: Boolean = true,
    animationDelay: Int = 0,
) {
    AnimatedVisibility(
        visible = visible,
        enter = slideInHorizontally(
            initialOffsetX = { if (type == BubbleType.User) it / 4 else -it / 4 }
        ) + fadeIn(),
    ) {
        Row(
            modifier = modifier.fillMaxWidth(),
            horizontalArrangement = if (type == BubbleType.User)
                Arrangement.End
            else
                Arrangement.Start,
        ) {
            if (type == BubbleType.Assistant) {
                Image(
                    painter = painterResource(id = omiLogoResource()),
                    contentDescription = "欧米",
                    modifier = Modifier
                        .size(28.dp)
                        .clip(RoundedCornerShape(14.dp)),
                    contentScale = ContentScale.Crop,
                )
                Spacer(modifier = Modifier.width(8.dp))
            }

            Surface(
                shape = when (type) {
                    BubbleType.User -> RoundedCornerShape(16.dp, 4.dp, 16.dp, 16.dp)
                    BubbleType.Assistant -> RoundedCornerShape(4.dp, 16.dp, 16.dp, 16.dp)
                },
                color = when (type) {
                    BubbleType.User -> MaterialTheme.colorScheme.primary
                    // Do not use the light-theme AI swatch here: in dark mode it
                    // produced a nearly white bubble with nearly white text.
                    BubbleType.Assistant -> MaterialTheme.colorScheme.primaryContainer
                },
                modifier = Modifier.widthIn(max = 360.dp),
                tonalElevation = if (type == BubbleType.User) 0.dp else 1.dp,
            ) {
                Text(
                    text = text,
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (type == BubbleType.User) {
                        MaterialTheme.colorScheme.onPrimary
                    } else {
                        MaterialTheme.colorScheme.onPrimaryContainer
                    },
                )
            }
        }
    }
}
