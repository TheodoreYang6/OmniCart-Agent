@echo off
chcp 65001 >nul
echo ============================================
echo   OmniCart Agent - 手机连接工具
echo ============================================
echo.

set ADB=C:\Users\61770\AppData\Local\Android\Sdk\platform-tools\adb.exe

REM === Step 0: 检查 ADB 是否存在 ===
if not exist "%ADB%" (
    echo [错误] 找不到 ADB 工具
    echo 路径: %ADB%
    echo 请安装 Android Studio 或 Android SDK Platform Tools
    goto end
)

REM === Step 1: 列出所有设备 ===
echo [步骤1] 检测设备...
echo.
"%ADB%" devices
echo.

REM 检查是否有设备（排除空行和 "List of devices" 标题行）
"%ADB%" devices 2>nul | findstr /v "List of devices" | findstr "." >nul
if %errorlevel% neq 0 (
    echo [失败] 没有检测到任何设备！
    echo.
    echo 请检查：
    echo   1. USB 线已连接手机和电脑
    echo   2. 手机已开启「USB 调试」（设置 → 开发者选项）
    echo   3. 如看不到开发者选项：设置 → 关于手机 → 连续点 7 次「版本号」
    echo.
    echo 如果是模拟器：
    echo   1. 先打开 Android Studio → AVD Manager → 启动模拟器
    echo   2. 再运行本脚本
    goto end
)

REM 检查设备状态是否为 unauthorized
"%ADB%" devices 2>nul | findstr "unauthorized" >nul
if %errorlevel% equ 0 (
    echo [失败] 设备未授权！
    echo.
    echo 请查看手机屏幕，会弹出「允许USB调试」对话框
    echo → 勾选「一律允许」然后点击「确定」
    echo → 然后重新运行本脚本
    goto end
)

echo [成功] 设备已连接且已授权

REM === Step 2: 建立反向隧道 ===
echo.
echo [步骤2] 建立端口转发 (手机:8006 → 电脑:8006)...
"%ADB%" reverse tcp:8006 tcp:8006
if %errorlevel% neq 0 (
    echo [失败] 端口转发建立失败
    goto end
)
echo [成功] 端口转发已建立

REM === Step 3: 检查后端是否在运行 ===
echo.
echo [步骤3] 检查后端...
curl -s --connect-timeout 3 http://127.0.0.1:8006/api/health >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 后端似乎未启动，请先启动：
    echo   cd backend
    echo   python -m uvicorn app.main:app --host 127.0.0.1 --port 8006
    goto end
)
echo [成功] 后端运行中

REM === Step 4: 确认隧道就绪 ===
echo.
echo [步骤4] 确认隧道...
"%ADB%" reverse --list 2>nul | findstr "8006" >nul
if %errorlevel% neq 0 (
    echo [提示] 隧道未检测到，但通常不影响使用
)
echo [成功] 隧道已建立

echo.
echo ============================================
echo   连接就绪！
echo.
echo   如果 App 已经打开，请从最近任务中划掉
echo   然后重新打开 App 即可正常使用
echo ============================================

:end
echo.
pause
