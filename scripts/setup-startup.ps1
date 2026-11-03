param(
    [switch]$Remove,
    [switch]$Minimized
)

$root = Split-Path -Parent $PSScriptRoot
$startupFolder = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Startup)
$shortcutPath = Join-Path $startupFolder "Veronica.lnk"
$iconPath = Join-Path $root "apps\desktop\assets\veronica.ico"
$startScript = Join-Path $root "scripts\start.ps1"

if ($Remove) {
    if (Test-Path $shortcutPath) {
        Remove-Item $shortcutPath -Force
        Write-Host "[VERONICA] Startup shortcut removed from: $shortcutPath" -ForegroundColor Yellow
    } else {
        Write-Host "[VERONICA] Startup shortcut was not registered." -ForegroundColor Gray
    }
    return
}

$wshShell = New-Object -ComObject WScript.Shell
$shortcut = $wshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "powershell.exe"
$windowStyle = if ($Minimized) { "7" } else { "1" }
$shortcut.Arguments = "-ExecutionPolicy Bypass -NoProfile -File `"$startScript`""
$shortcut.WorkingDirectory = $root
$shortcut.Description = "Veronica: Tactical AI Desktop Assistant"
if (Test-Path $iconPath) {
    $shortcut.IconLocation = "$iconPath, 0"
}
$shortcut.WindowStyle = [int]$windowStyle
$shortcut.Save()

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "       PROJECT VERONICA // AUTO-START CONFIGURATION       " -ForegroundColor White
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "[SUCCESS] Veronica configured to launch on Windows startup." -ForegroundColor Green
Write-Host "Location: $shortcutPath" -ForegroundColor Gray
Write-Host "To remove later, run: .\scripts\setup-startup.ps1 -Remove" -ForegroundColor DarkGray

