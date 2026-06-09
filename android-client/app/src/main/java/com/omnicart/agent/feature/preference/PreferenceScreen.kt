package com.omnicart.agent.feature.preference

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import com.omnicart.agent.core.network.PreferenceEntryDto
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PreferenceScreen(
    userId: String = "",
    onBack: () -> Unit = {},
    viewModel: PreferenceViewModel = viewModel(),
) {
    val uiState by viewModel.uiState.collectAsState()

    LaunchedEffect(userId) {
        if (userId.isNotBlank()) viewModel.loadEntries(userId)
    }

    // 保存成功提示自动消失
    LaunchedEffect(uiState.saveMessage) {
        if (uiState.saveMessage == "已保存") {
            kotlinx.coroutines.delay(2000)
            viewModel.dismissSaveMessage()
        }
    }

    Column(modifier = Modifier.fillMaxSize()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, "返回") }
            Text("购物偏好", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        }
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            // ============ 输入区 ============
            Text("添加偏好", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            Text(
                "描述你的购物习惯，豆仔会智能解析",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            OutlinedTextField(
                value = uiState.inputText,
                onValueChange = viewModel::onInputChange,
                label = { Text("例如：我喜欢苹果手机，预算500左右，不喜欢太重的") },
                minLines = 2,
                maxLines = 4,
                modifier = Modifier.fillMaxWidth(),
                enabled = !uiState.isParsing && !uiState.isSaving,
            )

            // ============ 解析按钮 ============
            Button(
                onClick = { viewModel.parse(userId) },
                modifier = Modifier.fillMaxWidth(),
                enabled = !uiState.isParsing && !uiState.isSaving && uiState.inputText.isNotBlank(),
            ) {
                if (uiState.isParsing) {
                    CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp,
                        color = MaterialTheme.colorScheme.onPrimary)
                    Spacer(Modifier.width(8.dp))
                    Text("解析中...")
                } else {
                    Icon(Icons.Filled.AutoAwesome, null, Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                    Text("解析")
                }
            }

            // ============ 解析错误 ============
            uiState.parseError?.let { err ->
                Card(
                    Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
                ) {
                    Text(err, Modifier.padding(12.dp), color = MaterialTheme.colorScheme.onErrorContainer,
                        style = MaterialTheme.typography.bodySmall)
                }
            }

            // ============ 解析预览 + 保存 ============
            uiState.parsedEntry?.let { entry ->
                Card(
                    Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.4f)),
                ) {
                    Column(Modifier.padding(12.dp)) {
                        Text("解析结果", style = MaterialTheme.typography.labelMedium,
                            fontWeight = FontWeight.SemiBold,
                            color = MaterialTheme.colorScheme.primary)
                        Spacer(Modifier.height(6.dp))

                        PreferenceTagRow("品类", entry.category)
                        if (entry.subCategory.isNotBlank()) PreferenceTagRow("子品类", entry.subCategory)
                        if (entry.brands.isNotEmpty()) PreferenceTagRow("品牌", entry.brands.joinToString(" · "))
                        if (entry.scenarios.isNotEmpty()) PreferenceTagRow("场景", entry.scenarios.joinToString(" · "))
                        if (entry.budgetMin != null || entry.budgetMax != null) {
                            val b = buildString {
                                if (entry.budgetMin != null && entry.budgetMin > 0) append("¥${entry.budgetMin.toInt()}")
                                append(" ~ ")
                                if (entry.budgetMax != null && entry.budgetMax > 0) append("¥${entry.budgetMax.toInt()}")
                            }
                            PreferenceTagRow("预算", b)
                        }
                        if (entry.mustTags.isNotEmpty()) PreferenceTagRow("偏好", entry.mustTags.joinToString(" · "))
                        if (entry.avoidTags.isNotEmpty()) PreferenceTagRow("避雷", entry.avoidTags.joinToString(" · "))

                        Spacer(Modifier.height(8.dp))
                        Button(
                            onClick = { viewModel.save(userId) },
                            modifier = Modifier.fillMaxWidth(),
                            enabled = !uiState.isSaving,
                        ) {
                            if (uiState.isSaving) {
                                CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp,
                                    color = MaterialTheme.colorScheme.onPrimary)
                                Spacer(Modifier.width(8.dp))
                            }
                            Text(if (uiState.isSaving) "保存中..." else "保存")
                        }
                    }
                }
            }

            // ============ 保存反馈 ============
            uiState.saveMessage?.let { msg ->
                if (msg != "已保存") {
                    Card(
                        Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(12.dp),
                        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer),
                    ) {
                        Text(msg, Modifier.padding(12.dp), color = MaterialTheme.colorScheme.onErrorContainer,
                            style = MaterialTheme.typography.bodySmall)
                    }
                }
            }

            HorizontalDivider(Modifier.padding(vertical = 4.dp))

            // ============ 已保存列表 ============
            Text(
                "已保存的偏好 (${uiState.entries.size})",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
            )

            if (uiState.isLoadingEntries) {
                Box(Modifier.fillMaxWidth().padding(24.dp), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
            } else if (uiState.entries.isEmpty()) {
                Text(
                    "还没有偏好，在上面添加吧",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.padding(vertical = 16.dp),
                )
            } else {
                uiState.entries.forEach { entry ->
                    PreferenceEntryCard(
                        entry = entry,
                        onDelete = { viewModel.deleteEntry(userId, entry.entryId) },
                        isDeleting = uiState.isDeleting,
                    )
                }
            }

            Spacer(Modifier.height(80.dp))
        }
    }
}

