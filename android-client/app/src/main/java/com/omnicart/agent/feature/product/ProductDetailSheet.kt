package com.omnicart.agent.feature.product

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.omnicart.agent.core.model.DecisionResult
import com.omnicart.agent.core.model.Product

enum class DetailTab(val label: String) {
    Recommend("推荐"),
    Evidence("证据"),
    Score("评分"),
    Trace("链路"),
    Skill("技能"),
    Harness("验证"),
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProductDetailSheet(
    product: Product,
    decisionResult: DecisionResult?,
    evidenceList: List<Map<String, Any?>>,
    traceSteps: List<Map<String, Any?>>,
    harnessReport: Map<String, Any?>,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
) {
    var selectedTab by remember { mutableStateOf(DetailTab.Recommend) }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        modifier = modifier,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(max = 560.dp)
                .padding(bottom = 16.dp),
        ) {
            // 标题栏
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = product.title,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f),
                    maxLines = 1,
                )
                IconButton(onClick = onDismiss) {
                    Icon(Icons.Default.Close, contentDescription = "关闭")
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Tab 栏（可滚动）
            ScrollableTabRow(
                selectedTabIndex = selectedTab.ordinal,
                edgePadding = 0.dp,
            ) {
                DetailTab.entries.forEach { tab ->
                    Tab(
                        selected = selectedTab == tab,
                        onClick = { selectedTab = tab },
                        text = {
                            Text(
                                text = tab.label,
                                style = MaterialTheme.typography.labelMedium,
                            )
                        },
                    )
                }
            }

            // Tab 内容区
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f, fill = false)
                    .verticalScroll(rememberScrollState()),
            ) {
                when (selectedTab) {
                    DetailTab.Recommend -> RecommendTab(product, decisionResult)
                    DetailTab.Evidence -> EvidenceTab(evidenceList)
                    DetailTab.Score -> ScoreTab(decisionResult)
                    DetailTab.Trace -> TraceTab(traceSteps)
                    DetailTab.Skill -> SkillTab()
                    DetailTab.Harness -> HarnessTab(harnessReport)
                }
            }
        }
    }
}

// ---- 各 Tab 占位内容 ----

