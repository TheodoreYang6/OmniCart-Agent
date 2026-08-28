package com.omnicart.agent.feature.chat

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp

@Composable
fun ChatInputBar(
    queryText: String,
    onQueryChange: (String) -> Unit,
    onSend: () -> Unit,
    onCameraClick: () -> Unit,
    onPlusClick: () -> Unit,
    onVoiceStart: () -> Unit,
    onVoiceEnd: () -> Unit,
    onVoiceCancel: () -> Unit,
    enabled: Boolean,
    hasImage: Boolean = false,
    isRecording: Boolean = false,
    deepThink: Boolean = false,
    onDeepThinkToggle: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val canSend = queryText.isNotBlank() || hasImage

    Surface(
        tonalElevation = 2.dp,
        shadowElevation = 8.dp,
        modifier = modifier,
        color = MaterialTheme.colorScheme.surface,
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // 深度思考收进输入框：避免与对话框并排抢占空间。
            OutlinedTextField(
                value = queryText,
                onValueChange = onQueryChange,
                modifier = Modifier.weight(1f).heightIn(min = 52.dp).padding(vertical = 2.dp),
                label = if (deepThink) ({ Text("深度思考") }) else null,
                leadingIcon = {
                    IconToggleButton(
                        checked = deepThink,
                        onCheckedChange = { onDeepThinkToggle() },
                        modifier = Modifier.size(42.dp),
                    ) {
                        Icon(
                            Icons.Filled.AutoAwesome,
                            contentDescription = if (deepThink) "关闭深度思考" else "开启深度思考",
                            tint = if (deepThink) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.size(19.dp),
                        )
                    }
                },
                placeholder = {
                    Text(
                        if (deepThink) "慢一点想得更周全，告诉欧米你的需求" else "想买什么？问问欧米",
                        style = MaterialTheme.typography.bodyMedium,
                    )
                },
                enabled = enabled,
                maxLines = 3,
                textStyle = MaterialTheme.typography.bodyMedium,
                shape = RoundedCornerShape(18.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = MaterialTheme.colorScheme.outlineVariant,
                    unfocusedBorderColor = MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.5f),
                    focusedContainerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.45f),
                    unfocusedContainerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f),
                ),
            )

            Spacer(modifier = Modifier.width(6.dp))

            // 右侧：语音按钮 + 加号 / 发送
            if (canSend) {
                // 有内容时显示发送
                FlatIconButton(
                    icon = Icons.Filled.Send,
                    onClick = onSend,
                    enabled = enabled,
                    contentDescription = "发送需求",
                    emphasized = true,
                )
            } else {
                // 无内容时显示语音 + 加号
                var pressStartTime by remember { mutableLongStateOf(0L) }
                Box(
                    modifier = Modifier
                        .size(40.dp)
                        .clip(CircleShape)
                        .background(
                            if (isRecording) MaterialTheme.colorScheme.errorContainer
                            else MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.55f)
                        )
                        .pointerInput(Unit) {
                            detectTapGestures(
                                onPress = {
                                    pressStartTime = System.currentTimeMillis()
                                    onVoiceStart()
                                    tryAwaitRelease()
                                    if (System.currentTimeMillis() - pressStartTime > 400) {
                                        onVoiceEnd()
                                    } else {
                                        onVoiceCancel()
                                    }
                                }
                            )
                        },
                    contentAlignment = Alignment.Center,
                ) {
                    Icon(
                        imageVector = Icons.Filled.Mic,
                        contentDescription = if (isRecording) "松开发送" else "长按录音",
                        tint = if (isRecording)
                            MaterialTheme.colorScheme.error
                        else
                            MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.size(22.dp),
                    )
                }
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
    emphasized: Boolean = false,
) {
    IconButton(
        onClick = onClick,
        enabled = enabled,
        modifier = Modifier
            .size(40.dp)
            .then(
                if (emphasized) Modifier
                    .clip(CircleShape)
                    .background(MaterialTheme.colorScheme.primary)
                else Modifier
            ),
    ) {
        Icon(
            imageVector = icon,
            contentDescription = contentDescription,
            tint = when {
                !enabled -> MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.3f)
                emphasized -> MaterialTheme.colorScheme.onPrimary
                else -> MaterialTheme.colorScheme.onSurfaceVariant
            },
            modifier = Modifier.size(22.dp),
        )
    }
}