@Composable
private fun PreferenceTagRow(label: String, value: String) {
    Row(Modifier.padding(vertical = 1.dp)) {
        Text("$label: ", style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.width(56.dp))
        Text(value, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun PreferenceEntryCard(
    entry: PreferenceEntryDto,
    onDelete: () -> Unit,
    isDeleting: Boolean,
) {
    Card(
        Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)),
    ) {
        Row(Modifier.padding(12.dp), verticalAlignment = Alignment.Top) {
            Column(Modifier.weight(1f)) {
                // 品类标签
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Surface(shape = RoundedCornerShape(6.dp), color = MaterialTheme.colorScheme.primaryContainer) {
                        Text(
                            entry.category.ifBlank { "未分类" },
                            Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.primary,
                        )
                    }
                    if (entry.subCategory.isNotBlank()) {
                        Surface(shape = RoundedCornerShape(6.dp), color = MaterialTheme.colorScheme.secondaryContainer) {
                            Text(
                                entry.subCategory,
                                Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.secondary,
                            )
                        }
                    }
                }
                Spacer(Modifier.height(4.dp))
                // 原始输入
                Text(
                    entry.rawText,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
                // 关键字段摘要
                val summary = buildList {
                    if (entry.brands.isNotEmpty()) add(entry.brands.joinToString("/"))
                    if (entry.mustTags.isNotEmpty()) add(entry.mustTags.take(3).joinToString(" · "))
                    if (entry.avoidTags.isNotEmpty()) add("避:${entry.avoidTags.take(2).joinToString("/")}")
                    if (entry.scenarios.isNotEmpty()) add(entry.scenarios.joinToString("/"))
                    if (entry.budgetMax != null && entry.budgetMax > 0) add("≤¥${entry.budgetMax.toInt()}")
                }.joinToString(" | ")
                if (summary.isNotBlank()) {
                    Text(
                        summary,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
            }
            IconButton(
                onClick = onDelete,
                enabled = !isDeleting,
                modifier = Modifier.size(36.dp),
            ) {
                Icon(Icons.Filled.Delete, "删除", Modifier.size(18.dp),
                    tint = MaterialTheme.colorScheme.error)
            }
        }
    }
}
