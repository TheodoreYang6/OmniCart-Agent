package com.omnicart.agent.feature.product

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AddShoppingCart
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.omnicart.agent.core.model.DecisionResult
import com.omnicart.agent.core.model.Product
import com.omnicart.agent.core.theme.*

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
    onAddToCart: ((skuId: String?, skuLabel: String, skuPrice: Double) -> Unit)? = null,
    modifier: Modifier = Modifier,
) {
    var selectedTab by remember { mutableStateOf(DetailTab.Recommend) }
    // SKU 选择
    val skus = product.skus.orEmpty()
    var selectedSkuIndex by remember { mutableIntStateOf(if (skus.isNotEmpty()) 0 else -1) }
    val selectedSku = skus.getOrNull(selectedSkuIndex)
    val effectivePrice = selectedSku?.let { if (it.price > 0.0) it.price else product.price } ?: product.price

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        modifier = modifier,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().heightIn(max = 560.dp).padding(bottom = 16.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = product.title, style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f), maxLines = 1,
                )
                IconButton(onClick = onDismiss) { Icon(Icons.Default.Close, "关闭") }
            }
            Spacer(Modifier.height(8.dp))

            ScrollableTabRow(selectedTabIndex = selectedTab.ordinal, edgePadding = 0.dp) {
                DetailTab.entries.forEach { tab ->
                    Tab(selected = selectedTab == tab, onClick = { selectedTab = tab },
                        text = { Text(tab.label, style = MaterialTheme.typography.labelMedium) })
                }
            }

            Box(Modifier.fillMaxWidth().weight(1f, fill = false).verticalScroll(rememberScrollState())) {
                when (selectedTab) {
                    DetailTab.Recommend -> RecommendTab(product, decisionResult, effectivePrice)
                    DetailTab.Evidence -> EvidenceTab(evidenceList)
                    DetailTab.Score -> ScoreTab(decisionResult)
                    DetailTab.Trace -> TraceTab(traceSteps)
                    DetailTab.Skill -> SkillTab()
                    DetailTab.Harness -> HarnessTab(harnessReport)
                }
            }

            // 规格选择 + 加购
            if (onAddToCart != null) {
                if (skus.size > 1) {
                    Row(
                        Modifier.fillMaxWidth().padding(horizontal = 16.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        skus.forEachIndexed { index, sku ->
                            val label = sku.properties?.entries
                                ?.joinToString(" · ") { "${it.key}:${it.value}" }
                                ?: sku.skuId.ifBlank { "默认" }
                            FilterChip(
                                selected = index == selectedSkuIndex,
                                onClick = { selectedSkuIndex = index },
                                label = {
                                    Text(label, style = MaterialTheme.typography.labelSmall, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                },
                                leadingIcon = if (index == selectedSkuIndex) {
                                    { Icon(Icons.Default.CheckCircle, null, Modifier.size(14.dp)) }
                                } else null,
                                shape = RoundedCornerShape(8.dp),
                            )
                        }
                    }
                }
                Surface(color = Surface, tonalElevation = 4.dp) {
                    Row(
                        Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Column {
                            Text(
                                if (skus.size > 1) "已选规格" else "商品价格",
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                            Text(
                                "¥%.2f".format(effectivePrice),
                                style = MaterialTheme.typography.titleMedium,
                                color = PriceRed,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                        Button(
                            onClick = {
                                val sku = skus.getOrNull(selectedSkuIndex)
                                val skuId = sku?.skuId?.ifBlank { null }
                                val skuLabel = sku?.properties?.entries
                                    ?.joinToString(" · ") { "${it.key}:${it.value}" } ?: ""
                                val skuPrice = sku?.price ?: product.price
                                onAddToCart(skuId, skuLabel, skuPrice)
                            },
                            shape = RoundedCornerShape(12.dp),
                        ) {
                            Icon(Icons.Default.AddShoppingCart, null, Modifier.size(18.dp))
                            Spacer(Modifier.width(6.dp))
                            Text("加购物车")
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun RecommendTab(product: Product, decision: DecisionResult?, displayPrice: Double = product.price) {
    Column(modifier = Modifier.padding(16.dp)) {
        decision?.recommendationReason?.let { reason ->
            if (reason.isNotEmpty()) {
                Text("推荐理由", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(8.dp))
                Text(reason, style = MaterialTheme.typography.bodyMedium)
                Spacer(Modifier.height(16.dp))
            }
        }
        decision?.riskFactors?.let { risks ->
            if (risks.isNotEmpty()) {
                Text("风险提示", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(8.dp))
                risks.forEach { risk -> Text("· $risk", style = MaterialTheme.typography.bodyMedium); Spacer(Modifier.height(4.dp)) }
                Spacer(Modifier.height(16.dp))
            }
        }
        Text("商品信息", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(8.dp))
        InfoRow("品牌", product.brand)
        InfoRow("品类", "${product.category} / ${product.subCategory}")
        InfoRow("价格", "¥$displayPrice")
        if (!product.skus.isNullOrEmpty()) InfoRow("规格数", "${product.skus.size} 个 SKU")
        product.ragKnowledge?.userReviews?.let { reviews ->
            InfoRow("用户评分", "${"%.1f".format(reviews.map { it.rating }.average())} / 5 (${reviews.size}条)")
        }
    }
}

@Composable
private fun EvidenceTab(evidenceList: List<Map<String, Any?>>) {
    Column(modifier = Modifier.padding(16.dp)) {
        if (evidenceList.isEmpty()) {
            Text("暂无证据数据", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            return@Column
        }
        Text("证据列表 (${evidenceList.size}条)", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(12.dp))
        evidenceList.take(15).forEach { ev ->
            val type = ev["source_type"]?.toString() ?: "unknown"
            val content = ev["content"]?.toString() ?: ""
            val confidence = (ev["confidence"] as? Number)?.toDouble() ?: 0.0
            Card(Modifier.fillMaxWidth().padding(vertical = 4.dp),
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f))) {
                Column(Modifier.padding(12.dp)) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(typeLabel(type), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
                        Text("置信度 ${"%.0f".format(confidence * 100)}%", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Spacer(Modifier.height(4.dp))
                    Text(content, style = MaterialTheme.typography.bodySmall, maxLines = 4)
                }
            }
        }
    }
}

@Composable
private fun ScoreTab(decision: DecisionResult?) {
    Column(modifier = Modifier.padding(16.dp)) {
        if (decision == null) { Text("暂无评分数据", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant); return@Column }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("综合评分", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
            Text("${decision.displayScore} / 10", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
        }
        Spacer(Modifier.height(16.dp))
        val bd = decision.scoreBreakdown
        ScoreBar("预算匹配", bd?.budgetFit ?: 0.0)
        ScoreBar("场景匹配", bd?.scenarioFit ?: 0.0)
        ScoreBar("规格匹配", bd?.specMatch ?: 0.0)
        ScoreBar("评论置信度", bd?.reviewConfidence ?: 0.0)
        ScoreBar("语义相关度", bd?.visualSimilarity ?: 0.0)
        ScoreBar("性价比", bd?.availabilityScore ?: 0.0)
        ScoreBar("风险惩罚", -(bd?.riskPenalty ?: 0.0))
    }
}

@Composable
private fun ScoreBar(label: String, value: Double) {
    val absValue = kotlin.math.abs(value).coerceIn(0.0, 1.0)
    val color = when { value < 0 -> MaterialTheme.colorScheme.error; absValue >= 0.8 -> MaterialTheme.colorScheme.primary; absValue >= 0.5 -> MaterialTheme.colorScheme.tertiary; else -> MaterialTheme.colorScheme.error }
    Column(modifier = Modifier.padding(vertical = 4.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(label, style = MaterialTheme.typography.bodySmall)
            Text("%.2f".format(value), style = MaterialTheme.typography.labelSmall, color = color)
        }
        Spacer(Modifier.height(2.dp))
        LinearProgressIndicator(progress = { absValue.toFloat() }, modifier = Modifier.fillMaxWidth(), color = color, trackColor = MaterialTheme.colorScheme.surfaceVariant)
    }
}

@Composable
private fun TraceTab(traceSteps: List<Map<String, Any?>>) {
    Column(modifier = Modifier.padding(16.dp)) {
        if (traceSteps.isEmpty()) { Text("暂无 Agent 链路数据", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant); return@Column }
        Text("Agent 执行链路", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(12.dp))
        traceSteps.forEach { step ->
            val agent = step["agent_name"]?.toString() ?: "?"
            val action = step["action"]?.toString() ?: ""
            val status = step["status"]?.toString() ?: "pending"
            val latency = (step["latency_ms"] as? Number)?.toInt() ?: 0
            val output = step["output_summary"]?.toString() ?: ""
            val statusColor = when (status) { "success" -> MaterialTheme.colorScheme.primary; "failed" -> MaterialTheme.colorScheme.error; else -> MaterialTheme.colorScheme.onSurfaceVariant }
            Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.Top) {
                Surface(Modifier.padding(top = 6.dp).size(8.dp), shape = MaterialTheme.shapes.extraSmall, color = statusColor) {}
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(agent, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.SemiBold)
                        Text("${latency}ms", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    if (action.isNotEmpty()) Text(action, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if (output.isNotEmpty()) Text(output, style = MaterialTheme.typography.bodySmall, maxLines = 2)
                }
            }
        }
    }
}

@Composable
private fun SkillTab() {
    Column(modifier = Modifier.padding(16.dp)) {
        Text("Skill 技能执行", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(12.dp))
        listOf(
            Triple("商品截图解析", "Visual Agent → Qwen-VL", "提取商品名/品牌/价格/规格"),
            Triple("评论风险挖掘", "Retrieval Agent → review channel", "提取差评 + 好评"),
            Triple("政策规则查询", "Retrieval Agent → policy channel", "匹配FAQ中航空/兼容/敏感规则"),
            Triple("约束求解", "Decision Agent", "硬约束过滤(预算/品类/标签)"),
            Triple("证据评分", "Decision Agent → Scoring", "7维加权公式 + 风险惩罚"),
            Triple("回答生成", "Response Agent → Qwen LLM", "证据绑定自然语言生成"),
        ).forEachIndexed { i, (name, source, desc) ->
            Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.Top) {
                Surface(Modifier.padding(top = 4.dp).size(8.dp), shape = MaterialTheme.shapes.extraSmall, color = MaterialTheme.colorScheme.primary) {}
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text("Skill ${i + 1}: $name", style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.SemiBold)
                    Text(source, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
                    Text(desc, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}

@Composable
private fun HarnessTab(harnessReport: Map<String, Any?>) {
    Column(modifier = Modifier.padding(16.dp)) {
        if (harnessReport.isEmpty()) { Text("暂无验证数据", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant); return@Column }
        Text("决策验证报告", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(12.dp))
        // 分离顶层 passed/failed_checks 汇总
        val passedOverall = when (val p = harnessReport["passed"]) {
            is Boolean -> p
            is String -> p.lowercase() in listOf("true", "pass", "ok")
            else -> null
        }
        if (passedOverall != null) {
            Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(if (passedOverall) "✅ 整体通过" else "❌ 存在问题", fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
            }
            Spacer(Modifier.height(8.dp))
        }
        harnessReport.forEach { (key, value) ->
            when {
                value is Boolean -> {
                    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(if (value) "✅" else "❌", style = MaterialTheme.typography.bodySmall)
                        Spacer(Modifier.width(6.dp))
                        Text(labelForHarnessKey(key), style = MaterialTheme.typography.bodySmall)
                    }
                }
                value is List<*> -> {
                    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), verticalAlignment = Alignment.Top) {
                        Text("⚠️", style = MaterialTheme.typography.bodySmall)
                        Spacer(Modifier.width(6.dp))
                        Column {
                            Text("$key (${value.size}条)", style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.SemiBold)
                            value.take(3).forEach { item ->
                                Text("  · ${item.toString().take(80)}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                        }
                    }
                }
                value is Map<*, *> -> {
                    // 嵌套 checks dict（如 DecisionHarness checks）
                    Spacer(Modifier.height(4.dp))
                    Text("$key:", style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.SemiBold)
                    value.entries.take(10).forEach { (ck, cv) ->
                        val cp = cv?.toString()?.lowercase() in listOf("true", "pass", "ok")
                        Row(Modifier.fillMaxWidth().padding(start = 16.dp, top = 1.dp)) {
                            Text(if (cp) "✅" else if (cv is Boolean) "❌" else "·", style = MaterialTheme.typography.labelSmall)
                            Spacer(Modifier.width(4.dp))
                            Text("$ck: ${cv?.toString()?.take(40) ?: ""}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
                value is String -> {
                    val passed = value.lowercase() in listOf("true", "pass", "ok", "passed")
                    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(if (passed) "✅" else if (key == "suggestion") "💡" else "·", style = MaterialTheme.typography.bodySmall)
                        Spacer(Modifier.width(6.dp))
                        Text("$key: ${value.take(80)}", style = MaterialTheme.typography.bodySmall)
                    }
                }
                else -> {
                    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("· $key: ${value?.toString()?.take(60) ?: "null"}", style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }
    }
}

private fun labelForHarnessKey(key: String): String = when (key) {
    "evidence_bound" -> "证据已绑定"; "price_accurate" -> "价格准确"; "risk_warned" -> "风险已提醒"
    "honest_on_empty" -> "诚实告知(无结果)"; "schema_valid" -> "Schema校验通过"
    "sufficiency_check" -> "证据充足性"; "no_empty_answer" -> "回答非空"
    else -> key
}

@Composable
private fun InfoRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
        Text("$label：", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.width(72.dp))
        Text(value, style = MaterialTheme.typography.bodySmall)
    }
}

private fun typeLabel(type: String): String = when (type) {
    "text_retrieval" -> "文本检索"; "review_risk" -> "差评风险"; "review_positive" -> "好评"
    "policy_faq" -> "政策FAQ"; "visual" -> "视觉证据"; "marketing" -> "商品描述"; else -> type
}
