package com.omnicart.agent.feature.profile

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.omnicart.agent.R

@Composable
fun ProfileScreen(
    isLoggedIn: Boolean = false,
    username: String = "",
    onLoginClick: () -> Unit = {},
    onLogoutClick: () -> Unit = {},
    onAddressClick: () -> Unit = {},
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
    ) {
        // 顶栏
        Surface(color = MaterialTheme.colorScheme.surface, tonalElevation = 1.dp) {
            Text(
                "我的",
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 12.dp).fillMaxWidth(),
            )
        }

        // 头像区
        Surface(
            modifier = Modifier.fillMaxWidth(),
            color = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.3f),
        ) {
            Column(
                modifier = Modifier.fillMaxWidth().padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Image(
                    painter = painterResource(id = R.drawable.ic_douzai),
                    contentDescription = "头像",
                    modifier = Modifier.size(80.dp).clip(CircleShape),
                    contentScale = ContentScale.Crop,
                )
                Spacer(Modifier.height(12.dp))

                if (isLoggedIn) {
                    Text(username, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    Button(
                        onClick = onLogoutClick,
                        modifier = Modifier.padding(top = 8.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
                    ) {
                        Text("退出登录")
                    }
                } else {
                    Text("未登录", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    Text("登录后可同步购物车和偏好", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.height(8.dp))
                    Button(onClick = onLoginClick) {
                        Icon(Icons.Filled.Login, null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("登录 / 注册")
                    }
                }
            }
        }

        Spacer(Modifier.height(16.dp))

        // 功能列表
        ProfileItem(Icons.Filled.ShoppingBag, "我的订单", "查看订单历史")
        ProfileItem(Icons.Filled.LocationOn, "收货地址", if (isLoggedIn) "管理收货地址" else "登录后管理收货地址", onClick = onAddressClick)
        ProfileItem(Icons.Filled.Favorite, "我的收藏", "暂无收藏商品")
        ProfileItem(Icons.Filled.Settings, "偏好设置", if (isLoggedIn) "自定义购物偏好" else "登录后设置购物偏好")
        ProfileItem(Icons.Filled.Info, "关于豆仔", "V1 参赛版 · 字节跳动 Agent 挑战赛")
    }
}

@Composable
private fun ProfileItem(icon: androidx.compose.ui.graphics.vector.ImageVector, title: String, subtitle: String, onClick: () -> Unit = {}) {
    Surface(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
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
