<#
One-command physical-device debug preparation.

It deliberately maps the device loopback port to the local backend.  Do not put a
Wi-Fi address here: DHCP/hotspots make it stale and Windows firewall rules vary.
#>
param(
    [int]$Port = 8006,
    [string]$Adb = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
)

$ErrorActionPreference = "Stop"
if (-not (Test-Path -LiteralPath $Adb)) {
    throw "找不到 adb：$Adb。请在 Android Studio SDK Manager 安装 Platform-Tools。"
}

$device = & $Adb devices | Select-String "`tdevice$" | Select-Object -First 1
if (-not $device) {
    throw "没有检测到已授权的 Android 调试设备。请连接 USB 并允许 USB 调试。"
}

try {
    Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/api/health" -TimeoutSec 3 | Out-Null
} catch {
    throw "本机后端未就绪：请先从项目根目录运行 python run.py。"
}

& $Adb reverse "tcp:$Port" "tcp:$Port"
if ($LASTEXITCODE -ne 0) { throw "adb reverse 失败。" }

& $Adb shell "toybox nc -z -w 3 127.0.0.1 $Port"
if ($LASTEXITCODE -ne 0) { throw "手机无法通过 adb reverse 连到后端。" }

Write-Host "欧米 Android 调试连接已就绪：手机 127.0.0.1:$Port → 电脑本机后端。"
