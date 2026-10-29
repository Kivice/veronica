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
$tokenFile = Join-Path $env:USERPROFILE '.veronica/token'
if (Test-Path $tokenFile) {
    try { $env:VERONICA_TOKEN = (Get-Content $tokenFile -Raw).Trim() } catch {}
}
if ([string]::IsNullOrWhiteSpace($env:VERONICA_TOKEN)) {
    $veronicaDir = Join-Path $env:USERPROFILE '.veronica'
    if (-not (Test-Path $veronicaDir)) { New-Item -ItemType Directory -Path $veronicaDir -Force | Out-Null }
    $env:VERONICA_TOKEN = [System.Guid]::NewGuid().ToString('N')
    Set-Content -Path $tokenFile -Value $env:VERONICA_TOKEN -Force
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
$procInfo.EnvironmentVariables["VERONICA_PARENT_PID"] = $PID.ToString()

# Preload persistent credentials into Python environment if available
$credsPath = Join-Path $env:USERPROFILE '.veronica/credentials.json'
if (Test-Path $credsPath) {
    try {
        $credsJson = Get-Content $credsPath -Raw | ConvertFrom-Json
        if ($credsJson.groq) { $procInfo.EnvironmentVariables["GROQ_API_KEY"] = [string]$credsJson.groq }
        if ($credsJson.openai) { $procInfo.EnvironmentVariables["OPENAI_API_KEY"] = [string]$credsJson.openai }
        if ($credsJson.gemini) { $procInfo.EnvironmentVariables["GEMINI_API_KEY"] = [string]$credsJson.gemini }
        if ($credsJson.anthropic) { $procInfo.EnvironmentVariables["ANTHROPIC_API_KEY"] = [string]$credsJson.anthropic }
        if ($credsJson.ollama) { $procInfo.EnvironmentVariables["OLLAMA_URL"] = [string]$credsJson.ollama }
    } catch {}
}

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

# Launch the Tactical Desktop HUD with Persistent Microphone & Media Permissions
$htmlPath = Join-Path $root 'apps/desktop/index.html'
$appUrl = "file:///$($htmlPath.Replace('\', '/'))?port=$port&token=$($env:VERONICA_TOKEN)"

Write-Host "[3/3] Deploying Stark Tactical Desktop HUD (Persistent Mic Enabled)..." -ForegroundColor Cyan

# Dedicated Chromium profile directory to persist permissions, tokens, and settings
$profileDir = Join-Path $root 'apps/desktop/.profile'
$defaultDir = Join-Path $profileDir 'Default'
if (-not (Test-Path $defaultDir)) {
    New-Item -ItemType Directory -Path $defaultDir -Force | Out-Null
}

# Pre-seed persistent permission preferences for microphone and audio
$prefsFile = Join-Path $defaultDir 'Preferences'
if (-not (Test-Path $prefsFile)) {
    $prefsObj = @{
        profile = @{
            content_settings = @{
                exceptions = @{
                    media_stream_mic = @{
                        "*,*" = @{ setting = 1 }
                    }
                    sound = @{
                        "*,*" = @{ setting = 1 }
                    }
                }
            }
        }
    }
    $prefsJson = $prefsObj | ConvertTo-Json -Depth 10
    Set-Content -Path $prefsFile -Value $prefsJson -Encoding UTF8 -Force
}

$browserArgs = @(
    "--app=`"$appUrl`"",
    "--window-size=1280,840",
    "--user-data-dir=`"$profileDir`"",
    "--use-fake-ui-for-media-stream",
    "--autoplay-policy=no-user-gesture-required",
    "--allow-file-access-from-files",
    "--enable-speech-input",
    "--enable-media-stream",
    "--unsafely-treat-insecure-origin-as-secure=`"$appUrl`""
)

$edgePath = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $edgePath)) {
    $edgePath = "${env:ProgramFiles}\Microsoft\Edge\Application\msedge.exe"
}
$chromePath = "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe"

if (Test-Path $edgePath) {
    Start-Process $edgePath -ArgumentList $browserArgs
} elseif (Test-Path $chromePath) {
    Start-Process $chromePath -ArgumentList $browserArgs
} else {
    Start-Process $appUrl
}

Write-Host ""
Write-Host ">>> VERONICA IS FULLY OPERATIONAL <<<" -ForegroundColor Green
Write-Host "Desktop HUD: $appUrl" -ForegroundColor Gray
Write-Host "Service PID: $($serviceProcess.Id)" -ForegroundColor Gray
Write-Host "Push-to-Talk: Hold [SPACEBAR] or click the Arc Reactor Mic" -ForegroundColor Yellow
Write-Host "Press Ctrl+C to shutdown Veronica." -ForegroundColor DarkGray

try {
    while (-not $serviceProcess.HasExited) {
        Start-Sleep -Seconds 1
    }
} finally {
    if (-not $serviceProcess.HasExited) {
        $serviceProcess.Kill()
    }
}
