package com.omnicart.agent.feature.chat

import android.Manifest
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import coil.compose.AsyncImage
import androidx.core.content.FileProvider
import androidx.lifecycle.viewmodel.compose.viewModel
import com.omnicart.agent.feature.demo.PlusMenuSheet
import com.omnicart.agent.feature.product.ProductCard
import com.omnicart.agent.feature.product.ProductDetailSheet
import com.omnicart.agent.feature.upload.ImagePreview
import java.io.File

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen(
    viewModel: ChatViewModel = viewModel(),
    modifier: Modifier = Modifier,
) {
    val uiState by viewModel.uiState.collectAsState()
    val context = LocalContext.current
    var showImageSourceDialog by remember { mutableStateOf(false) }
    var showPlusSheet by remember { mutableStateOf(false) }
    val snackbarHostState = remember { SnackbarHostState() }

    // 加购成功提示
    LaunchedEffect(uiState.addToCartSuccess) {
        uiState.addToCartSuccess?.let { title ->
            snackbarHostState.showSnackbar("「${title.take(20)}...」已加入购物车")
            viewModel.dismissAddToCartSuccess()
        }
    }

    val galleryLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.PickVisualMedia(),
    ) { uri -> if (uri != null) viewModel.onImageSelected(uri) }

    val cameraLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.TakePicturePreview(),
    ) { bitmap ->
        if (bitmap != null) {
            val file = File(context.cacheDir, "camera_${System.currentTimeMillis()}.jpg")
            file.parentFile?.mkdirs()
            try {
                file.outputStream().use { out ->
                    bitmap.compress(android.graphics.Bitmap.CompressFormat.JPEG, 90, out)
                }
                val uri = FileProvider.getUriForFile(context, "com.omnicart.agent.fileprovider", file)
                viewModel.onImageSelected(uri)
            } catch (_: Exception) { }
        }
    }

    val cameraPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission(),
    ) { granted -> if (granted) cameraLauncher.launch(null) }

    fun launchCamera() {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA)
            == android.content.pm.PackageManager.PERMISSION_GRANTED) {
            cameraLauncher.launch(null)
        } else {
            cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    fun launchGallery() {
        galleryLauncher.launch(PickVisualMediaRequest())
    }

    if (showImageSourceDialog) {
        AlertDialog(
            onDismissRequest = { showImageSourceDialog = false },
            title = { Text("选择图片来源") },
            text = {
                Column {
                    TextButton(onClick = { showImageSourceDialog = false; launchCamera() }, modifier = Modifier.fillMaxWidth()) {
                        Text("📷 拍照", style = MaterialTheme.typography.bodyLarge)
                    }
                    TextButton(onClick = { showImageSourceDialog = false; launchGallery() }, modifier = Modifier.fillMaxWidth()) {
                        Text("🖼️ 相册", style = MaterialTheme.typography.bodyLarge)
                    }
                }
            },
            confirmButton = {},
        )
    }

    if (showPlusSheet) {
        PlusMenuSheet(
            onDismiss = { showPlusSheet = false },
            onScenarioSelected = { query -> viewModel.onQueryChange(query) },
            onCameraClick = { launchCamera() },
            onGalleryClick = { launchGallery() },
        )
    }

    Box(modifier = modifier.fillMaxSize()) {
        Column(modifier = Modifier.fillMaxSize()) {
            // 顶栏
            Surface(color = MaterialTheme.colorScheme.surface, tonalElevation = 1.dp) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        "豆仔——您身边的购物小助手",
                        style = MaterialTheme.typography.titleMedium,
                        modifier = Modifier.weight(1f),
                    )
                    if (uiState.messages.isNotEmpty()) {
                        IconButton(onClick = { viewModel.onNewConversation() }) {
                            Icon(
                                Icons.Filled.Add,
                                contentDescription = "新对话",
                                tint = MaterialTheme.colorScheme.primary,
                            )
                        }
                    }
                }
            }

            Column(modifier = Modifier.fillMaxSize()) {
                val hasContent = uiState.messages.isNotEmpty() || uiState.isLoading || uiState.errorMessage != null

                if (hasContent) {
                    LazyColumn(
                        modifier = Modifier
                            .weight(1f)
                            .fillMaxWidth()
                            .padding(horizontal = 16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                        contentPadding = PaddingValues(vertical = 12.dp)
                    ) {
                        items(
                            items = uiState.messages,
                            key = { it.id }
                        ) { message ->
                            when (message.role) {
                                MessageRole.User -> {
                                    Column(horizontalAlignment = Alignment.End) {
                                        // 用户已发送图片
                                        uiState.lastSentImageUri?.let { imgUri ->
                                            AsyncImage(
                                                model = imgUri,
                                                contentDescription = "已发送图片",
                                                modifier = Modifier
                                                    .size(120.dp)
                                                    .clip(RoundedCornerShape(12.dp)),
                                                contentScale = ContentScale.Crop,
                                            )
                                            Spacer(modifier = Modifier.height(6.dp))
                                        }
                                        MessageBubble(
                                            text = message.text,
                                            type = BubbleType.User,
                                        )
                                    }
                                }
                                MessageRole.Assistant -> {
                                    Column {
                                        MessageBubble(
                                            text = message.text,
                                            type = BubbleType.Assistant,
                                        )
                                        if (message.hasProducts) {
                                            Spacer(modifier = Modifier.height(4.dp))
                                            Text(
                                                text = "为您找到 ${message.products.size} 款商品：",
                                                style = MaterialTheme.typography.labelLarge,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                                modifier = Modifier.padding(start = 36.dp),
                                            )
                                            Spacer(modifier = Modifier.height(4.dp))
                                        }
                                        message.products.forEach { product ->
                                            val decision = message.decisionResults.find {
                                                it.productId == product.productId
                                            }
                                            ProductCard(
                                                product = product,
                                                decisionResult = decision,
                                                onClick = { viewModel.onProductClick(product.productId) },
                                                onAddToCart = { viewModel.onAddToCart(product.productId, product.title) },
                                            )
                                            Spacer(modifier = Modifier.height(8.dp))
                                        }
                                    }
                                }
                            }
                        }

                        if (uiState.isLoading) {
                            item(key = "loading") {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    CircularProgressIndicator(modifier = Modifier.size(18.dp))
                                    Spacer(modifier = Modifier.width(12.dp))
                                    Text(
                                        text = "正在分析您的需求...",
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            }
                        }

                        uiState.errorMessage?.let { error ->
                            item(key = "error") {
                                Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
                                    Text(
                                        text = error,
                                        modifier = Modifier.padding(12.dp),
                                        color = MaterialTheme.colorScheme.onErrorContainer,
                                        style = MaterialTheme.typography.bodySmall
                                    )
                                }
                            }
                        }
                    }

                    // 详情弹窗
                    val selectedPid = uiState.selectedProductId
                    if (selectedPid != null && selectedPid.isNotEmpty()) {
                        val allProducts = uiState.messages.flatMap { it.products }
                        val allDecisions = uiState.messages.flatMap { it.decisionResults }
                        val allEvidence = uiState.messages.flatMap { it.evidenceList }
                        val allTraces = uiState.messages.flatMap { it.traceSteps }

                        val selectedProduct = allProducts.find { it.productId == selectedPid }
                        if (selectedProduct != null) {
                            val selectedDecision = allDecisions.find { it.productId == selectedPid }
                            ProductDetailSheet(
                                product = selectedProduct,
                                decisionResult = selectedDecision,
                                evidenceList = allEvidence.map { ev ->
                                    mapOf(
                                        "source_type" to ev.sourceType,
                                        "content" to ev.content,
                                        "confidence" to ev.confidence,
                                        "evidence_id" to ev.evidenceId,
                                    )
                                },
                                traceSteps = allTraces.map { ts ->
                                    mapOf(
                                        "agent_name" to ts.agentName,
                                        "action" to ts.action,
                                        "status" to ts.status,
                                        "latency_ms" to ts.latencyMs,
                                        "output_summary" to ts.outputSummary,
                                    )
                                },
                                harnessReport = uiState.messages.mapNotNull { it.harnessReport }.lastOrNull() ?: emptyMap(),
                                onDismiss = viewModel::onDismissDetail,
                            )
                        }
                    }
                } else {
                    // 空状态欢迎页
                    Box(
                        modifier = Modifier
                            .weight(1f)
                            .fillMaxWidth()
                            .padding(32.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                text = "豆仔",
                                style = MaterialTheme.typography.headlineMedium,
                                color = MaterialTheme.colorScheme.primary,
                                fontWeight = androidx.compose.ui.text.font.FontWeight.Bold
                            )
                            Spacer(modifier = Modifier.height(8.dp))
                            Text(
                                text = "您身边的购物小助手",
                                style = MaterialTheme.typography.bodyLarge,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Spacer(modifier = Modifier.height(8.dp))
                            Text(
                                text = "输入需求或上传商品截图\n获取专业的商品推荐与评分",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                textAlign = TextAlign.Center
                            )
                        }
                    }
                }

                // 图片预览
                uiState.selectedImageUri?.let { uri ->
                    ImagePreview(
                        uri = uri,
                        onRemove = viewModel::onImageRemoved,
                    )
                }

                // 底部输入栏
                ChatInputBar(
                    queryText = uiState.queryText,
                    onQueryChange = viewModel::onQueryChange,
                    onSend = viewModel::onSend,
                    onCameraClick = { showImageSourceDialog = true },
                    onPlusClick = { showPlusSheet = true },
                    enabled = !uiState.isLoading,
                    hasImage = uiState.selectedImageUri != null,
                    modifier = Modifier.imePadding(),
                )
            }
        }
        SnackbarHost(
            hostState = snackbarHostState,
            modifier = Modifier.align(Alignment.BottomCenter)
        )
    }
}
