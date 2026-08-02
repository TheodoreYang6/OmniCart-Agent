package com.omnicart.agent.feature.demo

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Image
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PlusMenuSheet(
    onDismiss: () -> Unit,
    onScenarioSelected: (String) -> Unit,
    onCameraClick: () -> Unit,
    onGalleryClick: () -> Unit,
) {
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(),
        shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp),
        dragHandle = { Surface(Modifier.padding(vertical = 10.dp), shape = RoundedCornerShape(999.dp), color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.3f)) {
            Box(Modifier.size(32.dp, 4.dp))
        }},
    ) {
        Column(modifier = Modifier.padding(bottom = 32.dp)) {
            // 标题
            Text(
                "快捷场景",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(horizontal = 20.dp),
            )
            Text(
                "点击即可自动发送，快速体验小O的各项能力",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(horizontal = 20.dp, vertical = 4.dp),
            )

            Spacer(modifier = Modifier.height(12.dp))

            // 场景卡片：2列网格
            Column(modifier = Modifier.padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                demoScenarios.chunked(2).forEach { rowItems ->
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        rowItems.forEach { scenario ->
                            Surface(
                                modifier = Modifier
                                    .weight(1f)
                                    .clickable {
                                        onScenarioSelected(scenario.query)
                                        onDismiss()
                                    },
                                shape = RoundedCornerShape(14.dp),
                                color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.7f),
                                tonalElevation = 1.dp,
                            ) {
                                Column(modifier = Modifier.padding(12.dp)) {
                                    Text(scenario.emoji, style = MaterialTheme.typography.titleMedium)
                                    Spacer(modifier = Modifier.height(4.dp))
                                    Text(
                                        scenario.label,
                                        style = MaterialTheme.typography.labelLarge,
                                        fontWeight = FontWeight.SemiBold,
                                    )
                                    Text(
                                        scenario.query.take(20) + "…",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                        maxLines = 1,
                                    )
                                }
                            }
                        }
                        repeat(2 - rowItems.size) { Spacer(modifier = Modifier.weight(1f)) }
                    }
                }
            }

            Spacer(modifier = Modifier.height(20.dp))

            // 图片来源
            Text(
                "图片来源",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(horizontal = 20.dp),
            )

            Spacer(modifier = Modifier.height(8.dp))

            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                listOf(
                    Triple(Icons.Filled.CameraAlt, "拍照", onCameraClick),
                    Triple(Icons.Filled.Image, "相册", onGalleryClick),
                ).forEach { (icon, label, onClick) ->
                    Surface(
                        modifier = Modifier
                            .weight(1f)
                            .clickable { onClick(); onDismiss() },
                        shape = RoundedCornerShape(14.dp),
                        color = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.5f),
                    ) {
                        Column(
                            modifier = Modifier.padding(20.dp),
                            horizontalAlignment = Alignment.CenterHorizontally,
                        ) {
                            Icon(icon, null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(32.dp))
                            Spacer(modifier = Modifier.height(6.dp))
                            Text(label, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Medium)
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))
        }
    }
}
