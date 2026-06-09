package com.omnicart.agent.feature.panel

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
import com.omnicart.agent.core.model.RecommendResponse

/** V1-Plus 全部10项加分面板整合 */
enum class InsightTab(val label: String) {
    Context("上下文"),
    Plan("检索计划"),
    Evidence("证据图"),
    Fallback("降级"),
    Tools("工具"),
    Counter("反事实"),
    Grounding("视觉绑定"),
    Preference("偏好"),
    Memory("记忆追溯"),
    Baseline("基准"),
    Summary("汇总"),
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AgentInsightSheet(
    response: RecommendResponse?,
    onDismiss: () -> Unit,
) {
    if (response == null) return
    var selectedTab by remember { mutableStateOf(InsightTab.Context) }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
    ) {
        Column(Modifier.fillMaxWidth().heightIn(max = 560.dp).padding(bottom = 16.dp)) {
            Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically) {
                Text("Agent 洞察", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                IconButton(onClick = onDismiss) { Icon(Icons.Default.Close, "关闭") }
            }
            Spacer(Modifier.height(4.dp))
            ScrollableTabRow(selectedTabIndex = selectedTab.ordinal, edgePadding = 0.dp) {
                InsightTab.entries.forEach { tab ->
                    Tab(selected = selectedTab == tab, onClick = { selectedTab = tab },
                        text = { Text(tab.label, style = MaterialTheme.typography.labelSmall) })
                }
            }
            Box(Modifier.fillMaxWidth().weight(1f, fill = false).verticalScroll(rememberScrollState())) {
                when (selectedTab) {
                    InsightTab.Context -> ContextTab(response)
                    InsightTab.Plan -> PlanTab(response)
                    InsightTab.Evidence -> EvidenceGraphTab(response)
                    InsightTab.Fallback -> FallbackTab(response)
                    InsightTab.Tools -> ToolsTab(response)
                    InsightTab.Counter -> CounterTab(response)
                    InsightTab.Grounding -> GroundingTab(response)
                    InsightTab.Preference -> PreferenceTab(response)
                    InsightTab.Memory -> MemoryTab(response)
                    InsightTab.Baseline -> BaselineTab(response)
                    InsightTab.Summary -> SummaryTab(response)
                }
            }
        }
    }
}

// ---- #31 Context Panel ----
@Composable
private fun ContextTab(r: RecommendResponse) {
    Column(Modifier.padding(16.dp)) {
        Text("系统理解的用户上下文", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleSmall)
        Spacer(Modifier.height(12.dp))

        val c = r.constraints ?: emptyMap()
        InsightRow("意图", r.retrievalPlan?.get("intent")?.toString() ?: r.traceSteps.firstOrNull()?.action ?: "-")
        InsightRow("品类", c["category"]?.toString() ?: "未指定")
        c["sub_category"]?.toString()?.takeIf { it.isNotBlank() }?.let { InsightRow("子品类", it) }
        c["budget_max"]?.let { InsightRow("预算上限", "¥${it}") }
        c["budget_min"]?.let { InsightRow("预算下限", "¥${it}") }
        c["scenario"]?.toString()?.takeIf { it.isNotBlank() }?.let { InsightRow("场景", it) }

        val tags = c["must_tags"] as? List<*> ?: emptyList<Any>()
        if (tags.isNotEmpty()) InsightRow("偏好标签", tags.joinToString("、"))

        r.sufficiencyReport?.let { sr ->
            Spacer(Modifier.height(8.dp))
            HorizontalDivider()
            Spacer(Modifier.height(8.dp))
            Text("证据充足性", fontWeight = FontWeight.SemiBold)
            InsightRow("总证据数", sr["total_evidence"]?.toString() ?: "0")
            InsightRow("是否充足", if (sr["sufficient"] == true) "✅ 充足" else "⚠️ 不足")
            (sr["missing_types"] as? List<*>)?.let { if (it.isNotEmpty()) InsightRow("缺失类型", it.joinToString("、")) }
        }
    }
}

