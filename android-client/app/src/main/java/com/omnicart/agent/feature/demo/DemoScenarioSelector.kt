package com.omnicart.agent.feature.demo

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp

data class DemoScenario(
    val label: String,
    val emoji: String,
    val query: String,
)

val demoScenarios = listOf(
    DemoScenario("数码耳机", "🎧", "推荐一款千元以内的降噪蓝牙耳机"),
    DemoScenario("美妆护肤", "✨", "适合敏感肌的保湿精华推荐"),
    DemoScenario("跑步装备", "🏃", "500以内的轻便跑鞋，适合日常5公里"),
    DemoScenario("办公咖啡", "☕", "办公室提神的咖啡推荐，不要酸的"),
    DemoScenario("风险咨询", "⚠️", "这个面霜油皮能用吗？有没有副作用？"),
    DemoScenario("替代推荐", "🔄", "有没有比AirPods Pro便宜但降噪差不多的替代品？"),
    DemoScenario("拍照识物", "📷", "帮我看看这个商品值不值得买"),
)

@Composable
fun DemoScenarioSelector(
    onScenarioSelected: (String) -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp),
    ) {
        Text(
            text = "试试这些场景：",
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(modifier = Modifier.height(8.dp))
        // 使用 Column + Row 代替 FlowRow 保证兼容性
        demoScenarios.chunked(3).forEach { rowItems ->
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                rowItems.forEach { scenario ->
                    AssistChip(
                        onClick = { onScenarioSelected(scenario.query) },
                        label = {
                            Text(
                                text = "${scenario.emoji} ${scenario.label}",
                                style = MaterialTheme.typography.labelSmall,
                            )
                        },
                        modifier = Modifier.weight(1f),
                    )
                }
                // 补齐不足 3 个的空白
                repeat(3 - rowItems.size) {
                    Spacer(modifier = Modifier.weight(1f))
                }
            }
            Spacer(modifier = Modifier.height(6.dp))
        }
    }
}
