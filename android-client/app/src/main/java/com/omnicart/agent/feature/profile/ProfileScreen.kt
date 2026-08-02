package com.omnicart.agent.feature.profile

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Login
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.runtime.*
import com.omnicart.agent.R
import com.omnicart.agent.core.network.UserMemoryItem

@Composable
fun ProfileScreen(
    isLoggedIn: Boolean = false,
    username: String = "",
    memories: List<UserMemoryItem> = emptyList(),
    isLoadingMemories: Boolean = false,
    onLoginClick: () -> Unit = {},
    onLogoutClick: () -> Unit = {},
    onAddressClick: () -> Unit = {},
    onPreferenceClick: () -> Unit = {},
    onOrdersClick: () -> Unit = {},
    onLoadMemories: () -> Unit = {},
    onDeleteMemory: (String) -> Unit = {},
) {
    LaunchedEffect(Unit) {
        onLoadMemories()
    }
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(
                    Brush.linearGradient(
                        listOf(
                            MaterialTheme.colorScheme.primary,
                            MaterialTheme.colorScheme.primary.copy(alpha = 0.72f),
                        )
                    )
                )
                .padding(20.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Image(
                    painter = painterResource(id = R.drawable.ic_douzai),
                    contentDescription = "头像",
                    modifier = Modifier.size(76.dp).clip(CircleShape),
                    contentScale = ContentScale.Crop,
                )
                Spacer(Modifier.width(16.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        if (isLoggedIn) username else "欢迎来到 OmniCart",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onPrimary,
                    )
                    Text(
                        if (isLoggedIn) "购物车、偏好和对话可同步" else "登录后同步购物车、地址和偏好",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.82f),
                    )
                }
                if (isLoggedIn) {
                    OutlinedButton(
                        onClick = onLogoutClick,
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.onPrimary),
                    ) {
                        Text("退出")
                    }
                } else {
                    Button(onClick = onLoginClick, colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.surface)) {
                        Icon(Icons.AutoMirrored.Filled.Login, null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("登录", color = MaterialTheme.colorScheme.primary)
                    }
                }
            }
        }

        Spacer(Modifier.height(16.dp))

        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            StatCard("AI 推荐", "证据可追溯", Modifier.weight(1f))
            StatCard("购物偏好", if (isLoggedIn) "已启用" else "待登录", Modifier.weight(1f))
        }

        Spacer(Modifier.height(12.dp))

        ProfileItem(Icons.Filled.ShoppingBag, "我的订单", "查看已结算的模拟订单", onClick = onOrdersClick)
        ProfileItem(Icons.Filled.LocationOn, "收货地址", if (isLoggedIn) "管理收货地址" else "登录后管理收货地址", onClick = onAddressClick)
        ProfileItem(Icons.Filled.Settings, "偏好设置", if (isLoggedIn) "预算、场景、标签会用于推荐" else "登录后设置购物偏好", onClick = onPreferenceClick)

        Spacer(Modifier.height(12.dp))
        Text("我的记忆", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, modifier = Modifier.padding(horizontal = 16.dp))
        Spacer(Modifier.height(4.dp))

        if (isLoadingMemories) {
            Box(Modifier.fillMaxWidth().padding(16.dp), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(modifier = Modifier.size(24.dp))
            }
        } else if (memories.isEmpty()) {
            Text("暂无记忆数据。使用推荐后系统会自动积累您的购物偏好。",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp))
        } else {
            memories.take(8).forEach { mem ->
                MemoryCard(mem, onDelete = { onDeleteMemory(mem.memoryId) })
            }
        }

        Spacer(Modifier.height(8.dp))
        ProfileItem(Icons.Filled.Info, "关于小O", "参赛版 · 基于 RAG 的多模态电商智能导购 Agent")
    }
}

@Composable
private fun StatCard(title: String, subtitle: String, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(14.dp),
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 1.dp,
    ) {
        Column(Modifier.padding(14.dp)) {
            Text(title, style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(4.dp))
            Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun ProfileItem(icon: androidx.compose.ui.graphics.vector.ImageVector, title: String, subtitle: String, onClick: () -> Unit = {}) {
    Surface(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
        shape = MaterialTheme.shapes.medium,
        onClick = onClick,
    ) {
        Row(modifier = Modifier.padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, null, modifier = Modifier.size(24.dp), tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(16.dp))
            Column {
                Text(title, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
                Text(subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun MemoryCard(mem: UserMemoryItem, onDelete: () -> Unit) {
    val typeLabel = when (mem.memoryType) {
        "budget" -> "预算"
        "brand" -> "品牌"
        "category" -> "品类"
        "scenario" -> "场景"
        "device" -> "设备"
        "negative_preference" -> "避雷"
        else -> mem.memoryType
    }
    val typeColor = when (mem.memoryType) {
        "budget" -> MaterialTheme.colorScheme.primary
        "negative_preference" -> MaterialTheme.colorScheme.error
        else -> MaterialTheme.colorScheme.secondary
    }

    Surface(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 3.dp),
        shape = RoundedCornerShape(10.dp),
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.4f),
    ) {
        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.Top) {
            Surface(
                shape = RoundedCornerShape(6.dp),
                color = typeColor.copy(alpha = 0.15f),
            ) {
                Text(typeLabel,
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                    style = MaterialTheme.typography.labelSmall,
                    fontWeight = FontWeight.Bold,
                    color = typeColor)
            }
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(mem.content.take(100), style = MaterialTheme.typography.bodySmall)
                Row {
                    Text("置信度: ${(mem.confidence * 100).toInt()}%",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.width(8.dp))
                    Text("活跃度: ${(mem.decayWeight * 100).toInt()}%",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            IconButton(onClick = onDelete, modifier = Modifier.size(32.dp)) {
                Icon(Icons.Filled.Delete, "删除", modifier = Modifier.size(18.dp),
                    tint = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}
