package com.omnicart.agent.feature.chat

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
import com.omnicart.agent.R
import com.omnicart.agent.core.theme.AiBlueContainer

enum class BubbleType { User, Assistant }

@Composable
fun MessageBubble(
    text: String,
    type: BubbleType,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = if (type == BubbleType.User)
            Arrangement.End
        else
            Arrangement.Start,
    ) {
        if (type == BubbleType.Assistant) {
            // 豆仔头像
            Image(
                painter = painterResource(id = R.drawable.ic_douzai),
                contentDescription = "豆仔",
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
                BubbleType.Assistant -> AiBlueContainer
            },
            modifier = Modifier.widthIn(max = 300.dp),
            tonalElevation = if (type == BubbleType.User) 0.dp else 1.dp,
        ) {
            Text(
                text = text,
                modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                style = MaterialTheme.typography.bodyMedium,
                color = if (type == BubbleType.User) {
                    MaterialTheme.colorScheme.onPrimary
                } else {
                    MaterialTheme.colorScheme.onSurface
                },
            )
        }
    }
}
