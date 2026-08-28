package com.omnicart.agent

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import coil.ImageLoader
import coil.ImageLoaderFactory
import okhttp3.OkHttpClient
import com.omnicart.agent.core.config.ServerConfig
import com.omnicart.agent.core.theme.OmniCartTheme

class MainActivity : ComponentActivity(), ImageLoaderFactory {

    private companion object {
        const val UI_PREFERENCES = "omnicart_ui_preferences"
        const val DARK_MODE = "dark_mode"
    }

    override fun newImageLoader(): ImageLoader {
        return ImageLoader.Builder(this)
            .crossfade(true)
            .okHttpClient {
                OkHttpClient.Builder()
                    .hostnameVerifier { _, _ -> true }
                    .build()
            }
            .build()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        ServerConfig.load(this)
        val preferences = getSharedPreferences(UI_PREFERENCES, MODE_PRIVATE)
        setContent {
            val systemDark = isSystemInDarkTheme()
            var darkTheme by remember {
                mutableStateOf(preferences.getBoolean(DARK_MODE, systemDark))
            }
            OmniCartTheme(darkTheme = darkTheme) {
                MainScreen(
                    isDarkTheme = darkTheme,
                    onDarkThemeChange = { enabled ->
                        darkTheme = enabled
                        preferences.edit().putBoolean(DARK_MODE, enabled).apply()
                    },
                )
            }
        }
    }
}
