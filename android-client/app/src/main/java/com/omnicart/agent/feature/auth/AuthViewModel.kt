package com.omnicart.agent.feature.auth

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.omnicart.agent.core.network.ApiClient
import com.omnicart.agent.core.network.LoginRequest
import com.omnicart.agent.core.network.RegisterRequest
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class AuthUiState(
    val isLoggedIn: Boolean = AuthManager.isLoggedIn,
    val username: String = AuthManager.username,
    val isLoading: Boolean = false,
    val isRegisterMode: Boolean = false,
    val errorMessage: String? = null,
)

class AuthViewModel(application: Application) : AndroidViewModel(application) {

    init {
        AuthManager.init(application)
    }

    private val _uiState = MutableStateFlow(AuthUiState())
    val uiState: StateFlow<AuthUiState> = _uiState.asStateFlow()

    fun toggleMode() {
        _uiState.update { it.copy(isRegisterMode = !it.isRegisterMode, errorMessage = null) }
    }

    fun login(username: String, password: String) {
        if (username.isBlank() || password.isBlank()) {
            _uiState.update { it.copy(errorMessage = "请输入用户名和密码") }
            return
        }
        _uiState.update { it.copy(isLoading = true, errorMessage = null) }
        viewModelScope.launch {
            try {
                val result = ApiClient.api.login(LoginRequest(username.trim(), password))
                if (result.error != null) {
                    _uiState.update { it.copy(isLoading = false, errorMessage = "用户名或密码错误") }
                } else {
                    AuthManager.saveLogin(result.userId, result.username, result.token, result.email, result.phone)
                    _uiState.update {
                        it.copy(isLoading = false, isLoggedIn = true, username = result.username)
                    }
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(isLoading = false, errorMessage = "登录失败: ${e.message}")
                }
            }
        }
    }

    fun register(username: String, password: String, email: String = "", phone: String = "") {
        if (username.isBlank() || password.isBlank()) {
            _uiState.update { it.copy(errorMessage = "请输入用户名和密码") }
            return
        }
        _uiState.update { it.copy(isLoading = true, errorMessage = null) }
        viewModelScope.launch {
            try {
                val result = ApiClient.api.register(RegisterRequest(username.trim(), password, email.trim(), phone.trim()))
                if (result.error != null) {
                    _uiState.update { it.copy(isLoading = false, errorMessage = "用户名已存在") }
                } else {
                    AuthManager.saveLogin(result.userId, result.username, result.token, result.email, result.phone)
                    _uiState.update {
                        it.copy(isLoading = false, isLoggedIn = true, username = result.username)
                    }
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(isLoading = false, errorMessage = "注册失败: ${e.message}")
                }
            }
        }
    }

    fun logout() {
        AuthManager.logout()
        _uiState.update { AuthUiState() }
    }

    fun clearError() {
        _uiState.update { it.copy(errorMessage = null) }
    }
}
