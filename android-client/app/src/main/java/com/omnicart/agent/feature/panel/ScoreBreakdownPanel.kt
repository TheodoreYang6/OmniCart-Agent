package com.omnicart.agent.feature.panel

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.omnicart.agent.core.model.ScoreBreakdown

@Composable
fun ScoreBreakdownPanel(breakdown: ScoreBreakdown?, finalScore: Double = 0.0, displayScore: Double = 0.0) {
    if (breakdown == null) return
    var showAll by remember { mutableStateOf(false) }

    val scoreColor = when {
        displayScore >= 8.0 -> Color(0xFF4CAF50)
        displayScore >= 6.0 -> Color(0xFFFF9800)
        else -> Color(0xFFFF5722)
    }

    Column {
        Row(Modifier.fillMaxWidth().clickable { showAll = !showAll }.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.Star, null, Modifier.size(20.dp), tint = scoreColor)
            Spacer(Modifier.width(8.dp))
            Text("评分细分", fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.weight(1f))
            Text(String.format("%.1f", displayScore), fontWeight = FontWeight.Bold,
                color = scoreColor, style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.width(4.dp))
            Icon(if (showAll) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore, null)
        }

        AnimatedVisibility(showAll) {
            Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
                ScoreRow("预算匹配", breakdown.budgetFit)
                ScoreRow("场景匹配", breakdown.scenarioFit)
                ScoreRow("规格匹配", breakdown.specMatch)
                ScoreRow("评论置信度", breakdown.reviewConfidence)
                ScoreRow("视觉相似度", breakdown.visualSimilarity)
                ScoreRow("可用性", breakdown.availabilityScore)
                ScoreRow("风险惩罚", breakdown.riskPenalty, isPenalty = true)
                HorizontalDivider(Modifier.padding(vertical = 4.dp))
                Row(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                    Text("综合评分", fontWeight = FontWeight.Bold)
                    Spacer(Modifier.weight(1f))
                    Text(String.format("%.3f", finalScore), fontWeight = FontWeight.Bold, color = scoreColor)
                }
            }
        }
    }
}

@Composable
private fun ScoreRow(label: String, value: Double, isPenalty: Boolean = false) {
    Row(Modifier.fillMaxWidth().padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, style = MaterialTheme.typography.bodySmall, modifier = Modifier.weight(1f))
        LinearProgressIndicator(
            progress = { value.toFloat().coerceIn(0f, 1f) },
            modifier = Modifier.width(80.dp).height(6.dp),
            color = when {
                isPenalty && value > 0.3f -> Color(0xFFFF5722)
                isPenalty -> Color(0xFF4CAF50)
                value >= 0.7f -> Color(0xFF4CAF50)
                value >= 0.4f -> Color(0xFFFF9800)
                else -> Color(0xFFFF5722)
            },
            trackColor = MaterialTheme.colorScheme.surfaceVariant,
        )
        Spacer(Modifier.width(8.dp))
        Text(String.format("%.2f", value), style = MaterialTheme.typography.labelSmall,
            modifier = Modifier.width(36.dp))
    }
}

