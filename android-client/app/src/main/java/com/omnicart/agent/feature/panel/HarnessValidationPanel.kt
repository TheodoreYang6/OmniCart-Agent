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

@Composable
fun HarnessValidationPanel(report: Map<String, Any?>?) {
    if (report == null || report.isEmpty()) return

    var showAll by remember { mutableStateOf(false) }

    val checks = listOf(
        "schema_valid" to "Schema 校验",
        "evidence_bound" to "证据绑定",
        "score_recalculable" to "评分可复算",
        "policy_cited" to "政策引用",
        "risk_warning" to "风险提醒",
    )

    Column {
        Row(Modifier.fillMaxWidth().clickable { showAll = !showAll }.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.VerifiedUser, null, Modifier.size(20.dp), tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(8.dp))
            Text("Harness 校验", fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.weight(1f))
            Icon(if (showAll) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore, null)
        }

        AnimatedVisibility(showAll) {
            Column(Modifier.padding(horizontal = 16.dp, vertical = 8.dp)) {
                checks.forEach { (key, label) ->
                    val passed = report[key] as? Boolean ?: (report[key]?.toString() == "true")
                    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            if (passed) Icons.Filled.CheckCircle else Icons.Filled.Cancel,
                            null, Modifier.size(18.dp),
                            tint = if (passed) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
                        )
                        Spacer(Modifier.width(8.dp))
                        Text(label, style = MaterialTheme.typography.bodySmall)
                        Spacer(Modifier.weight(1f))
                        Text(if (passed) "PASS" else "FAIL",
                            style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold,
                            color = if (passed) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error)
                    }
                }
                // Generic check items from report
                report.entries.filter { (k, _) -> k !in checks.map { it.first } }.forEach { (key, value) ->
                    Row(Modifier.fillMaxWidth().padding(vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Filled.Info, null, Modifier.size(18.dp))
                        Spacer(Modifier.width(8.dp))
                        Text(key, style = MaterialTheme.typography.bodySmall)
                        Spacer(Modifier.weight(1f))
                        Text(value.toString(), style = MaterialTheme.typography.labelSmall)
                    }
                }
            }
        }
    }
}