// ---- #30 Retrieval Plan Panel ----
@Composable
private fun PlanTab(r: RecommendResponse) {
    Column(Modifier.padding(16.dp)) {
        Text("Router 检索计划", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleSmall)
        Spacer(Modifier.height(12.dp))

        val plan = r.retrievalPlan ?: emptyMap()
        InsightRow("频道", (plan["channels"] as? List<*>)?.joinToString(" → ") ?: "text")
        InsightRow("品类", plan["category"]?.toString() ?: "全品类")
        plan["sub_category"]?.toString()?.takeIf { it.isNotBlank() }?.let { InsightRow("子品类", it) }
        InsightRow("Top-K", plan["top_k"]?.toString() ?: "5")
        InsightRow("策略", plan["priority"]?.toString() ?: "balanced")
        InsightRow("意图", plan["intent"]?.toString() ?: r.traceSteps.firstOrNull()?.action ?: "-")

        Spacer(Modifier.height(12.dp))
        Text("实际执行链路", fontWeight = FontWeight.SemiBold)
        Spacer(Modifier.height(8.dp))
        r.traceSteps.forEach { step ->
            Row(Modifier.padding(vertical = 2.dp)) {
                Text("${step.stepId} ", style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary)
                Text("${step.agentName} → ${step.action}", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

// ---- #35 Evidence Graph Panel ----
@Composable
private fun EvidenceGraphTab(r: RecommendResponse) {
    Column(Modifier.padding(16.dp)) {
        Text("证据图关系", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleSmall)
        Spacer(Modifier.height(12.dp))

        val evidenceByProduct = r.evidenceList.groupBy { it.productId ?: "global" }
        evidenceByProduct.forEach { (pid, evs) ->
            if (pid != "global") {
                val product = r.products.find { it.productId == pid }
                Text(product?.title?.take(30) ?: pid, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodySmall)
                evs.forEach { ev ->
                    Row(Modifier.padding(start = 12.dp, top = 2.dp)) {
                        val icon = when (ev.sourceType) {
                            "review_positive" -> "🟢"; "review_risk" -> "🔴"
                            "policy_faq" -> "🔵"; "marketing" -> "🟡"; else -> "⚪"
                        }
                        Text("$icon ${ev.evidenceId}", style = MaterialTheme.typography.labelSmall)
                    }
                }
                Spacer(Modifier.height(4.dp))
            }
        }
        if (evidenceByProduct.isEmpty() || evidenceByProduct.size == 1 && evidenceByProduct.containsKey("global")) {
            Text("暂无证据图数据", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

// ---- #37 Fallback Status Panel ----
@Composable
private fun FallbackTab(r: RecommendResponse) {
    Column(Modifier.padding(16.dp)) {
        Text("降级状态追踪", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleSmall)
        Spacer(Modifier.height(12.dp))

        val fb = r.fallbackStatus ?: emptyMap()
        if (fb.isEmpty()) {
            Text("本次请求无降级发生（全链路正常运行）", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.primary)
            return@Column
        }
        InsightRow("降级级别", fb["level"]?.toString() ?: "0")
        InsightRow("描述", fb["description"]?.toString() ?: "-")
        (fb["attempts"] as? List<*>)?.let { attempts ->
            Text("降级历史:", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.labelSmall)
            attempts.forEach { a -> Text("  · $a", style = MaterialTheme.typography.bodySmall) }
        }

        Spacer(Modifier.height(12.dp))
        Text("Trace 中的状态异常", fontWeight = FontWeight.SemiBold)
        r.traceSteps.filter { it.status != "success" && it.status != "pass" }.forEach { step ->
            Row(Modifier.padding(vertical = 2.dp)) {
                Text("${step.status}: ", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.labelSmall)
                Text(step.agentName, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

// ---- #36 Tool Governance Panel ----
@Composable
private fun ToolsTab(r: RecommendResponse) {
    Column(Modifier.padding(16.dp)) {
        Text("工具调用治理", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleSmall)
        Spacer(Modifier.height(12.dp))

        val tools = listOf(
            ToolInfo("product_text_search", "读", "低", "RetrievalAgent", "jieba关键词检索"),
            ToolInfo("product_vector_search", "读", "低", "RetrievalAgent", "Qdrant向量检索"),
            ToolInfo("review_search", "读", "低", "RetrievalAgent", "用户评论挖掘"),
            ToolInfo("policy_lookup", "读", "低", "RetrievalAgent", "政策FAQ查询"),
            ToolInfo("structured_filter", "读", "低", "DecisionAgent", "品类/价格过滤"),
            ToolInfo("decision_score_calculator", "读", "低", "DecisionAgent", "7维评分计算"),
            ToolInfo("qwen_vision", "读", "中", "VisualAgent", "Qwen-VL图片解析"),
            ToolInfo("qwen_chat", "读", "中", "ResponseAgent", "LLM回答生成"),
        )

        tools.forEach { t ->
            Card(Modifier.fillMaxWidth().padding(vertical = 2.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f))) {
                Row(Modifier.padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(t.name, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold)
                        Text(t.desc, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    AssistChip(onClick = {}, label = { Text(t.permission, style = MaterialTheme.typography.labelSmall) }, modifier = Modifier.height(20.dp))
                    Spacer(Modifier.width(4.dp))
                    AssistChip(onClick = {}, label = { Text(t.risk, style = MaterialTheme.typography.labelSmall) },
                        modifier = Modifier.height(20.dp),
                        colors = AssistChipDefaults.assistChipColors(containerColor = if (t.risk == "低") MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.3f) else MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.3f)))
                }
            }
        }
    }
}

// ---- #34 Counterfactual Panel ----
@Composable
private fun CounterTab(r: RecommendResponse) {
    Column(Modifier.padding(16.dp)) {
        Text("反事实推荐", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleSmall)
        Spacer(Modifier.height(12.dp))

        if (r.products.isEmpty()) {
            Text("⚠️ 本次检索返回0结果", color = MaterialTheme.colorScheme.error)
            Spacer(Modifier.height(8.dp))
            Text("建议方案:", fontWeight = FontWeight.SemiBold)
            listOf("放宽预算范围", "扩大品类搜索", "减少偏好标签限制", "使用更通用的关键词").forEach {
                Row(Modifier.padding(vertical = 2.dp)) { Text("  · $it", style = MaterialTheme.typography.bodySmall) }
            }
        } else {
            Text("本次检索返回 ${r.products.size} 个结果", color = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.height(4.dp))
            Text("如对结果不满意，可尝试：", style = MaterialTheme.typography.bodySmall)
            listOf("调整预算或品类筛选条件", "换用同义词重新搜索", "上传商品截图进行视觉匹配").forEach {
                Text("  · $it", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

// ---- #33 Visual Grounding Panel ----
@Composable
private fun GroundingTab(r: RecommendResponse) {
    Column(Modifier.padding(16.dp)) {
        Text("视觉证据绑定", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleSmall)
        Spacer(Modifier.height(12.dp))

        val vr = r.visualResult
        if (vr == null || vr.isEmpty()) {
            Row {
                Icon(Icons.Filled.Close, null, Modifier.size(16.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(Modifier.width(4.dp))
                Text("本次请求未包含图片或无视觉解析结果", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            return@Column
        }
        val fields = listOf("product_name" to "商品名称", "brand" to "品牌", "category" to "品类", "specs" to "规格", "price" to "价格")
        fields.forEach { (key, label) ->
            val value = vr[key]
            if (value != null && value.toString().isNotBlank()) {
                Row(Modifier.padding(vertical = 3.dp)) {
                    Text("${label}: ", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.bodySmall)
                    Text(value.toString().take(60), style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        InsightRow("置信度", "${((vr["confidence"] as? Number)?.toDouble()?.times(100))?.toInt() ?: 0}%")

        vr["evidence_list"]?.let { evList ->
            if (evList is List<*> && evList.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                Text("绑定证据:", fontWeight = FontWeight.SemiBold)
                evList.take(5).forEach { ev ->
                    if (ev is Map<*, *>) {
                        Text("  · ${ev["field"]}: ${ev["value"]?.toString()?.take(40)}", style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }
    }
}

// ---- #32 Preference Memory Card Panel ----
@Composable
private fun PreferenceTab(r: RecommendResponse) {
    Column(Modifier.padding(16.dp)) {
        Text("偏好记忆卡片", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleSmall)
        Spacer(Modifier.height(12.dp))

        val c = r.constraints ?: emptyMap()
        val hasPrefs = c.any { (_, v) -> v != null && v.toString().isNotBlank() && v !is List<*> || (v is List<*> && v.isNotEmpty()) }

        if (!hasPrefs) {
            Text("暂无会话偏好记忆。多轮对话后系统会积累您的偏好。", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            return@Column
        }
        Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.2f))) {
            Column(Modifier.padding(12.dp)) {
                c["category"]?.toString()?.takeIf { it.isNotBlank() }?.let { InsightRow("品类", it) }
                c["sub_category"]?.toString()?.takeIf { it.isNotBlank() }?.let { InsightRow("子品类", it) }
                c["budget_max"]?.let { InsightRow("预算", "≤ ¥${it}") }
                c["scenario"]?.toString()?.takeIf { it.isNotBlank() }?.let { InsightRow("场景", it) }
                val tags = c["must_tags"] as? List<*> ?: emptyList<Any>()
                if (tags.isNotEmpty()) InsightRow("偏好标签", tags.joinToString("、"))
                val avoids = c["exclude_tags"] as? List<*> ?: emptyList<Any>()
                if (avoids.isNotEmpty()) InsightRow("排除标签", avoids.joinToString("、"))
            }
        }
        Spacer(Modifier.height(8.dp))
        Text("提示：切换品类话题时旧偏好自动清除，确保推荐不受历史干扰", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

// ---- #P2 Memory Trace Panel — 记忆追溯 ----
@Composable
private fun MemoryTab(r: RecommendResponse) {
    Column(Modifier.padding(16.dp)) {
        Text("记忆追溯 (Memory Trace)", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleSmall)
        Spacer(Modifier.height(4.dp))
        Text("本次推荐使用了哪些长期记忆，屏蔽了哪些记忆", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(12.dp))

        val used = r.usedMemories ?: emptyList()
        val blocked = r.blockedMemories ?: emptyList()
        val trace = r.memoryTrace ?: emptyMap()

        // 统计摘要
        if (trace.isNotEmpty()) {
            Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.15f))) {
                Column(Modifier.padding(12.dp)) {
                    InsightRow("原子记忆总数", trace["total_atomic"]?.toString() ?: "-")
                    InsightRow("本次使用", trace["used_count"]?.toString() ?: "-")
                    InsightRow("已屏蔽", trace["blocked_count"]?.toString() ?: "-")
                    InsightRow("快照可用", if (trace["snapshot_available"] == true) "是" else "否")
                    InsightRow("参考消息", trace["recent_messages"]?.toString() ?: "0")
                }
            }
            Spacer(Modifier.height(12.dp))
        }

        // 使用的记忆
        if (used.isNotEmpty()) {
            Text("已使用的记忆 (${used.size})", fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.height(4.dp))
            used.forEach { m ->
                val mem = m as? Map<*, *> ?: return@forEach
                val type = mem["memory_type"]?.toString() ?: ""
                val content = mem["content"]?.toString()?.take(80) ?: ""
                val source = mem["source"]?.toString() ?: ""
                val conf = (mem["confidence"] as? Number)?.toDouble() ?: 0.0
                val isHard = mem["is_hard_constraint"] == true
                val reason = mem["reason"]?.toString() ?: ""

                Card(Modifier.fillMaxWidth().padding(vertical = 2.dp),
                    colors = CardDefaults.cardColors(containerColor = if (isHard) MaterialTheme.colorScheme.errorContainer.copy(alpha = 0.2f) else MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f))
                ) {
                    Column(Modifier.padding(8.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("[$type]", style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold,
                                color = if (isHard) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.primary)
                            if (isHard) {
                                Spacer(Modifier.width(4.dp))
                                Text("硬约束", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.error)
                            }
                        }
                        Text(content, style = MaterialTheme.typography.bodySmall)
                        Row {
                            Text("置信度: ${(conf * 100).toInt()}%", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Spacer(Modifier.width(8.dp))
                            Text("来源: $source", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        if (reason.isNotBlank()) {
                            Text(reason, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
            Spacer(Modifier.height(8.dp))
        } else {
            Text("本次推荐未使用长期记忆（可能是首次使用或未提供 user_id）", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(8.dp))
        }

        // 屏蔽的记忆
        if (blocked.isNotEmpty()) {
            Text("已屏蔽的记忆 (${blocked.size})", fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.error)
            Spacer(Modifier.height(4.dp))
            blocked.take(5).forEach { b ->
                val mem = b as? Map<*, *> ?: return@forEach
                val type = mem["memory_type"]?.toString() ?: ""
                val reason = mem["reason"]?.toString() ?: ""
                val content = mem["content"]?.toString()?.take(60) ?: ""

                Row(Modifier.padding(vertical = 1.dp)) {
                    Text("[$type] ", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.error)
                    Text(content, style = MaterialTheme.typography.labelSmall)
                    if (reason.isNotBlank()) {
                        Text(" — $reason", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }

        if (used.isEmpty() && blocked.isEmpty() && trace.isEmpty()) {
            Text("暂无记忆追溯数据。\n\n登录用户多次使用后，系统将累积偏好记忆并在推荐时追溯展示。", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

// ---- #39 Baseline Panel ----
@Composable
private fun BaselineTab(r: RecommendResponse) {
    Column(Modifier.padding(16.dp)) {
        Text("基准评测", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleSmall)
        Spacer(Modifier.height(12.dp))

        Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f))) {
            Column(Modifier.padding(12.dp)) {
                Text("当前查询评测指标", fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(8.dp))
                InsightRow("返回结果数", r.products.size.toString())
                InsightRow("证据总数", r.evidenceList.size.toString())
                InsightRow("决策结果数", r.decisionResults.size.toString())
                InsightRow("Trace 步数", r.traceSteps.size.toString())
                InsightRow("Harness 通过", if (r.harnessReport?.get("passed")?.toString()?.lowercase() == "true") "✅ 通过" else "❌ 未通过")
                InsightRow("回答长度", "${r.answer.length} 字")
                InsightRow("有图片", if (r.visualResult != null) "✅" else "❌")
            }
        }

        Spacer(Modifier.height(8.dp))
        Text("完整 Baseline 评测运行: python scripts/run_baseline.py", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

// ---- Summary Tab ----
@Composable
private fun SummaryTab(r: RecommendResponse) {
    Column(Modifier.padding(16.dp)) {
        Text("Agent 执行摘要", fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleSmall)
        Spacer(Modifier.height(12.dp))

        Card(Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.15f))) {
            Column(Modifier.padding(12.dp)) {
                InsightRow("会话ID", r.sessionId)
                InsightRow("意图", r.retrievalPlan?.get("intent")?.toString() ?: "-")
                InsightRow("结果数", "${r.products.size} 个商品")
                InsightRow("证据", "${r.evidenceList.size} 条")
                InsightRow("Trace", "${r.traceSteps.size} 步")
                InsightRow("Harness", if (r.harnessReport?.get("passed")?.toString()?.lowercase() == "true") "通过" else "未通过/无数据")
                InsightRow("降级", if (r.fallbackStatus.isNullOrEmpty()) "无" else "L${r.fallbackStatus?.get("level")}")
                InsightRow("图片", if (r.visualResult != null) "有识别结果" else "无")
            }
        }
    }
}

@Composable
private fun InsightRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
        Text("$label：", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.width(80.dp))
        Text(value, style = MaterialTheme.typography.bodySmall)
    }
}

private data class ToolInfo(val name: String, val permission: String, val risk: String, val agent: String, val desc: String)
