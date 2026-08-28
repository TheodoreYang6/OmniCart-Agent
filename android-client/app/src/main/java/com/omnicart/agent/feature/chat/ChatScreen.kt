package com.omnicart.agent.feature.chat

import android.Manifest
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.compose.ui.text.font.FontWeight
import com.omnicart.agent.core.theme.Primary
import com.omnicart.agent.core.theme.OnPrimary
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.Refresh
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
import com.omnicart.agent.feature.auth.AuthManager
import com.omnicart.agent.feature.demo.PlusMenuSheet
import com.omnicart.agent.feature.product.ProductCard
import com.omnicart.agent.feature.product.ProductImage
import com.omnicart.agent.feature.product.ProductDetailSheet
import com.omnicart.agent.feature.upload.ImagePreview
import com.omnicart.agent.core.design.OmiLogo
import java.io.File

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen(
    sessionId: String = "",
    userId: String = "",
    viewModel: ChatViewModel = viewModel(),
    modifier: Modifier = Modifier,
    askDouzaiProductId: String = "",
    askDouzaiTitle: String = "",
    onAskDouzaiConsumed: () -> Unit = {},
    onProductClick: (String) -> Unit = {},
    onNavigateToAddress: () -> Unit = {},
) {
    LaunchedEffect(sessionId) {
        if (sessionId.isNotBlank() && viewModel.uiState.value.sessionId != sessionId) {
            viewModel.setSessionId(sessionId)
        }
    }
    // 问问小O：自动发送聚焦分析
    LaunchedEffect(askDouzaiProductId) {
        if (askDouzaiProductId.isNotBlank()) {
            viewModel.sendAskDouzai(askDouzaiProductId, askDouzaiTitle)
            onAskDouzaiConsumed()
        }
    }
    var previousUserId by remember { mutableStateOf(userId) }
    LaunchedEffect(userId) {
        if (userId.isNotBlank() && userId != previousUserId) {
            viewModel.onUserChanged()
        }
        previousUserId = userId
    }
    val uiState by viewModel.uiState.collectAsState()
    val context = LocalContext.current
    var showImageSourceDialog by remember { mutableStateOf(false) }
    var showPlusSheet by remember { mutableStateOf(false) }
    val snackbarHostState = remember { SnackbarHostState() }
    val listState = rememberLazyListState()

    // 自动滚动到底部（新消息 + 流式输出时都触发）
    LaunchedEffect(uiState.messages.size, uiState.isLoading, uiState.streamingText.length, uiState.recommendationStage) {
        if (uiState.messages.isNotEmpty() || uiState.streamingText.isNotEmpty()) {
            // Streaming/status entries live after the persistent messages.  Using
            // messages.size - 1 left the live assistant bubble below the viewport,
            // which made Android appear not to stream even while tokens arrived.
            kotlinx.coroutines.delay(24)
            val target = (listState.layoutInfo.totalItemsCount - 1).coerceAtLeast(0)
            listState.animateScrollToItem(target)
        }
    }

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
            val file = File(context.cacheDir, "camera/camera_${System.currentTimeMillis()}.jpg")
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

    val audioPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission(),
    ) { granted -> if (granted) viewModel.startRecording() }

    val cameraPermissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission(),
    ) { granted -> if (granted) cameraLauncher.launch(null) }

    fun launchVoice() {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO)
            == android.content.pm.PackageManager.PERMISSION_GRANTED) {
            viewModel.startRecording()
        } else {
            audioPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
        }
    }

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
                        Text("拍照", style = MaterialTheme.typography.bodyLarge)
                    }
                    TextButton(onClick = { showImageSourceDialog = false; launchGallery() }, modifier = Modifier.fillMaxWidth()) {
                        Text("相册", style = MaterialTheme.typography.bodyLarge)
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

    // IME 位移由外层 Scaffold 统一承担，让输入栏与底部导航保持同步。
    Box(modifier = modifier.fillMaxSize()) {
        Column(modifier = Modifier.fillMaxSize()) {
            // 顶栏与 Web 端同样采用清透展台，而不是整块高饱和色条。
            Surface(
                color = MaterialTheme.colorScheme.surface.copy(alpha = 0.94f),
                tonalElevation = 0.dp,
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    OmiLogo(size = 42.dp, contentDescription = "欧米")
                    Spacer(Modifier.width(10.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            "欧米 · 购物智能体",
                            style = MaterialTheme.typography.titleMedium,
                            color = MaterialTheme.colorScheme.onSurface,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            "懂你想买什么，帮你挑得更合适",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    // 偏好生效指示
                    if (uiState.profileEnabled) {
                        Spacer(Modifier.width(8.dp))
                        Surface(
                            shape = RoundedCornerShape(12.dp),
                            color = MaterialTheme.colorScheme.primaryContainer,
                        ) {
                            Row(
                                Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Icon(
                                    Icons.Filled.Star,
                                    null,
                                    Modifier.size(12.dp),
                                    tint = MaterialTheme.colorScheme.primary,
                                )
                                Spacer(Modifier.width(4.dp))
                                Text(
                                    "偏好生效",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onPrimaryContainer,
                                )
                            }
                        }
                    }
                    // 新对话按钮
                    if (uiState.messages.isNotEmpty()) {
                        IconButton(onClick = { viewModel.onNewConversation() }) {
                            Icon(
                                Icons.Filled.Add,
                                contentDescription = "新对话",
                                tint = MaterialTheme.colorScheme.primary,
                            )
                        }
                    }
                    // 历史按钮 — 仅登录用户可见
                    if (AuthManager.userId.isNotBlank()) {
                        IconButton(onClick = { viewModel.toggleHistorySheet() }) {
                            Icon(
                                Icons.Filled.Refresh,
                                contentDescription = "历史聊天",
                                tint = MaterialTheme.colorScheme.primary,
                            )
                        }
                    }
                }
            }

            Column(modifier = Modifier.fillMaxSize()) {
                val hasContent = uiState.messages.isNotEmpty() || uiState.isLoading || uiState.isLoadingConversation || uiState.errorMessage != null

                if (hasContent) {
                    LazyColumn(
                        state = listState,
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
                                        if (message.isTranscribing) {
                                            // 语音转写中 loading 指示器
                                            Row(verticalAlignment = Alignment.CenterVertically) {
                                                CircularProgressIndicator(
                                                    modifier = Modifier.size(14.dp),
                                                    strokeWidth = 2.dp,
                                                    color = MaterialTheme.colorScheme.primary,
                                                )
                                                Spacer(Modifier.width(8.dp))
                                                Text(
                                                    "语音识别中...",
                                                    style = MaterialTheme.typography.bodyMedium,
                                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                                )
                                            }
                                            Spacer(Modifier.height(8.dp))
                                        }
                                        // 用户已发送图片（仅当前消息的图片）
                                        message.imageUri?.let { imgUri ->
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
                                        if (message.isVoice) {
                                            // 语音消息标识
                                            Row(verticalAlignment = Alignment.CenterVertically) {
                                                Icon(
                                                    Icons.Filled.Mic,
                                                    contentDescription = null,
                                                    tint = MaterialTheme.colorScheme.primary,
                                                    modifier = Modifier.size(16.dp),
                                                )
                                                Spacer(Modifier.width(4.dp))
                                                Text(
                                                    "语音输入",
                                                    style = MaterialTheme.typography.labelSmall,
                                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                                )
                                            }
                                            Spacer(Modifier.height(2.dp))
                                        }
                                        MessageBubble(
                                            text = message.text,
                                            type = BubbleType.User,
                                        )
                                    }
                                }
                                MessageRole.Assistant -> {
                                    Column {
                                        var showAlternatives by remember(message.id) { mutableStateOf(false) }
                                        MessageBubble(
                                            text = message.text,
                                            type = BubbleType.Assistant,
                                        )
                                        message.productResolution?.get("label")?.toString()
                                            ?.takeIf { it.isNotBlank() }?.let { label ->
                                                Text(
                                                    text = label,
                                                    style = MaterialTheme.typography.labelMedium,
                                                    color = MaterialTheme.colorScheme.primary,
                                                    modifier = Modifier.padding(start = 36.dp, top = 6.dp, bottom = 2.dp),
                                                )
                                            }
                                        message.visualResult?.let { visual ->
                                            VisualRecognitionSummary(visual, modifier = Modifier.padding(start = 36.dp, top = 4.dp))
                                        }
                                        // 对比与单品档案是两个明确的交付形态：单品档案不再
                                        // 被误当成对比表，也不会和通用商品卡重复出现。
                                        if (message.hasComparison) {
                                            Spacer(modifier = Modifier.height(6.dp))
                                            ComparisonCardForMessage(message)
                                        }
                                        val focus = message.resolvedFocusAnalysis
                                        if (focus != null && !message.hasComparison) {
                                            Spacer(modifier = Modifier.height(6.dp))
                                            FocusAnalysisCard(
                                                analysis = focus,
                                                onCompare = {
                                                    val productId = focus["product_id"]?.toString().orEmpty()
                                                    val title = focus["title"]?.toString().orEmpty()
                                                    if (productId.isNotBlank() && title.isNotBlank()) {
                                                        viewModel.sendAskDouzai(productId, title, comparison = true)
                                                    }
                                                },
                                            )
                                        }
                                        if (message.hasProducts && focus == null && !message.hasComparison) {
                                            Spacer(modifier = Modifier.height(4.dp))
                                            Text(
                                                text = "欧米为你优先挑了 ${message.products.size} 款",
                                                style = MaterialTheme.typography.labelLarge,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                                modifier = Modifier.padding(start = 36.dp),
                                            )
                                            Spacer(modifier = Modifier.height(4.dp))
                                        }
                                        if (focus == null && !message.hasComparison) message.products.forEachIndexed { index, product ->
                                            val decision = message.decisionResults.find {
                                                it.productId == product.productId
                                            }
                                            androidx.compose.animation.AnimatedVisibility(
                                                visible = true,
                                                enter = androidx.compose.animation.fadeIn() +
                                                        androidx.compose.animation.slideInVertically(
                                                            initialOffsetY = { it / 8 }
                                                        ),
                                            ) {
                                                ProductCard(
                                                    product = product,
                                                    decisionResult = decision,
                                                    onClick = { onProductClick(product.productId) },
                                                    onAddToCart = { skuId, skuLabel, skuPrice ->
                                                        viewModel.onAddToCart(product.productId, product.title, skuId, skuLabel, skuPrice)
                                                    },
                                                    onAskAgent = { viewModel.sendAskDouzai(product.productId, product.title) },
                                                    onScoreDetail = { viewModel.onProductClick(product.productId) },
                                                    modifier = Modifier.padding(start = 36.dp),
                                                )
                                            }
                                            Spacer(modifier = Modifier.height(8.dp))
                                        }
                                        if (focus == null && !message.hasComparison && message.recommendationAlternatives.isNotEmpty()) {
                                            Text(
                                                text = if (showAlternatives) "收起其他选择" else "再看看其他选择（${message.recommendationAlternatives.size}）",
                                                style = MaterialTheme.typography.labelLarge,
                                                color = MaterialTheme.colorScheme.primary,
                                                modifier = Modifier.padding(start = 36.dp, top = 2.dp, bottom = 6.dp)
                                                    .clickable { showAlternatives = !showAlternatives },
                                            )
                                            if (showAlternatives) {
                                                message.recommendationAlternatives.forEach { product ->
                                                    val decision = message.decisionResults.find { it.productId == product.productId }
                                                    ProductCard(
                                                        product = product,
                                                        decisionResult = decision,
                                                        onClick = { onProductClick(product.productId) },
                                                        onAddToCart = { skuId, skuLabel, skuPrice ->
                                                            viewModel.onAddToCart(product.productId, product.title, skuId, skuLabel, skuPrice)
                                                        },
                                                        onAskAgent = { viewModel.sendAskDouzai(product.productId, product.title) },
                                                        onScoreDetail = { viewModel.onProductClick(product.productId) },
                                                        modifier = Modifier.padding(start = 36.dp, bottom = 8.dp),
                                                    )
                                                }
                                            }
                                        }
                                        if (message.needsClarification && message.clarificationOptions.isNotEmpty()) {
                                            Spacer(modifier = Modifier.height(6.dp))
                                            ClarificationChips(
                                                question = message.clarificationQuestion,
                                                options = message.clarificationOptions,
                                                onSelect = { viewModel.onQueryChange(it); viewModel.onSend() },
                                            )
                                        }
                                        if (message.actions.isNotEmpty()) {
                                            Spacer(modifier = Modifier.height(6.dp))
                                            ShopActionButtons(
                                                actions = message.actions,
                                                onAddressForm = onNavigateToAddress,
                                                onQuickReply = { viewModel.onQueryChange(it); viewModel.onSend() },
                                            )
                                        }
                                    }
                                }
                            }
                        }

                        if (uiState.isLoadingConversation) {
                            item(key = "load_conv") {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    CircularProgressIndicator(modifier = Modifier.size(18.dp))
                                    Spacer(modifier = Modifier.width(12.dp))
                                    Text(
                                        text = "正在恢复历史会话...",
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            }
                        }

                        // 加载指示器 (统一入口，不重复)
                        if (uiState.isLoading || (uiState.isStreamingText && uiState.streamingText.isEmpty())) {
                            item(key = "loading") {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    CircularProgressIndicator(modifier = Modifier.size(18.dp))
                                    Spacer(modifier = Modifier.width(12.dp))
                                    Text(
                                        text = uiState.loadingMessage.ifBlank { "欧米正在分析…" },
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
                            }
                        }

                        // 与 Web 保持同一交付顺序：SSE 的推荐简报仅用于锁定范围，
                        // 不能在实时文字前抢占出商品卡。图片识别可以给一个轻状态，
                        // 完整识别信息则随最终消息一并落盘、展示。
                        uiState.streamingVisualResult?.let { visual ->
                            item(key = "streaming_visual_result") {
                                val facts = listOf("brand", "product_name", "product_line", "model", "category")
                                    .mapNotNull { visual[it]?.toString()?.trim()?.takeIf(String::isNotBlank) }
                                    .distinct()
                                val label = uiState.streamingVisualResolution?.get("label")?.toString()
                                    ?.takeIf { it.isNotBlank() }
                                    ?: if (facts.isNotEmpty()) "已识别图片线索，正在核对商品目录" else "正在核对图片中的商品线索"
                                AssistChip(
                                    onClick = {},
                                    label = { Text(label, maxLines = 1) },
                                    leadingIcon = { Icon(Icons.Filled.AutoAwesome, null, Modifier.size(15.dp)) },
                                    modifier = Modifier.padding(start = 36.dp, bottom = 4.dp),
                                )
                            }
                        }

                        // 打字机流式文字
                        if (uiState.isStreamingText && uiState.streamingText.isNotEmpty()) {
                            item(key = "streaming_text") {
                                MessageBubble(
                                    text = uiState.streamingText,
                                    type = BubbleType.Assistant,
                                )
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

                    // 详情弹窗 — 只取选中商品所在消息的数据，不跨消息泄漏
                    val selectedPid = uiState.selectedProductId
                    if (selectedPid != null && selectedPid.isNotEmpty()) {
                        // 找到包含该商品的最后一条消息
                        val ownerMessage = uiState.messages.findLast { msg ->
                            msg.products.any { it.productId == selectedPid }
                        }
                        val selectedProduct = ownerMessage?.products?.find { it.productId == selectedPid }
                        if (selectedProduct != null && ownerMessage != null) {
                            val selectedDecision = ownerMessage.decisionResults.find { it.productId == selectedPid }
                            ProductDetailSheet(
                                product = selectedProduct,
                                decisionResult = selectedDecision,
                                evidenceList = ownerMessage.evidenceList
                                    .filter { it.productId == selectedPid || it.productId == null }
                                    .map { ev ->
                                        mapOf(
                                            "source_type" to ev.sourceType,
                                            "content" to ev.content,
                                            "confidence" to ev.confidence,
                                            "evidence_id" to ev.evidenceId,
                                        )
                                    },
                                traceSteps = ownerMessage.traceSteps.map { ts ->
                                    mapOf(
                                        "agent_name" to ts.agentName,
                                        "action" to ts.action,
                                        "status" to ts.status,
                                        "latency_ms" to ts.latencyMs,
                                        "output_summary" to ts.outputSummary,
                                    )
                                },
                                harnessReport = ownerMessage.harnessReport ?: emptyMap(),
                                onDismiss = viewModel::onDismissDetail,
                                onAddToCart = { skuId, skuLabel, skuPrice ->
                                    viewModel.onAddToCart(selectedPid, selectedProduct.title, skuId, skuLabel, skuPrice)
                                },
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
                            OmiLogo(size = 88.dp, contentDescription = "欧米")
                            Spacer(modifier = Modifier.height(18.dp))
                            Text(
                                text = "你好，我是欧米",
                                style = MaterialTheme.typography.headlineMedium,
                                color = MaterialTheme.colorScheme.onBackground,
                                fontWeight = androidx.compose.ui.text.font.FontWeight.Bold
                            )
                            Spacer(modifier = Modifier.height(8.dp))
                            Text(
                                text = "你的购物智能体，陪你挑到更合适的商品",
                                style = MaterialTheme.typography.bodyLarge,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Spacer(modifier = Modifier.height(12.dp))
                            Text(
                                text = "告诉我预算、用途或喜欢的品牌\n也可以上传商品截图，让欧米帮你看一看",
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
                    onSend = { viewModel.onSend() },
                    onCameraClick = { showImageSourceDialog = true },
                    onPlusClick = { showPlusSheet = true },
                    onVoiceStart = { launchVoice() },
                    onVoiceEnd = { viewModel.stopRecordingAndSend() },
                    onVoiceCancel = { viewModel.cancelRecording() },
                    enabled = !uiState.isLoading,
                    hasImage = uiState.selectedImageUri != null,
                    isRecording = uiState.isRecording,
                    deepThink = uiState.deepThink,
                    onDeepThinkToggle = { viewModel.toggleDeepThink() },
                    modifier = Modifier,
                )
            }
        }
        SnackbarHost(
            hostState = snackbarHostState,
            modifier = Modifier.align(Alignment.BottomCenter)
        )

        // 全屏语音输入覆盖层
        if (uiState.showVoiceOverlay) {
            VoiceInputOverlay(
                isRecording = uiState.isRecording,
                recordingSeconds = uiState.recordingSeconds,
                onCancel = { viewModel.cancelRecording() },
            )
        }

        // 历史聊天列表 (Memory Lite P3)
        if (uiState.showHistorySheet) {
            ConversationListSheet(
                conversations = uiState.conversations,
                isLoading = uiState.isLoadingHistory,
                onSelect = { conv -> viewModel.loadConversation(conv.conversationId) },
                onNewConversation = { viewModel.onNewConversation() },
                onDismiss = { viewModel.toggleHistorySheet() },
                onDelete = { conv -> viewModel.deleteConversation(conv.conversationId) },
            )
        }
    }
}

@Composable
fun ConstraintChipsRow(
    options: List<ConstraintOption>,
    onSelected: (ConstraintOption) -> Unit,
) {
    Surface(
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f),
        tonalElevation = 1.dp,
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .horizontalScroll(rememberScrollState())
                .padding(horizontal = 12.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            options.forEach { option ->
                SuggestionChip(
                    onClick = { onSelected(option) },
                    label = {
                        Text(
                            text = option.label,
                            style = MaterialTheme.typography.labelLarge,
                        )
                    },
                    shape = RoundedCornerShape(20.dp),
                )
            }
        }
    }
}

// ---- P2-2: "问问小O" 对比分析卡片 ----

/** 目标商品分析区块 (共用) */
@Composable
fun TargetProductSection(a: Map<String, Any?>) {
    val title = a["title"]?.toString() ?: ""
    val brand = a["brand"]?.toString() ?: ""
    val price = (a["price"] as? Number)?.toDouble() ?: 0.0
    val level = a["recommendation_level"]?.toString() ?: ""
    val levelCN = when (level) {
        "strong_recommend" -> "高度匹配"
        "recommended" -> "较匹配"
        "worth_considering" -> "有条件匹配"
        "cautious" -> "有条件匹配"
        "insufficient_evidence" -> "信息有限"
        "not_recommended" -> "暂不建议优先"
        else -> level
    }
    val suitable = a["suitable_for"] as? List<*> ?: emptyList<Any>()
    val strengths = a["strengths"] as? List<*> ?: emptyList<Any>()
    val risks = a["risks"] as? List<*> ?: emptyList<Any>()
    val skuAdvice = a["sku_advice"]?.toString() ?: ""

    Surface(shape = RoundedCornerShape(10.dp), color = MaterialTheme.colorScheme.surface) {
        Column(Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("$brand $title".take(30),
                    style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f))
                Text("¥${price.toInt()}",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.error)
            }
            Spacer(Modifier.height(4.dp))
            Row {
                Text("欧米判断：$levelCN",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.primary)
            }
            if (suitable.isNotEmpty()) {
                Spacer(Modifier.height(6.dp))
                Text("适合人群: ${suitable.joinToString(", ")}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (strengths.isNotEmpty()) {
                strengths.take(3).forEach { s ->
                    Row(Modifier.padding(top = 2.dp)) {
                        Text("+ ${s.toString().take(60)}",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.primary)
                    }
                }
            }
            if (risks.isNotEmpty()) {
                risks.take(2).forEach { r ->
                    Row(Modifier.padding(top = 2.dp)) {
                        Text("- ${r.toString().take(60)}",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.error)
                    }
                }
            }
            if (skuAdvice.isNotBlank()) {
                Spacer(Modifier.height(4.dp))
                Text(skuAdvice, style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

/** Mobile counterpart of Web's product dossier card.  It is intentionally a
 * compact decision aid rather than a spreadsheet: identity, who it suits,
 * cautions, then one explicit comparison action. */
@Composable
private fun FocusAnalysisCard(analysis: Map<String, Any?>, onCompare: () -> Unit) {
    val productId = analysis["product_id"]?.toString().orEmpty()
    val title = analysis["title"]?.toString().orEmpty()
    val brand = analysis["brand"]?.toString().orEmpty()
    val price = (analysis["price"] as? Number)?.toDouble()
    val imageUrl = analysis["image_url"]?.toString()
    val suitable = (analysis["suitable_for"] as? List<*>)
        ?.mapNotNull { it?.toString()?.takeIf(String::isNotBlank) }.orEmpty()
    val highlights = (analysis["strengths"] as? List<*>)
        ?.mapNotNull { it?.toString()?.takeIf(String::isNotBlank) }.orEmpty()
    val cautions = (analysis["risks"] as? List<*>)
        ?.mapNotNull { it?.toString()?.takeIf(String::isNotBlank) }.orEmpty()
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = androidx.compose.foundation.BorderStroke(
            1.dp, MaterialTheme.colorScheme.outlineVariant.copy(alpha = 0.56f),
        ),
        shape = RoundedCornerShape(16.dp),
    ) {
        Column(Modifier.padding(12.dp)) {
            Text("欧米的商品分析", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.height(8.dp))
            Row(verticalAlignment = Alignment.Top) {
                ProductImage(
                    imageUrl = imageUrl,
                    productId = productId,
                    contentDescription = title,
                    modifier = Modifier.size(92.dp),
                    cornerRadius = 12.dp,
                )
                Spacer(Modifier.width(10.dp))
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    if (brand.isNotBlank()) Text(brand, style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary)
                    Text(title.ifBlank { "已锁定的商品" }, style = MaterialTheme.typography.bodyMedium,
                        fontWeight = FontWeight.Bold, maxLines = 2, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                    price?.let { Text("¥${if (it % 1.0 == 0.0) it.toInt() else it}",
                        style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.error) }
                    if (suitable.isNotEmpty()) Text("适合：${suitable.take(2).joinToString("、")}",
                        style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 2, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                }
            }
            if (highlights.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                Text("适合你的点：${highlights.take(2).joinToString("；")}", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (cautions.isNotEmpty()) {
                Spacer(Modifier.height(4.dp))
                Text("购买前留意：${cautions.take(1).joinToString()}", style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error)
            }
            Spacer(Modifier.height(10.dp))
            OutlinedButton(
                onClick = onCompare,
                shape = RoundedCornerShape(12.dp),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Icon(Icons.Filled.AutoAwesome, contentDescription = null, modifier = Modifier.size(16.dp))
                Spacer(Modifier.width(6.dp))
                Text("与同类横向对比")
            }
        }
    }
}

/** 对比表格区块 (共用) */
@Composable
fun ComparisonTableSection(comp: Map<String, Any?>, alternatives: List<Map<String, Any?>>?) {
    val dims = comp["dimensions"] as? List<*> ?: return
    val targetVals = comp["target_values"] as? List<*> ?: return
    val altVals = comp["alternative_values"] as? List<*> ?: emptyList<Any>()

    Text("同类对比", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold)
    Spacer(Modifier.height(6.dp))

    Row(Modifier.fillMaxWidth().background(
        MaterialTheme.colorScheme.primary.copy(alpha = 0.1f),
        RoundedCornerShape(6.dp)
    ).padding(8.dp)) {
        Text("维度", Modifier.weight(1f), style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold)
        Text("目标品", Modifier.weight(1f), style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary)
        alternatives?.forEachIndexed { i, alt ->
            val name = alt?.get("brand")?.toString()?.take(6) ?: "替代${i+1}"
            Text(name, Modifier.weight(1f), style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Bold, maxLines = 1)
        }
    }
    dims.forEachIndexed { dimIdx, dim ->
        Row(Modifier.fillMaxWidth().padding(vertical = 4.dp, horizontal = 8.dp)) {
            Text(dim.toString(), Modifier.weight(1f),
                style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.SemiBold)
            Text((targetVals.getOrNull(dimIdx)?.toString() ?: "-"),
                Modifier.weight(1f),
                style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
            alternatives?.forEachIndexed { altIdx, _ ->
                val altRow = altVals.getOrNull(altIdx) as? List<*> ?: emptyList<Any>()
                Text((altRow.getOrNull(dimIdx)?.toString() ?: "-"),
                    Modifier.weight(1f),
                    style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}

/** 从 ChatMessage 渲染对比卡片 (持久化) */
@Composable
fun ComparisonCardForMessage(message: ChatMessage) {
    if (!message.hasComparison) return
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.2f)),
        shape = RoundedCornerShape(14.dp),
    ) {
        Column(Modifier.padding(14.dp)) {
            Text("对比分析",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.height(8.dp))
            message.targetProductAnalysis?.let { a -> TargetProductSection(a) }
            message.comparisonTable?.let { c -> ComparisonTableSection(c, message.analysisAlternatives) }
            message.comparison?.let { comparison -> CanonicalComparisonSection(comparison) }
        }
    }
}

@Composable
private fun VisualRecognitionSummary(visual: Map<String, Any?>, modifier: Modifier = Modifier) {
    val pieces = listOf("brand", "product_name", "product_line", "model", "specs", "category")
        .mapNotNull { visual[it]?.toString()?.trim()?.takeIf(String::isNotBlank) }
        .distinct()
    if (pieces.isEmpty()) return
    Text(
        text = "图中识别到：${pieces.joinToString(" · ").take(72)}",
        style = MaterialTheme.typography.labelMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = modifier,
    )
}

@Composable
private fun CanonicalComparisonSection(comparison: Map<String, Any?>) {
    val target = comparison["target"] as? Map<*, *> ?: return
    val alternatives = comparison["alternatives"] as? List<*> ?: emptyList<Any>()
    val verdict = comparison["verdict"] as? Map<*, *>
    val dimensions = (comparison["dimensions"] as? List<*>)
        ?.mapNotNull { it?.toString()?.takeIf(String::isNotBlank) }.orEmpty()
    val winnerId = verdict?.get("winner_id")?.toString().orEmpty()
    verdict?.get("text")?.toString()?.takeIf { it.isNotBlank() }?.let { text ->
        Surface(
            color = MaterialTheme.colorScheme.primary,
            shape = RoundedCornerShape(12.dp),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Column(Modifier.padding(12.dp)) {
                Text(text, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.onPrimary)
                (verdict["reasons"] as? List<*>)?.mapNotNull { it?.toString() }?.take(3)
                    ?.takeIf { it.isNotEmpty() }?.let { reasons ->
                        Text(reasons.joinToString(" · "), style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.82f), modifier = Modifier.padding(top = 4.dp))
                    }
            }
        }
    }
    Spacer(Modifier.height(8.dp))
    Row(
        modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        listOf(target).plus(alternatives.take(3).mapNotNull { it as? Map<*, *> }).forEachIndexed { index, item ->
            ComparisonItemCard(
                item = item,
                dimensions = dimensions,
                isWinner = item["product_id"]?.toString() == winnerId,
                label = if (index == 0) "正在比较" else "备选 ${index}",
            )
        }
    }
}

@Composable
private fun ComparisonItemCard(
    item: Map<*, *>, dimensions: List<String>, isWinner: Boolean, label: String,
) {
    val title = item["title"]?.toString().orEmpty()
    val brand = item["brand"]?.toString().orEmpty()
    val productId = item["product_id"]?.toString().orEmpty()
    val price = item["price"]?.toString()?.takeIf { it.isNotBlank() } ?: "—"
    val image = item["image_url"]?.toString()
    val attributes = item["attributes"] as? Map<*, *> ?: emptyMap<Any, Any>()
    val highlights = (item["highlights"] as? List<*>)?.mapNotNull { it?.toString() }.orEmpty()
    val caution = (item["cautions"] as? List<*>)?.firstOrNull()?.toString().orEmpty()
    Card(
        modifier = Modifier.width(236.dp),
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = androidx.compose.foundation.BorderStroke(
            if (isWinner) 2.dp else 1.dp,
            if (isWinner) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outlineVariant,
        ),
    ) {
        Column {
            Box {
                ProductImage(image, title, productId, Modifier.fillMaxWidth().height(142.dp), cornerRadius = 0.dp)
                Surface(
                    color = if (isWinner) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surface.copy(alpha = 0.9f),
                    shape = RoundedCornerShape(bottomEnd = 9.dp),
                ) {
                    Text(if (isWinner) "欧米更推荐" else label, Modifier.padding(horizontal = 7.dp, vertical = 4.dp),
                        style = MaterialTheme.typography.labelSmall,
                        color = if (isWinner) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            Column(Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                if (brand.isNotBlank()) Text(brand, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
                Text(title, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Bold, maxLines = 2,
                    overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                Text("¥$price", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.error)
                dimensions.take(4).forEach { dimension ->
                    val value = attributes[dimension]?.toString()?.takeIf { it.isNotBlank() } ?: "—"
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(dimension, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        Text(value, style = MaterialTheme.typography.labelSmall, fontWeight = FontWeight.Medium,
                            maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
                            modifier = Modifier.padding(start = 8.dp))
                    }
                }
                highlights.take(2).takeIf { it.isNotEmpty() }?.let {
                    Text("亮点：${it.joinToString("；")}", style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary, maxLines = 2,
                        overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                }
                if (caution.isNotBlank()) Text("留意：$caution", style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.error, maxLines = 1,
                    overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                item["suitable_for"]?.toString()?.takeIf { it.isNotBlank() }?.let {
                    Text("怎么选：$it", style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 2,
                        overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                }
            }
        }
    }
}

@Composable
fun ComparisonCard(response: com.omnicart.agent.core.model.RecommendResponse) {
    val analysis = response.targetProductAnalysis
    val comparison = response.comparisonTable
    val alternatives = response.analysisAlternatives

    if (analysis == null && comparison == null) return

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer.copy(alpha = 0.2f)),
        shape = RoundedCornerShape(14.dp),
    ) {
        Column(Modifier.padding(14.dp)) {
            Text("对比分析",
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary)
            Spacer(Modifier.height(10.dp))

            // 目标商品分析
            analysis?.let { a -> TargetProductSection(a) }

            // 对比表格
            comparison?.let { comp ->
                Spacer(Modifier.height(10.dp))
                ComparisonTableSection(comp, alternatives)
            }
        }
    }
}

// ---- F2-3: 推荐结果摘要 chips ----

@Composable
fun SummaryChips(response: com.omnicart.agent.core.model.RecommendResponse) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        val evCount = response.evidenceList.size
        if (evCount > 0) {
            AssistChip(
                onClick = {},
                label = { Text("参考信息 $evCount 条", style = MaterialTheme.typography.labelSmall) },
                leadingIcon = { Icon(Icons.Filled.AutoAwesome, null, Modifier.size(14.dp)) },
                modifier = Modifier.height(28.dp),
            )
        }
        val memCount = (response.usedMemories?.size ?: 0)
        if (memCount > 0) {
            AssistChip(
                onClick = {},
                label = { Text("记忆 $memCount 条", style = MaterialTheme.typography.labelSmall) },
                leadingIcon = { Icon(Icons.Filled.Star, null, Modifier.size(14.dp)) },
                modifier = Modifier.height(28.dp),
            )
        }
        val harPassed = response.harnessReport?.get("passed")?.toString()?.lowercase() == "true"
        val harFailed = response.harnessReport?.get("passed")?.toString()?.lowercase() == "false"
        if (harPassed || harFailed) {
            AssistChip(
                onClick = {},
                label = { Text(if (harPassed) "Harness 通过" else "Harness 待查", style = MaterialTheme.typography.labelSmall) },
                leadingIcon = {
                    Icon(Icons.Filled.Refresh, null, Modifier.size(14.dp),
                        tint = if (harPassed) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error)
                },
                modifier = Modifier.height(28.dp),
            )
        }
    }
}

// ---- F2-2: Clarification 引导选项 ----

@Composable
fun ClarificationChips(
    question: String,
    options: List<Map<String, Any?>>,
    onSelect: (String) -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.secondaryContainer.copy(alpha = 0.3f)),
        shape = RoundedCornerShape(12.dp),
    ) {
        Column(Modifier.padding(12.dp)) {
            if (question.isNotBlank()) {
                Text(question, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(8.dp))
            }
            Row(
                modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                options.forEach { opt ->
                    val label = opt["label"]?.toString() ?: opt["value"]?.toString() ?: ""
                    SuggestionChip(
                        onClick = { onSelect(label) },
                        label = { Text(label, style = MaterialTheme.typography.labelLarge) },
                        shape = RoundedCornerShape(20.dp),
                    )
                }
            }
        }
    }
}

// ---- Shop Action 操作按钮 ----

@Composable
fun ShopActionButtons(
    actions: List<Map<String, Any?>>,
    onAddressForm: () -> Unit,
    onQuickReply: (String) -> Unit,
) {
    val skuActions = actions.filter { it["type"]?.toString() == "sku_option" }
    val normalActions = actions.filter { it["type"]?.toString() != "sku_option" }

    // 普通操作按钮（换行排列）
    if (normalActions.isNotEmpty()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            normalActions.forEach { action ->
                val type = action["type"]?.toString() ?: ""
                val label = action["label"]?.toString() ?: ""
                when (type) {
                    "address_form" -> {
                        Button(
                            onClick = onAddressForm,
                            shape = RoundedCornerShape(20.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary),
                        ) { Text(label, style = MaterialTheme.typography.labelLarge) }
                    }
                    "quick_reply" -> {
                        OutlinedButton(
                            onClick = { onQuickReply(label) },
                            shape = RoundedCornerShape(20.dp),
                        ) { Text(label, style = MaterialTheme.typography.labelLarge) }
                    }
                }
            }
        }
    }

    // SKU 规格选项（横向滚动）
    if (skuActions.isNotEmpty()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 4.dp)
                .horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            skuActions.forEach { action ->
                val label = action["label"]?.toString() ?: ""
                OutlinedButton(
                    onClick = { onQuickReply(label) },
                    shape = RoundedCornerShape(20.dp),
                    colors = ButtonDefaults.outlinedButtonColors(
                        contentColor = MaterialTheme.colorScheme.tertiary,
                    ),
                ) { Text(label, style = MaterialTheme.typography.labelLarge, maxLines = 1) }
            }
        }
    }
}

// ---- 地址填写弹窗 ----

@Composable
fun AddressFormDialog(
    onDismiss: () -> Unit,
    onSubmit: (String, String, String, String, String, String) -> Unit,
) {
    var name by remember { mutableStateOf("") }
    var phone by remember { mutableStateOf("") }
    var province by remember { mutableStateOf("") }
    var city by remember { mutableStateOf("") }
    var district by remember { mutableStateOf("") }
    var detail by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("填写收货地址") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(value = name, onValueChange = { name = it }, label = { Text("收件人") }, singleLine = true)
                OutlinedTextField(value = phone, onValueChange = { phone = it }, label = { Text("电话") }, singleLine = true)
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(value = province, onValueChange = { province = it }, label = { Text("省") }, modifier = Modifier.weight(1f), singleLine = true)
                    OutlinedTextField(value = city, onValueChange = { city = it }, label = { Text("市") }, modifier = Modifier.weight(1f), singleLine = true)
                    OutlinedTextField(value = district, onValueChange = { district = it }, label = { Text("区") }, modifier = Modifier.weight(1f), singleLine = true)
                }
                OutlinedTextField(value = detail, onValueChange = { detail = it }, label = { Text("详细地址") }, singleLine = true)
            }
        },
        confirmButton = {
            Button(onClick = {
                if (name.isNotBlank() && phone.isNotBlank() && detail.isNotBlank()) {
                    onSubmit(name, phone, province, city, district, detail)
                }
            }) { Text("确认") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("取消") } },
    )
}
