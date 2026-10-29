@echo off
title Project Veronica // Tactical Desktop Assistant
cd /d "%~dp0.."
where pwsh >nul 2>&1
if %errorlevel% equ 0 (
    pwsh -ExecutionPolicy Bypass -File "%~dp0start.ps1"
) else (
    powershell.exe -ExecutionPolicy Bypass -File "%~dp0start.ps1"
)
exit /b