@Composable
private fun RecommendTab(product: Product, decision: DecisionResult?) {
    Column(modifier = Modifier.padding(16.dp)) {
        val reason = decision?.recommendationReason ?: ""
        if (reason.isNotEmpty()) {
            Text(
                text = "推荐理由",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = reason,
                style = MaterialTheme.typography.bodyMedium,
            )
            Spacer(modifier = Modifier.height(16.dp))
        }

        val risks = decision?.riskFactors ?: emptyList()
        if (risks.isNotEmpty()) {
            Text(
                text = "风险提示",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(modifier = Modifier.height(8.dp))
            risks.forEach { risk ->
                Text(
                    text = "⚠ $risk",
                    style = MaterialTheme.typography.bodyMedium,
                )
                Spacer(modifier = Modifier.height(4.dp))
            }
            Spacer(modifier = Modifier.height(16.dp))
        }

        if (reason.isEmpty() && risks.isEmpty()) {
            Text(
                text = "暂无推荐详情",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        // 商品基本信息
        Text(
            text = "商品信息",
            style = MaterialTheme.typography.titleSmall,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(modifier = Modifier.height(8.dp))
        InfoRow("品牌", product.brand)
        InfoRow("品类", "${product.category} / ${product.subCategory}")
        InfoRow("价格", "¥${product.price}")
        if (!product.skus.isNullOrEmpty()) {
            InfoRow("规格数", "${product.skus.size} 个 SKU")
        }
        product.ragKnowledge?.userReviews?.let { reviews ->
            val avg = reviews.map { it.rating }.average()
            InfoRow("用户评分", "${"%.1f".format(avg)} / 5 (${reviews.size}条评价)")
        }
    }
}

@Composable
private fun EvidenceTab(evidenceList: List<Map<String, Any?>>) {
    Column(modifier = Modifier.padding(16.dp)) {
        if (evidenceList.isEmpty()) {
            Text(
                text = "暂无证据数据",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            return@Column
        }

        Text(
            text = "证据列表 (${evidenceList.size}条)",
            style = MaterialTheme.typography.titleSmall,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(modifier = Modifier.height(12.dp))

        evidenceList.take(15).forEachIndexed { i, ev ->
            val type = ev["source_type"]?.toString() ?: "unknown"
            val content = ev["content"]?.toString() ?: ""
            val confidence = (ev["confidence"] as? Number)?.toDouble() ?: 0.0

            Card(
                modifier = Modifier.fillMaxWidth(),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
                ),
            ) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Text(
                            text = typeLabel(type),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.primary,
                        )
                        Text(
                            text = "置信度 ${"%.0f".format(confidence * 100)}%",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = content,
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 4,
                    )
                }
            }
            if (i < evidenceList.size - 1) {
                Spacer(modifier = Modifier.height(8.dp))
            }
        }
    }
}

@Composable
private fun ScoreTab(decision: DecisionResult?) {
    Column(modifier = Modifier.padding(16.dp)) {
        if (decision == null) {
            Text(
                text = "暂无评分数据",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            return@Column
        }

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(
                text = "综合评分",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                text = "${decision.displayScore} / 10",
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary,
            )
        }
        Spacer(modifier = Modifier.height(16.dp))

        val bd = decision.scoreBreakdown
        ScoreBar("预算匹配", bd?.budgetFit ?: 0.0)
        ScoreBar("场景匹配", bd?.scenarioFit ?: 0.0)
        ScoreBar("规格匹配", bd?.specMatch ?: 0.0)
        ScoreBar("评论置信度", bd?.reviewConfidence ?: 0.0)
        ScoreBar("视觉相似度", bd?.visualSimilarity ?: 0.0)
        ScoreBar("可用性", bd?.availabilityScore ?: 0.0)
        ScoreBar("风险惩罚", -(bd?.riskPenalty ?: 0.0))
    }
}

@Composable
private fun ScoreBar(label: String, value: Double) {
    val absValue = kotlin.math.abs(value).coerceIn(0.0, 1.0)
    val color = when {
        value < 0 -> MaterialTheme.colorScheme.error
        absValue >= 0.8 -> MaterialTheme.colorScheme.primary
        absValue >= 0.5 -> MaterialTheme.colorScheme.tertiary
        else -> MaterialTheme.colorScheme.error
    }

    Column(modifier = Modifier.padding(vertical = 4.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text(text = label, style = MaterialTheme.typography.bodySmall)
            Text(
                text = "%.2f".format(value),
                style = MaterialTheme.typography.labelSmall,
                color = color,
            )
        }
        Spacer(modifier = Modifier.height(2.dp))
        LinearProgressIndicator(
            progress = { absValue.toFloat() },
            modifier = Modifier.fillMaxWidth(),
            color = color,
            trackColor = MaterialTheme.colorScheme.surfaceVariant,
        )
    }
}

@Composable
private fun TraceTab(traceSteps: List<Map<String, Any?>>) {
    Column(modifier = Modifier.padding(16.dp)) {
        if (traceSteps.isEmpty()) {
            Text(
                text = "暂无 Agent 链路数据",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            return@Column
        }

        Text(
            text = "Agent 执行链路",
            style = MaterialTheme.typography.titleSmall,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(modifier = Modifier.height(12.dp))

        traceSteps.forEach { step ->
            val agent = step["agent_name"]?.toString() ?: "?"
            val action = step["action"]?.toString() ?: ""
            val status = step["status"]?.toString() ?: "pending"
            val latency = (step["latency_ms"] as? Number)?.toInt() ?: 0
            val output = step["output_summary"]?.toString() ?: ""

            val statusColor = when (status) {
                "success" -> MaterialTheme.colorScheme.primary
                "failed" -> MaterialTheme.colorScheme.error
                "fallback" -> MaterialTheme.colorScheme.tertiary
                else -> MaterialTheme.colorScheme.onSurfaceVariant
            }

            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 6.dp),
                verticalAlignment = Alignment.Top,
            ) {
                // 状态指示点
                Surface(
                    modifier = Modifier
                        .padding(top = 6.dp)
                        .size(8.dp),
                    shape = MaterialTheme.shapes.extraSmall,
                    color = statusColor,
                ) {}
                Spacer(modifier = Modifier.width(12.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                    ) {
                        Text(
                            text = agent,
                            style = MaterialTheme.typography.bodySmall,
                            fontWeight = FontWeight.SemiBold,
                        )
                        Text(
                            text = "${latency}ms",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    if (action.isNotEmpty()) {
                        Text(
                            text = action,
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    if (output.isNotEmpty()) {
                        Text(
                            text = output,
                            style = MaterialTheme.typography.bodySmall,
                            maxLines = 2,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun HarnessTab(harnessReport: Map<String, Any?>) {
    Column(modifier = Modifier.padding(16.dp)) {
        if (harnessReport.isEmpty()) {
            Text(
                text = "暂无 Harness 验证数据",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            return@Column
        }

        Text(
            text = "决策验证报告",
            style = MaterialTheme.typography.titleSmall,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(modifier = Modifier.height(12.dp))

        harnessReport.forEach { (key, value) ->
            val passed = value?.toString()?.lowercase() in listOf("true", "pass", "ok", "passed")
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 4.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Icon(
                    imageVector = if (passed)
                        Icons.Default.Close // placeholder — 替换为勾图标
                    else
                        Icons.Default.Close,
                    contentDescription = null,
                    modifier = Modifier.size(16.dp),
                    tint = if (passed)
                        MaterialTheme.colorScheme.primary
                    else
                        MaterialTheme.colorScheme.error,
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = "$key: ${value?.toString() ?: ""}",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
}

@Composable
private fun SkillTab() {
    Column(modifier = Modifier.padding(16.dp)) {
        // V2 API 尚未返回 skill_executions 数据，展示架构预留说明
        Text(
            text = "Skill 技能执行",
            style = MaterialTheme.typography.titleSmall,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(modifier = Modifier.height(12.dp))

        val plannedSkills = listOf(
            Triple("商品截图解析", "Visual Agent → Qwen-VL", "提取商品名/品牌/价格/规格"),
            Triple("评论风险挖掘", "Retrieval Agent → review channel", "提取≤2星差评 + ≥4星好评"),
            Triple("政策规则查询", "Retrieval Agent → policy channel", "匹配FAQ中航空/兼容/敏感规则"),
            Triple("约束求解", "Decision Agent", "硬约束过滤(预算/品类/标签)"),
            Triple("证据评分", "Decision Agent → Scoring", "7维加权公式 + 风险惩罚"),
            Triple("回答生成", "Response Agent → Qwen LLM", "证据绑定自然语言生成"),
        )

        plannedSkills.forEachIndexed { i, (name, source, desc) ->
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 6.dp),
                verticalAlignment = Alignment.Top,
            ) {
                Surface(
                    modifier = Modifier
                        .padding(top = 4.dp)
                        .size(8.dp),
                    shape = MaterialTheme.shapes.extraSmall,
                    color = MaterialTheme.colorScheme.primary,
                ) {}
                Spacer(modifier = Modifier.width(12.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Skill ${i + 1}: $name",
                        style = MaterialTheme.typography.bodySmall,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Text(
                        text = source,
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary,
                    )
                    Text(
                        text = desc,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}

@Composable
private fun InfoRow(label: String, value: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 2.dp),
    ) {
        Text(
            text = "$label：",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.width(72.dp),
        )
        Text(text = value, style = MaterialTheme.typography.bodySmall)
    }
}

private fun typeLabel(type: String): String = when (type) {
    "text_retrieval" -> "文本检索"
    "review_risk" -> "差评风险"
    "review_positive" -> "好评"
    "policy_faq" -> "政策FAQ"
    "visual" -> "视觉证据"
    "marketing" -> "商品描述"
    else -> type
}
