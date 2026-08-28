plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.omnicart.agent"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.omnicart.agent"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
    }

    signingConfigs {
        create("release") {
            storeFile = file("omnicart-release.keystore")
            storePassword = "omnicart2026"
            keyAlias = "omnicart"
            keyPassword = "omnicart2026"
        }
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
            // 真机调试通过 adb reverse 映射到电脑端 8006，IP 切换、热点切换或
            // Windows 防火墙都不会再让 App 绑定一条过期的局域网地址。
            buildConfigField("String", "BASE_URL", "\"http://127.0.0.1:8006/\"")
        }
        release {
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            signingConfig = signingConfigs.getByName("release")
            buildConfigField("String", "BASE_URL", "\"http://8.137.187.54:8006/\"")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }
}

// Android Studio Run 会触发 installDebug。安装完成后自动建立 USB 调试端口映射：
// 手机上的 127.0.0.1:8006 → 开发机的 127.0.0.1:8006。
// adb 不可用时不使构建失败；此时仍可用 release 配置的线上服务。
tasks.configureEach {
    if (name.startsWith("install") && name.endsWith("Debug")) {
        doLast {
            val adb = File(android.sdkDirectory, "platform-tools/adb.exe")
            if (adb.isFile) {
                exec {
                    commandLine(adb.absolutePath, "reverse", "tcp:8006", "tcp:8006")
                    isIgnoreExitValue = true
                }
            }
        }
    }
}

dependencies {
    // Compose BOM
    val composeBom = platform("androidx.compose:compose-bom:2024.06.00")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    debugImplementation("androidx.compose.ui:ui-tooling")

    // Navigation
    implementation("androidx.navigation:navigation-compose:2.7.7")

    // Activity + Lifecycle
    implementation("androidx.activity:activity-compose:1.9.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.0")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.0")

    // Retrofit + OkHttp
    implementation("com.squareup.retrofit2:retrofit:2.11.0")
    implementation("com.squareup.retrofit2:converter-gson:2.11.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")

    // Coil
    implementation("io.coil-kt:coil-compose:2.6.0")

    // Coroutines
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")

    // Core
    implementation("androidx.core:core-ktx:1.13.1")
}
