@echo off
setlocal
title OmniCart Local Infrastructure

if /I "%~1"=="--no-pause" (
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-local-infra.ps1"
) else (
    powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-local-infra.ps1" %*
)
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Startup failed. Review the message above.
)

if /I not "%~1"=="--no-pause" pause
exit /b %EXIT_CODE%
