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
import com.omnicart.agent.core.model.EvidenceItem

@Composable
fun EvidencePanel(evidenceList: List<EvidenceItem>, expanded: Boolean = false) {
    var showAll by remember { mutableStateOf(expanded) }

    Column {
        Row(Modifier.fillMaxWidth().clickable { showAll = !showAll }.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Filled.Policy, null, Modifier.size(20.dp), tint = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.width(8.dp))
            Text("证据列表 (${evidenceList.size})", fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.weight(1f))
            Icon(if (showAll) Icons.Filled.ExpandLess else Icons.Filled.ExpandMore, null)
        }

        AnimatedVisibility(showAll) {
            Column(modifier = Modifier.padding(horizontal = 8.dp)) {
                for (ev in evidenceList.take(20)) {
                    Surface(
                        modifier = Modifier.fillMaxWidth().padding(4.dp),
                        shape = MaterialTheme.shapes.small,
                        tonalElevation = 1.dp,
                    ) {
                        Row(Modifier.padding(10.dp), verticalAlignment = Alignment.Top) {
                            Icon(iconForSource(ev.sourceType), null, Modifier.size(16.dp).padding(top = 2.dp),
                                tint = colorForSource(ev.sourceType))
                            Spacer(Modifier.width(8.dp))
                            Column(Modifier.weight(1f)) {
                                Text(ev.evidenceId, style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Text(ev.content.take(120), style = MaterialTheme.typography.bodySmall, maxLines = 3)
                                if (ev.confidence > 0) {
                                    Text("置信度: ${(ev.confidence * 100).toInt()}%",
                                        style = MaterialTheme.typography.labelSmall,
                                        color = if (ev.confidence >= 0.7) MaterialTheme.colorScheme.primary
                                                else MaterialTheme.colorScheme.error)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

private val SourceIcons = mapOf(
    "text_retrieval" to Icons.Filled.Search,
    "review_positive" to Icons.Filled.ThumbUp,
    "review_risk" to Icons.Filled.Warning,
    "policy_faq" to Icons.Filled.Gavel,
    "visual" to Icons.Filled.Image,
)
private val SourceColors = mapOf(
    "text_retrieval" to androidx.compose.ui.graphics.Color(0xFF2196F3),
    "review_positive" to androidx.compose.ui.graphics.Color(0xFF4CAF50),
    "review_risk" to androidx.compose.ui.graphics.Color(0xFFFF5722),
    "policy_faq" to androidx.compose.ui.graphics.Color(0xFF9C27B0),
)

@Composable
private fun iconForSource(type: String) = SourceIcons[type] ?: Icons.Filled.Info

@Composable
private fun colorForSource(type: String) = SourceColors[type] ?: MaterialTheme.colorScheme.onSurfaceVariant

