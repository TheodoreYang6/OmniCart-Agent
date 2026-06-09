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
import com.omnicart.agent.feature.product.ProductDetailSheet
import com.omnicart.agent.feature.upload.ImagePreview
import com.omnicart.agent.feature.panel.AgentInsightSheet
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
) {
    LaunchedEffect(sessionId) {
        if (sessionId.isNotBlank() && viewModel.uiState.value.sessionId != sessionId) {
            viewModel.setSessionId(sessionId)
        }
    }
    // 问问豆仔：自动发送聚焦分析
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
    var showInsight by remember { mutableStateOf(false) }
    val snackbarHostState = remember { SnackbarHostState() }
    val listState = rememberLazyListState()

    // 自动滚动到底部
    LaunchedEffect(uiState.messages.size, uiState.isLoading) {
        if (uiState.messages.isNotEmpty()) {
            listState.animateScrollToItem(uiState.messages.size - 1)
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

    // The input bar owns IME padding so it lifts with the keyboard without double-spacing the whole screen.
    Box(modifier = modifier.fillMaxSize()) {
        Column(modifier = Modifier.fillMaxSize()) {
            // 顶栏 — 品牌化
            Surface(color = Primary, tonalElevation = 0.dp) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Surface(shape = RoundedCornerShape(12.dp), color = OnPrimary.copy(alpha = 0.16f)) {
                        Icon(
                            Icons.Filled.AutoAwesome,
                            contentDescription = null,
                            tint = OnPrimary,
                            modifier = Modifier.padding(8.dp).size(18.dp),
                        )
                    }
                    Spacer(Modifier.width(10.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            "豆仔 AI 导购",
                            style = MaterialTheme.typography.titleMedium,
                            color = OnPrimary,
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            "帮你比商品、看证据、避风险",
                            style = MaterialTheme.typography.labelSmall,
                            color = OnPrimary.copy(alpha = 0.82f),
                        )
                    }
                    // 偏好生效指示
                    if (uiState.profileEnabled) {
                        Spacer(Modifier.width(8.dp))
                        Surface(
                            shape = RoundedCornerShape(12.dp),
                            color = OnPrimary.copy(alpha = 0.18f),
                        ) {
                            Row(
                                Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                                verticalAlignment = Alignment.CenterVertically,
                            ) {
                                Icon(
                                    Icons.Filled.Star,
                                    null,
                                    Modifier.size(12.dp),
                                    tint = OnPrimary,
                                )
                                Spacer(Modifier.width(4.dp))
                                Text(
                                    "偏好生效",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = OnPrimary,
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
                                tint = OnPrimary,
                            )
                        }
                    }
                    // 历史按钮 — 仅登录用户可见
                    if (AuthManager.userId.isNotBlank()) {
                        IconButton(onClick = { viewModel.toggleHistorySheet() }) {
                            Icon(
                                Icons.Filled.Refresh,
                                contentDescription = "历史聊天",
                                tint = OnPrimary,
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
                                        MessageBubble(
                                            text = message.text,
                                            type = BubbleType.Assistant,
                                        )
                                        // 问问豆仔对比卡片 (持久化在消息中)
                                        if (message.hasComparison) {
                                            Spacer(modifier = Modifier.height(6.dp))
                                            ComparisonCardForMessage(message)
                                        }
                                        if (message.hasProducts) {
                                            Spacer(modifier = Modifier.height(4.dp))
                                            Text(
                                                text = "为你找到 ${message.products.size} 款值得比较的商品",
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
                                                onClick = { onProductClick(product.productId) },
                                                onAddToCart = { skuId, skuLabel, skuPrice ->
                                                    viewModel.onAddToCart(product.productId, product.title, skuId, skuLabel, skuPrice)
                                                },
                                                onScoreDetail = { viewModel.onProductClick(product.productId) },
                                            )
                                            Spacer(modifier = Modifier.height(8.dp))
                                        }
                                    }
                                }
                            }
                        }

                        // F2-3: 推荐结果摘要 chips — 仅当前回复有商品时，跟随最后一条消息
                        if (uiState.lastResponse?.products?.isNotEmpty() == true) {
                            item(key = "summary_${uiState.messages.size}") {
                                SummaryChips(uiState.lastResponse!!)
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
                                        text = uiState.loadingMessage.ifBlank { "豆仔正在思考…" },
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant
                                    )
                                }
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

                        // F2-2: Clarification 引导选项
                        if (uiState.lastResponse?.needsClarification == true) {
                            item(key = "clarification") {
                                ClarificationChips(
                                    question = uiState.lastResponse!!.clarificationQuestion,
                                    options = uiState.lastResponse!!.clarificationOptions ?: emptyList(),
                                    onSelect = { label ->
                                        viewModel.onQueryChange(label)
                                        viewModel.onSend()
                                    },
                                )
                            }
                        }

                        // Shop Action 操作按钮
                        if (uiState.lastResponse?.shopAction == true && uiState.lastResponse?.actions != null) {
                            item(key = "shop_actions") {
                                ShopActionButtons(
                                    actions = uiState.lastResponse!!.actions!!,
                                    onAddressForm = {
                                        viewModel.showAddressForm()
                                    },
                                    onQuickReply = { label ->
                                        viewModel.onQueryChange(label)
                                        viewModel.onSend()
                                    },
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
                            Surface(
                                shape = RoundedCornerShape(24.dp),
                                color = Primary.copy(alpha = 0.1f),
                            ) {
                                Icon(
                                    Icons.Filled.AutoAwesome,
                                    contentDescription = null,
                                    tint = Primary,
                                    modifier = Modifier.padding(18.dp).size(34.dp),
                                )
                            }
                            Spacer(modifier = Modifier.height(18.dp))
                            Text(
                                text = "豆仔",
                                style = MaterialTheme.typography.headlineMedium,
                                color = MaterialTheme.colorScheme.primary,
                                fontWeight = androidx.compose.ui.text.font.FontWeight.Bold
                            )
                            Spacer(modifier = Modifier.height(8.dp))
                            Text(
                                text = "你的 AI 购物决策助手",
                                style = MaterialTheme.typography.bodyLarge,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                            Spacer(modifier = Modifier.height(12.dp))
                            Text(
                                text = "告诉我预算、场景、设备或上传商品截图\n我会结合证据、评分和风险提示给出建议",
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
                    modifier = Modifier.imePadding(),
                )
            }
        }
        // 地址填写弹窗
        if (uiState.showAddressForm) {
            AddressFormDialog(
                onDismiss = { viewModel.dismissAddressForm() },
                onSubmit = { name, phone, province, city, district, detail ->
                    viewModel.submitAddress(name, phone, province, city, district, detail) {
                        viewModel.onQueryChange("下单")
                        viewModel.onSend()
                    }
                },
            )
        }

        SnackbarHost(
            hostState = snackbarHostState,
            modifier = Modifier.align(Alignment.BottomCenter)
        )

        // V1-Plus: Agent 洞察面板
        if (showInsight) {
            AgentInsightSheet(
                response = uiState.lastResponse,
                onDismiss = { showInsight = false },
            )
        }

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

// ---- P2-2: "问问豆仔" 对比分析卡片 ----

/** 目标商品分析区块 (共用) */
@Composable
fun TargetProductSection(a: Map<String, Any?>) {
    val title = a["title"]?.toString() ?: ""
    val brand = a["brand"]?.toString() ?: ""
    val price = (a["price"] as? Number)?.toDouble() ?: 0.0
    val score = (a["display_score"] as? Number)?.toDouble() ?: 0.0
    val level = a["recommendation_level"]?.toString() ?: ""
    val levelCN = when (level) {
        "strong_recommend" -> "强烈推荐"
        "recommended" -> "值得推荐"
        "cautious" -> "谨慎考虑"
        "insufficient_evidence" -> "证据不足"
        "not_recommended" -> "不推荐"
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
                Text("评分: ${score}/10",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.primary)
                Spacer(Modifier.width(12.dp))
                Text("等级: $levelCN",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.secondary)
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
            message.comparisonTable?.let { c -> ComparisonTableSection(c, message.alternativeProducts) }
        }
    }
}

@Composable
fun ComparisonCard(response: com.omnicart.agent.core.model.RecommendResponse) {
    val analysis = response.targetProductAnalysis
    val comparison = response.comparisonTable
    val alternatives = response.alternativeProducts

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
                label = { Text("证据 $evCount 条", style = MaterialTheme.typography.labelSmall) },
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
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        actions.forEach { action ->
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
