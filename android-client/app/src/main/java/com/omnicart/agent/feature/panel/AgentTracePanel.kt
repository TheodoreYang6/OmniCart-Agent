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
import com.omnicart.agent.core.model.TraceStepItem

@Composable
fun AgentTracePanel(traceSteps: List<TraceStepItem>) {
    var showAll by remember { mutableStateOf(false) }

    Column {
        Row(Modifier.fillMaxWidth().clickable { showAll = !showAll }.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.AccountTree, null, Modifier.size(20.dp), tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(8.dp))
            Text("Agent 链路 (${traceSteps.size} 步)", fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.weight(1f))
            Icon(if (showAll) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore, null)
        }

        AnimatedVisibility(showAll) {
            Column(modifier = Modifier.padding(horizontal = 8.dp)) {
                for (step in traceSteps) {
                    Row(Modifier.fillMaxWidth().padding(8.dp)) {
                        // 竖线连接器
                        Column(horizontalAlignment = Alignment.CenterHorizontally,
                            modifier = Modifier.width(32.dp)) {
                            Icon(
                                when (step.status) {
                                    "success", "pass" -> Icons.Filled.CheckCircle
                                    "failed", "insufficient" -> Icons.Filled.Error
                                    "fallback" -> Icons.Filled.Warning
                                    else -> Icons.Filled.RadioButtonUnchecked
                                },
                                null, Modifier.size(16.dp),
                                tint = when (step.status) {
                                    "success", "pass" -> MaterialTheme.colorScheme.primary
                                    "failed", "insufficient" -> MaterialTheme.colorScheme.error
                                    else -> MaterialTheme.colorScheme.onSurfaceVariant
                                },
                            )
                            Box(Modifier.width(2.dp).height(40.dp))
                        }
                        Column(Modifier.weight(1f)) {
                            Text("${step.stepId} ${step.agentName}",
                                style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold)
                            Text(step.action, style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant)
                            if (step.inputSummary.isNotBlank())
                                Text("入: ${step.inputSummary}", style = MaterialTheme.typography.bodySmall, maxLines = 1)
                            if (step.outputSummary.isNotBlank())
                                Text("出: ${step.outputSummary}", style = MaterialTheme.typography.bodySmall, maxLines = 1)
                        }
                    }
                }
            }
        }
    }
}

