package com.omnicart.agent.feature.address

import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.omnicart.agent.core.network.AddressItem

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddressScreen(
    onBack: () -> Unit = {},
    viewModel: AddressViewModel = viewModel(),
) {
    val uiState by viewModel.uiState.collectAsState()
    val snackbarHostState = remember { SnackbarHostState() }

    LaunchedEffect(Unit) {
        viewModel.loadAddresses()
    }

    LaunchedEffect(uiState.errorMessage) {
        uiState.errorMessage?.let {
            snackbarHostState.showSnackbar(it)
            viewModel.clearError()
        }
    }

    // 新增 / 编辑对话框
    if (uiState.showAddDialog) {
        AddressEditDialog(
            title = "新增地址",
            onDismiss = { viewModel.dismissAddDialog() },
            onSave = { name, phone, prov, city, dist, detail, isDef ->
                viewModel.saveAddress(name, phone, prov, city, dist, detail, isDef)
            },
        )
    }

    if (uiState.editingAddress != null) {
        val addr = uiState.editingAddress!!
        AddressEditDialog(
            title = "编辑地址",
            initialName = addr.name,
            initialPhone = addr.phone,
            initialProvince = addr.province,
            initialCity = addr.city,
            initialDistrict = addr.district,
            initialDetail = addr.detail,
            initialIsDefault = addr.isDefault,
            onDismiss = { viewModel.dismissEdit() },
            onSave = { name, phone, prov, city, dist, detail, isDef ->
                viewModel.saveAddress(name, phone, prov, city, dist, detail, isDef, editId = addr.addressId)
            },
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("收货地址") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Filled.ArrowBack, "返回")
                    }
                },
                actions = {
                    IconButton(onClick = { viewModel.showAddDialog() }) {
                        Icon(Icons.Filled.Add, "新增")
                    }
                },
            )
        },
        snackbarHost = { SnackbarHost(snackbarHostState) },
    ) { padding ->
        if (uiState.isLoading && uiState.addresses.isEmpty()) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                CircularProgressIndicator()
            }
        } else if (uiState.addresses.isEmpty()) {
            Box(Modifier.fillMaxSize().padding(padding), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(Icons.Filled.LocationOn, null, modifier = Modifier.size(48.dp), tint = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.height(8.dp))
                    Text("暂无收货地址", style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.height(8.dp))
                    OutlinedButton(onClick = { viewModel.showAddDialog() }) {
                        Text("添加新地址")
                    }
                }
            }
        } else {
            LazyColumn(modifier = Modifier.padding(padding)) {
                items(uiState.addresses, key = { it.addressId }) { addr ->
                    AddressCard(
                        addr = addr,
                        onEdit = { viewModel.startEdit(addr) },
                        onDelete = { viewModel.deleteAddress(addr.addressId) },
                    )
                    HorizontalDivider()
                }
            }
        }
    }
}

@Composable
private fun AddressCard(addr: AddressItem, onEdit: () -> Unit, onDelete: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (addr.isDefault)
                MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.2f)
            else MaterialTheme.colorScheme.surface
        ),
    ) {
        Row(modifier = Modifier.padding(16.dp)) {
            Column(modifier = Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(addr.name, fontWeight = FontWeight.Bold)
                    Spacer(Modifier.width(8.dp))
                    Text(addr.phone, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    if (addr.isDefault) {
                        Spacer(Modifier.width(8.dp))
                        SuggestionChip(
                            onClick = {},
                            label = { Text("默认", style = MaterialTheme.typography.labelSmall) },
                            modifier = Modifier.height(24.dp),
                        )
                    }
                }
                Spacer(Modifier.height(4.dp))
                Text(
                    "${addr.province}${addr.city}${addr.district}${addr.detail}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            IconButton(onClick = onEdit, modifier = Modifier.size(36.dp)) {
                Icon(Icons.Filled.Edit, "编辑", modifier = Modifier.size(20.dp))
            }
            IconButton(onClick = onDelete, modifier = Modifier.size(36.dp)) {
                Icon(Icons.Filled.Delete, "删除", modifier = Modifier.size(20.dp), tint = MaterialTheme.colorScheme.error)
            }
        }
    }
}

@Composable
private fun AddressEditDialog(
    title: String,
    initialName: String = "",
    initialPhone: String = "",
    initialProvince: String = "",
    initialCity: String = "",
    initialDistrict: String = "",
    initialDetail: String = "",
    initialIsDefault: Boolean = false,
    onDismiss: () -> Unit,
    onSave: (name: String, phone: String, province: String, city: String, district: String, detail: String, isDefault: Boolean) -> Unit,
) {
    var name by remember { mutableStateOf(initialName) }
    var phone by remember { mutableStateOf(initialPhone) }
    var province by remember { mutableStateOf(initialProvince) }
    var city by remember { mutableStateOf(initialCity) }
    var district by remember { mutableStateOf(initialDistrict) }
    var detail by remember { mutableStateOf(initialDetail) }
    var isDefault by remember { mutableStateOf(initialIsDefault) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("姓名") }, singleLine = true, modifier = Modifier.weight(1f))
                    OutlinedTextField(value = phone, onValueChange = { phone = it }, label = { Text("电话") }, singleLine = true, modifier = Modifier.weight(1f))
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(value = province, onValueChange = { province = it }, label = { Text("省") }, singleLine = true, modifier = Modifier.weight(1f))
                    OutlinedTextField(value = city, onValueChange = { city = it }, label = { Text("市") }, singleLine = true, modifier = Modifier.weight(1f))
                }
                OutlinedTextField(value = district, onValueChange = { district = it }, label = { Text("区") }, singleLine = true)
                OutlinedTextField(value = detail, onValueChange = { detail = it }, label = { Text("详细地址") }, singleLine = true)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(checked = isDefault, onCheckedChange = { isDefault = it })
                    Text("设为默认地址", style = MaterialTheme.typography.bodySmall)
                }
            }
        },
        confirmButton = {
            Button(onClick = { onSave(name, phone, province, city, district, detail, isDefault) }) {
                Text("保存")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("取消") }
        },
    )
}
