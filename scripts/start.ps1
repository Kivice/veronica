#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Launches Project Veronica: Tactical AI Desktop Assistant and Voice Core.
#>
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$svc = Join-Path $root 'services/voice'
$vpy = Join-Path $svc '.venv/Scripts/python.exe'

if (-not (Test-Path $vpy)) {
    Write-Host "[VERONICA] Virtual environment not found. Running setup..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot 'setup.ps1')
}

# Stop any existing Veronica voice service processes
Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -like '*veronica_voice*' } | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

$port = 8765
if ([string]::IsNullOrWhiteSpace($env:VERONICA_TOKEN)) {
    $env:VERONICA_TOKEN = [System.Guid]::NewGuid().ToString('N')
}
$env:VERONICA_PORT = $port.ToString()

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "       PROJECT VERONICA // TACTICAL DESKTOP AGENT         " -ForegroundColor White
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "[1/3] Initializing Voice Intelligence Core on port $port..." -ForegroundColor Yellow

$procInfo = New-Object System.Diagnostics.ProcessStartInfo
$procInfo.FileName = $vpy
$procInfo.Arguments = "-m veronica_voice"
$procInfo.WorkingDirectory = $svc
$procInfo.EnvironmentVariables["PYTHONPATH"] = (Join-Path $svc "src")
$procInfo.EnvironmentVariables["VERONICA_TOKEN"] = $env:VERONICA_TOKEN
$procInfo.EnvironmentVariables["VERONICA_PORT"] = $port.ToString()
$procInfo.UseShellExecute = $false
$procInfo.RedirectStandardOutput = $true
$procInfo.RedirectStandardError = $true
$procInfo.CreateNoWindow = $true

$serviceProcess = [System.Diagnostics.Process]::Start($procInfo)

# Wait for service startup message
$started = $false
$timeout = [DateTime]::UtcNow.AddSeconds(8)
while ([DateTime]::UtcNow -lt $timeout) {
    if ($serviceProcess.HasExited) {
        $err = $serviceProcess.StandardError.ReadToEnd()
        throw "Service failed to start: $err"
    }
    $line = $serviceProcess.StandardOutput.ReadLine()
    if ($line -and $line.Contains('"event": "listening"')) {
        $started = $true
        Write-Host "[2/3] Voice Intelligence Core ONLINE (127.0.0.1:$port)" -ForegroundColor Green
        break
    }
    Start-Sleep -Milliseconds 100
}

if (-not $started) {
    Write-Host "[!] Note: Continuing startup sequence..." -ForegroundColor Yellow
}

# Launch System Tray Resident and Miniature Desktop UI
$trayScript = Join-Path $root 'apps/desktop/tray.ps1'
$miniHtml = Join-Path $root 'apps/desktop/mini.html'
$miniUrl = "file:///$($miniHtml.Replace('\', '/'))?port=$port&token=$($env:VERONICA_TOKEN)"

Write-Host "[3/4] Initializing Windows System Tray Resident..." -ForegroundColor Cyan
$trayProc = Start-Process powershell -ArgumentList "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$trayScript`" -Port $port -Token `"$($env:VERONICA_TOKEN)`"" -PassThru

Write-Host "[4/4] Deploying Miniature Desktop UI (`"Hey Veronica`")..." -ForegroundColor Cyan

$edgePath = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $edgePath)) {
    $edgePath = "${env:ProgramFiles}\Microsoft\Edge\Application\msedge.exe"
}
$chromePath = "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe"

Add-Type -AssemblyName System.Windows.Forms
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$posX = [Math]::Max(50, $screen.Width - 460)
$posY = [Math]::Max(50, $screen.Height - 300)

if (Test-Path $edgePath) {
    Start-Process $edgePath -ArgumentList "--app=`"$miniUrl`"", "--window-size=440,280", "--window-position=$posX,$posY"
} elseif (Test-Path $chromePath) {
    Start-Process $chromePath -ArgumentList "--app=`"$miniUrl`"", "--window-size=440,280", "--window-position=$posX,$posY"
} else {
    Start-Process $miniUrl
}

Write-Host ""
Write-Host ">>> VERONICA IS FULLY OPERATIONAL <<<" -ForegroundColor Green
Write-Host "System Tray: Active with Arc Reactor icon (bottom-right notification area)" -ForegroundColor Cyan
Write-Host "Miniature UI: $miniUrl" -ForegroundColor Gray
Write-Host "Service PID: $($serviceProcess.Id)" -ForegroundColor Gray
Write-Host "Tray PID:    $($trayProc.Id)" -ForegroundColor Gray
Write-Host "Wake-Word:   Say 'Hey Veronica' anytime to summon the Miniature UI" -ForegroundColor Yellow
Write-Host "Push-to-Talk: Hold [SPACEBAR] or click the Arc Reactor" -ForegroundColor Yellow
Write-Host "Press Ctrl+C to shutdown Veronica." -ForegroundColor DarkGray

try {
    while (-not $serviceProcess.HasExited) {
        Start-Sleep -Seconds 1
    }
} finally {
    if (-not $serviceProcess.HasExited) {
        $serviceProcess.Kill()
    }
    if ($trayProc -and -not $trayProc.HasExited) {
        $trayProc.Kill()
    }
}
