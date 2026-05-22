package com.omnicart.agent.feature.chat

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp

@Composable
fun ChatInputBar(
    queryText: String,
    onQueryChange: (String) -> Unit,
    onSend: () -> Unit,
    onCameraClick: () -> Unit,
    onPlusClick: () -> Unit,
    enabled: Boolean,
    hasImage: Boolean = false,
    modifier: Modifier = Modifier,
) {
    val canSend = queryText.isNotBlank() || hasImage

    Surface(
        tonalElevation = 1.dp,
        shadowElevation = 2.dp,
        modifier = modifier,
        color = MaterialTheme.colorScheme.surface,
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // 左侧：相机按钮（扁平线条风格）
            FlatIconButton(
                icon = Icons.Filled.CameraAlt,
                onClick = onCameraClick,
                enabled = enabled,
                contentDescription = "拍照/相册",
            )

            Spacer(modifier = Modifier.width(4.dp))

            // 中间：输入框
            OutlinedTextField(
                value = queryText,
                onValueChange = onQueryChange,
                modifier = Modifier.weight(1f),
                placeholder = {
                    Text(
                        "输入购物需求...",
                        style = MaterialTheme.typography.bodyMedium,
                    )
                },
                enabled = enabled,
                maxLines = 3,
                textStyle = MaterialTheme.typography.bodyMedium,
                shape = RoundedCornerShape(24.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = MaterialTheme.colorScheme.outlineVariant,
                    unfocusedBorderColor = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.5f),
                    focusedContainerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f),
                    unfocusedContainerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.15f),
                ),
            )

            Spacer(modifier = Modifier.width(2.dp))

            // 右侧：语音按钮 + 加号 / 发送
            if (canSend) {
                // 有内容时显示发送
                FlatIconButton(
                    icon = Icons.Filled.Send,
                    onClick = onSend,
                    enabled = enabled,
                    contentDescription = "发送",
                )
            } else {
                // 无内容时显示语音 + 加号
                FlatIconButton(
                    icon = Icons.Filled.Mic,
                    onClick = { /* V2 语音功能 */ },
                    enabled = enabled,
                    contentDescription = "语音输入",
                )
                FlatIconButton(
                    icon = Icons.Filled.Add,
                    onClick = onPlusClick,
                    enabled = enabled,
                    contentDescription = "更多功能",
                )
            }
        }
    }
}

@Composable
private fun FlatIconButton(
    icon: ImageVector,
    onClick: () -> Unit,
    enabled: Boolean,
    contentDescription: String,
) {
    IconButton(onClick = onClick, enabled = enabled) {
        Icon(
            imageVector = icon,
            contentDescription = contentDescription,
            tint = if (enabled)
                MaterialTheme.colorScheme.onSurfaceVariant
            else
                MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.3f),
            modifier = Modifier.size(22.dp),
        )
    }
}
