package com.omnicart.agent.feature.chat

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.omnicart.agent.core.network.ConversationItem

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ConversationListSheet(
    conversations: List<ConversationItem>,
    isLoading: Boolean,
    onSelect: (ConversationItem) -> Unit,
    onNewConversation: () -> Unit,
    onDismiss: () -> Unit,
    onDelete: ((ConversationItem) -> Unit)? = null,
) {
    var deleteTarget by remember { mutableStateOf<ConversationItem?>(null) }

    // 删除确认对话框
    deleteTarget?.let { conv ->
        AlertDialog(
            onDismissRequest = { deleteTarget = null },
            title = { Text("删除对话") },
            text = { Text("确定删除「${conv.title?.ifBlank { "新对话" } ?: "新对话"}」吗？消息不可恢复。") },
            confirmButton = {
                TextButton(onClick = {
                    onDelete?.invoke(conv)
                    deleteTarget = null
                }) { Text("删除", color = MaterialTheme.colorScheme.error) }
            },
            dismissButton = {
                TextButton(onClick = { deleteTarget = null }) { Text("取消") }
            },
        )
    }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp)
                .padding(bottom = 32.dp),
        ) {
            // 标题栏
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "聊天记录",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f),
                )
                IconButton(onClick = {
                    onNewConversation()
                    onDismiss()
                }) {
                    Icon(Icons.Filled.Add, contentDescription = "新建对话",
                        tint = MaterialTheme.colorScheme.primary)
                }
            }
            Spacer(Modifier.height(12.dp))

            when {
                isLoading -> {
                    Box(Modifier.fillMaxWidth().height(200.dp), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator()
                    }
                }
                conversations.isEmpty() -> {
                    Box(Modifier.fillMaxWidth().height(200.dp), contentAlignment = Alignment.Center) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text("暂无聊天记录", style = MaterialTheme.typography.bodyLarge,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Spacer(Modifier.height(4.dp))
                            Text("开始和小O聊天吧", style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
                else -> {
                    LazyColumn(
                        modifier = Modifier.fillMaxWidth(),
                        verticalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        items(conversations, key = { it.conversationId }) { conv ->
                            Card(
                                modifier = Modifier.fillMaxWidth(),
                                shape = RoundedCornerShape(12.dp),
                                colors = CardDefaults.cardColors(
                                    containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                                ),
                            ) {
                                Row(
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .clickable { onSelect(conv) }
                                        .padding(start = 12.dp, top = 12.dp, bottom = 12.dp, end = 4.dp),
                                    verticalAlignment = Alignment.CenterVertically,
                                ) {
                                    Column(modifier = Modifier.weight(1f)) {
                                        Text(
                                            conv.title?.ifBlank { "新对话" } ?: "新对话",
                                            style = MaterialTheme.typography.bodyMedium,
                                            fontWeight = FontWeight.SemiBold,
                                            maxLines = 1,
                                            overflow = TextOverflow.Ellipsis,
                                        )
                                        if (!conv.lastMessage.isNullOrBlank()) {
                                            Spacer(Modifier.height(4.dp))
                                            Text(
                                                conv.lastMessage,
                                                style = MaterialTheme.typography.bodySmall,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                                maxLines = 2,
                                                overflow = TextOverflow.Ellipsis,
                                            )
                                        }
                                    }
                                    if (onDelete != null) {
                                        IconButton(onClick = { deleteTarget = conv }) {
                                            Icon(
                                                Icons.Filled.Delete,
                                                contentDescription = "删除",
                                                tint = MaterialTheme.colorScheme.error.copy(alpha = 0.6f),
                                                modifier = Modifier.size(20.dp),
                                            )
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
