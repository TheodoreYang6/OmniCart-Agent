package com.omnicart.agent

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.ShoppingCart
import androidx.compose.material.icons.filled.Storefront
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
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
import com.omnicart.agent.feature.cart.CartScreen
import com.omnicart.agent.feature.profile.ProfileScreen
import com.omnicart.agent.feature.address.AddressScreen

data class BottomTab(val route: String, val label: String, val icon: ImageVector)

val tabs = listOf(
    BottomTab("shop", "商品", Icons.Filled.Storefront),
    BottomTab("chat", "豆仔", Icons.Filled.Chat),
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

    // 初始化 AuthManager
    LaunchedEffect(Unit) {
        AuthManager.init(context)
    }

    // 隐藏底部 Tab 的页面路由
    val hideBottomBar = currentDestination?.route in listOf("login", "address")

    Scaffold(
        bottomBar = {
            if (!hideBottomBar) {
                NavigationBar {
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
            composable("shop") { ProductListScreen() }
            composable("chat") { ChatScreen() }
            composable("cart") { CartScreen(refreshKey = cartRefreshKey) }
            composable("profile") {
                ProfileScreen(
                    isLoggedIn = authState.isLoggedIn,
                    username = authState.username,
                    onLoginClick = { navController.navigate("login") },
                    onLogoutClick = { authViewModel.logout() },
                    onAddressClick = { navController.navigate("address") },
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
        }
    }
}
