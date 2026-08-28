package com.omnicart.agent.feature.profile

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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.runtime.*
import android.widget.Toast
import com.omnicart.agent.core.config.ServerConfig
import com.omnicart.agent.core.network.UserMemoryItem
import com.omnicart.agent.core.design.OmiLogo

@Composable
fun ProfileScreen(
    isLoggedIn: Boolean = false,
    username: String = "",
    isDarkTheme: Boolean = false,
    memories: List<UserMemoryItem> = emptyList(),
    isLoadingMemories: Boolean = false,
    onLoginClick: () -> Unit = {},
    onLogoutClick: () -> Unit = {},
    onAddressClick: () -> Unit = {},
    onPreferenceClick: () -> Unit = {},
    onOrdersClick: () -> Unit = {},
    onLoadMemories: () -> Unit = {},
    onDeleteMemory: (String) -> Unit = {},
    onDarkThemeChange: (Boolean) -> Unit = {},
) {
    LaunchedEffect(Unit) {
        onLoadMemories()
    }
    val context = LocalContext.current
    var showServerDialog by remember { mutableStateOf(false) }
    var serverInput by remember { mutableStateOf(ServerConfig.current()) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .verticalScroll(rememberScrollState())
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .background(
                    Brush.linearGradient(
                        listOf(
                            MaterialTheme.colorScheme.primaryContainer,
                            MaterialTheme.colorScheme.surfaceVariant,
                        )
                    )
                )
                .padding(20.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                OmiLogo(size = 72.dp, contentDescription = "欧米")
                Spacer(Modifier.width(16.dp))
                Column(Modifier.weight(1f)) {
                    Text(
                        if (isLoggedIn) username else "你好，我是欧米",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.onPrimaryContainer,
                    )
                    Text(
                        if (isLoggedIn) "欧米会结合你的偏好，推荐更适合的商品" else "登录后，欧米会更懂你的购物偏好",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.76f),
                    )
                }
                if (isLoggedIn) {
                    OutlinedButton(
                        onClick = onLogoutClick,
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.primary),
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
            StatCard("懂你偏好", if (isLoggedIn) "正在为你生效" else "登录后开启", Modifier.weight(1f))
            StatCard("购物清单", if (isLoggedIn) "随时查看和管理" else "登录后同步", Modifier.weight(1f))
        }

        Spacer(Modifier.height(12.dp))

        ProfileItem(Icons.Filled.ShoppingBag, "我的订单", "查看已下单的商品", onClick = onOrdersClick)
        ProfileItem(Icons.Filled.LocationOn, "收货地址", if (isLoggedIn) "用于给出更贴近你的建议" else "登录后管理常用地址", onClick = onAddressClick)
        ProfileItem(Icons.Filled.Settings, "偏好设置", if (isLoggedIn) "预算、场景与品牌偏好正在生效" else "登录后建立你的购物偏好", onClick = onPreferenceClick)
        ThemeToggleItem(isDarkTheme = isDarkTheme, onDarkThemeChange = onDarkThemeChange)

        Spacer(Modifier.height(12.dp))
        Text("欧米记住的偏好", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold, modifier = Modifier.padding(horizontal = 16.dp))
        Spacer(Modifier.height(4.dp))

        if (isLoadingMemories) {
            Box(Modifier.fillMaxWidth().padding(16.dp), contentAlignment = Alignment.Center) {
                CircularProgressIndicator(modifier = Modifier.size(24.dp))
            }
        } else if (memories.isEmpty()) {
            Text("还没有可用偏好。多和欧米聊几次，它会逐步记住你的取舍。",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp))
        } else {
            memories.take(8).forEach { mem ->
                MemoryCard(mem, onDelete = { onDeleteMemory(mem.memoryId) })
            }
        }

        Spacer(Modifier.height(8.dp))
        ProfileItem(
            Icons.Filled.Cloud,
            "服务器地址",
            ServerConfig.current(),
            onClick = {
                serverInput = ServerConfig.current()
                showServerDialog = true
            },
        )
        ProfileItem(Icons.Filled.Info, "关于欧米", "你的购物智能体")
    }

    if (showServerDialog) {
        AlertDialog(
            onDismissRequest = { showServerDialog = false },
            title = { Text("设置服务器地址") },
            text = {
                Column {
                    Text(
                        "USB 调试时保持默认 127.0.0.1:8006（Android Studio 会通过 adb reverse 连到电脑）。只有未连接 USB 时，才填写电脑的局域网 IP。",
                        style = MaterialTheme.typography.bodySmall,
                    )
                    Spacer(Modifier.height(8.dp))
                    OutlinedTextField(
                        value = serverInput,
                        onValueChange = { serverInput = it },
                        singleLine = true,
                        placeholder = { Text("http://127.0.0.1:8006/") },
                    )
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    ServerConfig.save(context, serverInput)
                    Toast.makeText(context, "已保存，重新操作即可生效", Toast.LENGTH_SHORT).show()
                    showServerDialog = false
                }) { Text("保存") }
            },
            dismissButton = {
                TextButton(onClick = { showServerDialog = false }) { Text("取消") }
            },
        )
    }
}

@Composable
private fun ThemeToggleItem(
    isDarkTheme: Boolean,
    onDarkThemeChange: (Boolean) -> Unit,
) {
    Surface(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
        shape = RoundedCornerShape(18.dp),
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 0.dp,
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                imageVector = if (isDarkTheme) Icons.Filled.DarkMode else Icons.Filled.LightMode,
                contentDescription = null,
                modifier = Modifier.size(24.dp),
                tint = MaterialTheme.colorScheme.primary,
            )
            Spacer(Modifier.width(16.dp))
            Column(Modifier.weight(1f)) {
                Text("深色模式", style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
                Text(
                    if (isDarkTheme) "已开启，夜间浏览更舒适" else "关闭后使用清爽的浅色界面",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Switch(checked = isDarkTheme, onCheckedChange = onDarkThemeChange)
        }
    }
}

@Composable
private fun StatCard(title: String, subtitle: String, modifier: Modifier = Modifier) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(18.dp),
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 0.dp,
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
        shape = RoundedCornerShape(18.dp),
        color = MaterialTheme.colorScheme.surface,
        tonalElevation = 0.dp,
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
