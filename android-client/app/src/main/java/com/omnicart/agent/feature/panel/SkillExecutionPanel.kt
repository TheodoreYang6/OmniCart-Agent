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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/** 单条 Skill 执行记录 */
data class SkillExecutionRecord(
    val skillName: String = "",
    val description: String = "",
    val status: String = "success",
    val inputSummary: String = "",
    val outputSummary: String = "",
    val latencyMs: Int = 0,
) {
    companion object {
        fun fromMap(map: Map<*, *>): SkillExecutionRecord {
            return SkillExecutionRecord(
                skillName = map["skill_name"] as? String ?: map["name"] as? String ?: "",
                description = map["description"] as? String ?: "",
                status = map["status"] as? String ?: "success",
                inputSummary = map["input_summary"] as? String ?: "",
                outputSummary = map["output_summary"] as? String ?: "",
                latencyMs = (map["latency_ms"] as? Number)?.toInt() ?: 0,
            )
        }
    }
}

@Composable
fun SkillExecutionPanel(executions: List<Map<String, Any?>>) {
    if (executions.isEmpty()) return
    val records = executions.map { SkillExecutionRecord.fromMap(it) }
    var showAll by remember { mutableStateOf(false) }

    Column {
        Row(Modifier.fillMaxWidth().clickable { showAll = !showAll }.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.Build, null, Modifier.size(20.dp), tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(8.dp))
            Text("Skill 执行 (${records.size})", fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.weight(1f))
            Icon(if (showAll) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore, null)
        }

        AnimatedVisibility(showAll) {
            Column(Modifier.padding(horizontal = 8.dp)) {
                for (rec in records) {
                    Surface(Modifier.fillMaxWidth().padding(4.dp), shape = MaterialTheme.shapes.small, tonalElevation = 1.dp) {
                        Row(Modifier.padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
                            Icon(
                                when (rec.status) {
                                    "success" -> Icons.Filled.CheckCircle
                                    "failed" -> Icons.Filled.Error
                                    else -> Icons.Filled.HourglassEmpty
                                },
                                null, Modifier.size(18.dp),
                                tint = if (rec.status == "success") MaterialTheme.colorScheme.primary
                                       else MaterialTheme.colorScheme.error,
                            )
                            Spacer(Modifier.width(8.dp))
                            Column(Modifier.weight(1f)) {
                                Text(rec.skillName, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodySmall)
                                if (rec.description.isNotBlank())
                                    Text(rec.description, style = MaterialTheme.typography.labelSmall,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 2)
                            }
                            if (rec.latencyMs > 0)
                                Text("${rec.latencyMs}ms", style = MaterialTheme.typography.labelSmall)
                        }
                    }
                }
            }
        }
    }
}

