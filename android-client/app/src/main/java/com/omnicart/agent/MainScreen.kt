package com.omnicart.agent

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Chat
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.ShoppingCart
import androidx.compose.material.icons.filled.Storefront
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import com.omnicart.agent.core.network.ApiClient
import kotlinx.coroutines.launch
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavDestination.Companion.hierarchy
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.omnicart.agent.feature.auth.AuthManager
import com.omnicart.agent.feature.auth.AuthViewModel
import com.omnicart.agent.feature.auth.LoginScreen
import com.omnicart.agent.feature.chat.ChatScreen
import com.omnicart.agent.feature.shop.ProductListScreen
import com.omnicart.agent.feature.product.ProductDetailScreen
import com.omnicart.agent.feature.cart.CartScreen
import com.omnicart.agent.feature.profile.ProfileScreen
import com.omnicart.agent.feature.address.AddressScreen
import com.omnicart.agent.feature.preference.PreferenceScreen

data class BottomTab(val route: String, val label: String, val icon: ImageVector)

val tabs = listOf(
    BottomTab("shop", "商品", Icons.Filled.Storefront),
    BottomTab("chat", "豆仔", Icons.AutoMirrored.Filled.Chat),
    BottomTab("cart", "购物车", Icons.Filled.ShoppingCart),
    BottomTab("profile", "我的", Icons.Filled.Person),
)

@Composable
fun MainScreen() {
    val navController = rememberNavController()
    val navBackStackEntry by navController.currentBackStackEntryAsState()
    val currentDestination = navBackStackEntry?.destination
    var cartRefreshKey by remember { mutableIntStateOf(0) }
    val context = LocalContext.current
    val authViewModel: AuthViewModel = viewModel()
    val authState by authViewModel.uiState.collectAsState()

    // P0-2: 共享 sessionId，用户切换时重新生成
    val sharedSessionId = remember(AuthManager.effectiveUserId) {
        java.util.UUID.randomUUID().toString().take(8)
    }

    // 初始化 AuthManager
    LaunchedEffect(Unit) {
        AuthManager.init(context)
    }

    // 隐藏底部 Tab 的页面路由
    val hideBottomBar = currentDestination?.route in listOf("login", "address", "preference", "product_detail/{productId}")

    // 问问豆仔状态
    var askDouzaiProductId by remember { mutableStateOf("") }
    var askDouzaiTitle by remember { mutableStateOf("") }

    Scaffold(
        bottomBar = {
            if (!hideBottomBar) {
                NavigationBar(
                    tonalElevation = 8.dp,
                    containerColor = MaterialTheme.colorScheme.surface,
                ) {
                    tabs.forEach { tab ->
                        val selected = currentDestination?.hierarchy?.any { it.route == tab.route } == true
                        NavigationBarItem(
                            selected = selected,
                            onClick = {
                                if (tab.route == "cart") cartRefreshKey++
                                navController.navigate(tab.route) {
                                    popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                            icon = { Icon(tab.icon, contentDescription = tab.label) },
                            label = { Text(tab.label) },
                            colors = NavigationBarItemDefaults.colors(
                                selectedIconColor = MaterialTheme.colorScheme.primary,
                                selectedTextColor = MaterialTheme.colorScheme.primary,
                                indicatorColor = MaterialTheme.colorScheme.primaryContainer,
                            ),
                        )
                    }
                }
            }
        }
    ) { padding ->
        NavHost(
            navController = navController,
            startDestination = "chat",
            modifier = Modifier.padding(padding),
        ) {
            composable("shop") {
                ProductListScreen(
                    sessionId = sharedSessionId,
                    userId = AuthManager.effectiveUserId,
                    onProductClick = { productId -> navController.navigate("product_detail/$productId") },
                )
            }
            composable("chat") {
                val chatUserId = AuthManager.effectiveUserId
                androidx.compose.runtime.key(chatUserId) {
                    ChatScreen(
                        sessionId = sharedSessionId,
                        userId = chatUserId,
                        askDouzaiProductId = askDouzaiProductId,
                        askDouzaiTitle = askDouzaiTitle,
                        onAskDouzaiConsumed = { askDouzaiProductId = ""; askDouzaiTitle = "" },
                        onProductClick = { productId -> navController.navigate("product_detail/$productId") },
                    )
                }
            }
            composable("product_detail/{productId}") { backStackEntry ->
                val pid = backStackEntry.arguments?.getString("productId") ?: ""
                ProductDetailScreen(
                    productId = pid,
                    sessionId = sharedSessionId,
                    userId = AuthManager.effectiveUserId,
                    onBack = { navController.popBackStack() },
                    onAskDouzai = { productId, title ->
                        askDouzaiProductId = productId
                        askDouzaiTitle = title
                        // 先关掉详情页, 回到聊天
                        navController.popBackStack()
                        // 再切到聊天tab
                        navController.navigate("chat") {
                            launchSingleTop = true
                        }
                    },
                )
            }
            composable("cart") { CartScreen(refreshKey = cartRefreshKey, sessionId = sharedSessionId) }
            composable("orders") {
                com.omnicart.agent.feature.order.OrderScreen(
                    userId = AuthManager.effectiveUserId,
                    onBack = { navController.popBackStack() },
                )
            }
            composable("profile") {
                var memories by remember { mutableStateOf<List<com.omnicart.agent.core.network.UserMemoryItem>>(emptyList()) }
                var isLoadingMemories by remember { mutableStateOf(false) }
                val scope = rememberCoroutineScope()

                val loadMemories: () -> Unit = {
                    scope.launch {
                        isLoadingMemories = true
                        try {
                            val response = com.omnicart.agent.core.network.ApiClient.api.getMemories(
                                userId = AuthManager.effectiveUserId
                            )
                            memories = response.memories
                        } catch (_: Exception) { }
                        isLoadingMemories = false
                    }
                }

                val deleteMemory: (String) -> Unit = { memoryId ->
                    scope.launch {
                        try {
                            com.omnicart.agent.core.network.ApiClient.api.deleteMemory(
                                memoryId = memoryId, userId = AuthManager.effectiveUserId
                            )
                            memories = memories.filter { it.memoryId != memoryId }
                        } catch (_: Exception) { }
                    }
                }

                ProfileScreen(
                    isLoggedIn = authState.isLoggedIn,
                    username = authState.username,
                    memories = memories,
                    isLoadingMemories = isLoadingMemories,
                    onLoginClick = { navController.navigate("login") },
                    onLogoutClick = { authViewModel.logout() },
                    onAddressClick = { navController.navigate("address") },
                    onPreferenceClick = { navController.navigate("preference") },
                    onOrdersClick = { navController.navigate("orders") },
                    onLoadMemories = loadMemories,
                    onDeleteMemory = deleteMemory,
                )
            }
            composable("login") {
                LoginScreen(
                    viewModel = authViewModel,
                    onLoggedIn = { navController.popBackStack() },
                )
            }
            composable("address") {
                AddressScreen(onBack = { navController.popBackStack() })
            }
            composable("preference") {
                PreferenceScreen(
                    userId = AuthManager.effectiveUserId,
                    onBack = { navController.popBackStack() },
                )
            }
        }
    }
}
