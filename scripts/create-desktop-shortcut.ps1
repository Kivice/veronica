$root = Split-Path -Parent $PSScriptRoot
$desktopFolder = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::DesktopDirectory)
$shortcutPath = Join-Path $desktopFolder "Veronica Tactical Assistant.lnk"
$iconPath = Join-Path $root "apps\desktop\assets\veronica.ico"
$startScript = Join-Path $root "scripts\start.ps1"

$wshShell = New-Object -ComObject WScript.Shell
$shortcut = $wshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-ExecutionPolicy Bypass -NoProfile -File `"$startScript`""
$shortcut.WorkingDirectory = $root
$shortcut.Description = "Veronica: Tactical AI Desktop Assistant"
if (Test-Path $iconPath) {
    $shortcut.IconLocation = "$iconPath, 0"
}
$shortcut.WindowStyle = 1
$shortcut.Save()

Write-Host "[SUCCESS] 1-Click Desktop Shortcut created at: $shortcutPath" -ForegroundColor Green
