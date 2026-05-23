package com.omnicart.agent.feature.chat

import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Keyboard
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** 全屏语音输入覆盖层 — 仿微信语音输入体验 */
@Composable
fun VoiceInputOverlay(
    isRecording: Boolean,
    recordingSeconds: Int,
    onCancel: () -> Unit,
    onSwitchToKeyboard: () -> Unit,
) {
    if (!isRecording) return

    val infiniteTransition = rememberInfiniteTransition(label = "pulse")
    val scale by infiniteTransition.animateFloat(
        initialValue = 1f, targetValue = 1.15f,
        animationSpec = infiniteRepeatable(
            animation = tween(600, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse,
        ), label = "scale",
    )

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.Black.copy(alpha = 0.88f))
            .clickable { onCancel() },
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(24.dp),
        ) {
            Text(
                text = "请说出你想买的商品...",
                color = Color.White.copy(alpha = 0.9f),
                fontSize = 18.sp,
                fontWeight = FontWeight.Medium,
            )

            Box(
                modifier = Modifier
                    .size(120.dp)
                    .scale(scale)
                    .clip(CircleShape)
                    .background(MaterialTheme.colorScheme.error.copy(alpha = 0.7f)),
                contentAlignment = Alignment.Center,
            ) {
                Text("🎤", fontSize = 48.sp)
            }

            Text(
                text = "松开发送，点击空白取消",
                color = Color.White.copy(alpha = 0.5f),
                fontSize = 13.sp,
            )

            Spacer(Modifier.height(8.dp))

            FilledTonalButton(
                onClick = onSwitchToKeyboard,
                colors = ButtonDefaults.filledTonalButtonColors(
                    containerColor = Color.White.copy(alpha = 0.2f),
                ),
            ) {
                Icon(
                    Icons.Filled.Keyboard,
                    contentDescription = "键盘输入",
                    tint = Color.White,
                    modifier = Modifier.size(20.dp),
                )
                Spacer(Modifier.width(6.dp))
                Text("键盘输入", color = Color.White)
            }
        }
    }
}
