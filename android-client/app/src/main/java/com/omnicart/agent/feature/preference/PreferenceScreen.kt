package com.omnicart.agent.feature.preference

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PreferenceScreen(
    sessionId: String,
    onBack: () -> Unit = {},
    viewModel: PreferenceViewModel = viewModel(),
) {
    val uiState by viewModel.uiState.collectAsState()

    LaunchedEffect(sessionId) {
        viewModel.loadPreferences(sessionId)
    }

    LaunchedEffect(uiState.saved) {
        if (uiState.saved) {
            kotlinx.coroutines.delay(1500)
            viewModel.dismissSaved()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("偏好设置") },
                navigationIcon = { IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, "返回") } },
                actions = {
                    TextButton(onClick = { viewModel.savePreferences(sessionId) },
                        enabled = !uiState.isLoading) {
                        if (uiState.saved) Icon(Icons.Filled.Check, null, Modifier.size(18.dp))
                        else Text("保存")
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            if (uiState.errorMessage != null) {
                Text(uiState.errorMessage!!, color = MaterialTheme.colorScheme.error)
            }

            OutlinedTextField(
                value = uiState.category, onValueChange = viewModel::onCategoryChange,
                label = { Text("品类偏好") }, placeholder = { Text("如：数码电子、美妆护肤、食品饮料") },
                singleLine = true, modifier = Modifier.fillMaxWidth(),
            )
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(
                    value = uiState.budgetMin, onValueChange = viewModel::onBudgetMinChange,
                    label = { Text("最低预算") }, singleLine = true, modifier = Modifier.weight(1f),
                )
                OutlinedTextField(
                    value = uiState.budgetMax, onValueChange = viewModel::onBudgetMaxChange,
                    label = { Text("最高预算") }, singleLine = true, modifier = Modifier.weight(1f),
                )
            }
            OutlinedTextField(
                value = uiState.scenario, onValueChange = viewModel::onScenarioChange,
                label = { Text("使用场景") }, placeholder = { Text("如：出差旅行、日常通勤、运动健身") },
                singleLine = true, modifier = Modifier.fillMaxWidth(),
            )
            OutlinedTextField(
                value = uiState.mustTags, onValueChange = viewModel::onMustTagsChange,
                label = { Text("偏好标签（逗号分隔）") }, placeholder = { Text("如：轻便，快充，降噪") },
                singleLine = true, modifier = Modifier.fillMaxWidth(),
            )

            Spacer(Modifier.height(8.dp))
            Button(
                onClick = { viewModel.savePreferences(sessionId) },
                modifier = Modifier.fillMaxWidth(), enabled = !uiState.isLoading,
            ) {
                if (uiState.isLoading) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                else Text("保存偏好设置")
            }
        }
    }
}
