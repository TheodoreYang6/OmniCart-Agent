[CmdletBinding()]
param(
    [string]$RuntimeRoot = 'D:\OmniCart-Agent-runtime',
    [int]$TimeoutSeconds = 30
)

$ErrorActionPreference = 'Stop'
$hostAddress = '127.0.0.1'
$logRoot = Join-Path $RuntimeRoot 'logs'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Test-TcpPort([int]$Port, [int]$TimeoutMs = 700) {
    $client = [System.Net.Sockets.TcpClient]::new()
    $asyncResult = $null
    try {
        $asyncResult = $client.BeginConnect($hostAddress, $Port, $null, $null)
        if (-not $asyncResult.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
            return $false
        }
        $client.EndConnect($asyncResult)
        return $true
    }
    catch {
        return $false
    }
    finally {
        if ($null -ne $asyncResult) { $asyncResult.AsyncWaitHandle.Close() }
        $client.Dispose()
    }
}

function Wait-TcpPort([int]$Port, [string]$Name) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-TcpPort -Port $Port) { return $true }
        Start-Sleep -Milliseconds 500
    }
    throw "$Name did not open $hostAddress`:$Port within $TimeoutSeconds seconds."
}

function Start-PostgreSql {
    Write-Step 'PostgreSQL (5432)'
    if (Test-TcpPort -Port 5432) {
        Write-Host 'Already running.' -ForegroundColor Green
        return
    }

    $service = Get-Service -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like 'postgresql*' -or $_.DisplayName -like '*PostgreSQL*' } |
        Sort-Object Name -Descending |
        Select-Object -First 1

    if ($null -eq $service) {
        throw 'PostgreSQL Windows service was not found.'
    }

    Write-Host "Starting Windows service: $($service.Name)"
    try {
        Start-Service -Name $service.Name
    }
    catch {
        throw "Unable to start $($service.Name). Try running this script as Administrator. $($_.Exception.Message)"
    }
    Wait-TcpPort -Port 5432 -Name 'PostgreSQL' | Out-Null
    Write-Host 'Started successfully.' -ForegroundColor Green
}

function Start-Redis {
    Write-Step 'Redis / Memurai (6379, project DB 1)'
    $alreadyRunning = Test-TcpPort -Port 6379
    if ($alreadyRunning) {
        Write-Host 'Already running.' -ForegroundColor Green
    }
    else {
        $redisService = Get-Service -ErrorAction SilentlyContinue |
            Where-Object {
                $_.Name -like 'Memurai*' -or $_.DisplayName -like '*Memurai*' -or
                $_.Name -like 'Redis*' -or $_.DisplayName -like '*Redis*'
            } |
            Select-Object -First 1

        if ($null -ne $redisService) {
            Write-Host "Starting Windows service: $($redisService.Name)"
            try {
                Start-Service -Name $redisService.Name
            }
            catch {
                throw "Unable to start $($redisService.Name). Try running this script as Administrator. $($_.Exception.Message)"
            }
        }
        else {
            $memuraiExe = Join-Path $RuntimeRoot 'memurai\bin\SourceDir\Memurai\memurai.exe'
            $memuraiConfig = Join-Path $RuntimeRoot 'memurai\config\omnicart.conf'
            if (-not (Test-Path -LiteralPath $memuraiExe)) {
                throw "Memurai executable not found: $memuraiExe"
            }
            if (-not (Test-Path -LiteralPath $memuraiConfig)) {
                throw "Memurai config not found: $memuraiConfig"
            }

            Write-Host "Starting standalone Memurai: $memuraiExe"
            Start-Process -FilePath $memuraiExe `
                -ArgumentList @("`"$memuraiConfig`"") `
                -WorkingDirectory (Split-Path -Parent $memuraiExe) `
                -WindowStyle Hidden `
                -RedirectStandardOutput (Join-Path $logRoot 'memurai.stdout.log') `
                -RedirectStandardError (Join-Path $logRoot 'memurai.stderr.log') | Out-Null
        }
    }

    Wait-TcpPort -Port 6379 -Name 'Redis / Memurai' | Out-Null

    $redisCli = Join-Path $RuntimeRoot 'memurai\bin\SourceDir\Memurai\memurai-cli.exe'
    if (Test-Path -LiteralPath $redisCli) {
        $pong = & $redisCli -h $hostAddress -p 6379 PING 2>$null
        if (($pong | Out-String).Trim() -ne 'PONG') {
            throw 'Redis port opened, but PING did not return PONG.'
        }
    }
    Write-Host 'Started successfully. OmniCart uses redis://127.0.0.1:6379/1.' -ForegroundColor Green
}

function Start-Qdrant {
    Write-Step 'Qdrant (6333 HTTP / 6334 gRPC)'
    $alreadyRunning = Test-TcpPort -Port 6333
    if ($alreadyRunning) {
        Write-Host 'Already running.' -ForegroundColor Green
    }
    else {
        $qdrantRoot = Join-Path $RuntimeRoot 'qdrant'
        $qdrantExe = Join-Path $qdrantRoot 'qdrant.exe'
        $qdrantConfig = Join-Path $qdrantRoot 'config\omnicart.yaml'
        if (-not (Test-Path -LiteralPath $qdrantExe)) {
            throw "Qdrant executable not found: $qdrantExe"
        }
        if (-not (Test-Path -LiteralPath $qdrantConfig)) {
            throw "Qdrant config not found: $qdrantConfig"
        }

        Write-Host "Starting Qdrant: $qdrantExe"
        Start-Process -FilePath $qdrantExe `
            -ArgumentList @('--config-path', "`"$qdrantConfig`"", '--disable-telemetry') `
            -WorkingDirectory $qdrantRoot `
            -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $logRoot 'qdrant.stdout.log') `
            -RedirectStandardError (Join-Path $logRoot 'qdrant.stderr.log') | Out-Null
    }

    Wait-TcpPort -Port 6333 -Name 'Qdrant HTTP' | Out-Null
    Wait-TcpPort -Port 6334 -Name 'Qdrant gRPC' | Out-Null
    try {
        Invoke-RestMethod -Uri "http://$hostAddress`:6333/healthz" -TimeoutSec 3 | Out-Null
    }
    catch {
        throw "Qdrant ports opened, but /healthz failed: $($_.Exception.Message)"
    }
    Write-Host 'Started successfully.' -ForegroundColor Green
}

$failures = [System.Collections.Generic.List[string]]::new()
foreach ($starter in @('Start-PostgreSql', 'Start-Redis', 'Start-Qdrant')) {
    try {
        & $starter
    }
    catch {
        $failures.Add("$starter`: $($_.Exception.Message)")
        Write-Host "FAILED: $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host "`n----------------------------------------"
Write-Host "PostgreSQL : postgresql://127.0.0.1:5432"
Write-Host "Redis      : redis://127.0.0.1:6379/1"
Write-Host "Qdrant     : http://127.0.0.1:6333"
Write-Host "----------------------------------------"

if ($failures.Count -gt 0) {
    Write-Host "`n$($failures.Count) service(s) failed:" -ForegroundColor Red
    $failures | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}

Write-Host "`nAll local infrastructure services are ready." -ForegroundColor Green
exit 0
