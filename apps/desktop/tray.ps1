<#
.SYNOPSIS
  Project Veronica // Windows System Tray Resident & HUD Controller
  Maintains system tray icon, listens for "Hey Veronica" wake-word via WebSocket,
  and launches / manages the miniature desktop UI and full tactical deck.
#>

param (
    [int]$Port = 8765,
    [string]$Token = ""
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName PresentationCore

# Pin User32 APIs for window activation
$cSource = @"
using System;
using System.Runtime.InteropServices;

public class Win32 {
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);

    public const int SW_RESTORE = 9;
    public const int SW_SHOW = 5;
}
"@
if (-not ([System.Management.Automation.PSTypeName]'Win32').Type) {
    Add-Type -TypeDefinition $cSource
}

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$icoPath = Join-Path $PSScriptRoot "assets/veronica.ico"
$miniHtml = Join-Path $PSScriptRoot "mini.html"
$fullHtml = Join-Path $PSScriptRoot "index.html"

# Browser paths
$edgePath = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $edgePath)) {
    $edgePath = "${env:ProgramFiles}\Microsoft\Edge\Application\msedge.exe"
}
$chromePath = "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe"
$browserBin = if (Test-Path $edgePath) { $edgePath } elseif (Test-Path $chromePath) { $chromePath } else { "" }

# Calculate position for bottom-right corner (above system tray)
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$miniWidth = 440
$miniHeight = 280
$posX = [Math]::Max(50, $screen.Width - $miniWidth - 20)
$posY = [Math]::Max(50, $screen.Height - $miniHeight - 20)

$global:miniProcess = $null
$global:fullProcess = $null

function Launch-MiniHUD {
    $miniUrl = "file:///$($miniHtml.Replace('\', '/'))?port=$Port&token=$Token"
    if ($global:miniProcess -and -not $global:miniProcess.HasExited) {
        try {
            [Win32]::ShowWindowAsync($global:miniProcess.MainWindowHandle, [Win32]::SW_RESTORE)
            [Win32]::SetForegroundWindow($global:miniProcess.MainWindowHandle) | Out-Null
            return
        } catch {}
    }

    if ($browserBin) {
        $argList = @(
            "--app=`"$miniUrl`"",
            "--window-size=$miniWidth,$miniHeight",
            "--window-position=$posX,$posY"
        )
        $global:miniProcess = Start-Process -FilePath $browserBin -ArgumentList $argList -PassThru
    } else {
        Start-Process $miniUrl
    }
}

function Launch-FullHUD {
    $fullUrl = "file:///$($fullHtml.Replace('\', '/'))?port=$Port&token=$Token"
    if ($global:fullProcess -and -not $global:fullProcess.HasExited) {
        try {
            [Win32]::ShowWindowAsync($global:fullProcess.MainWindowHandle, [Win32]::SW_RESTORE)
            [Win32]::SetForegroundWindow($global:fullProcess.MainWindowHandle) | Out-Null
            return
        } catch {}
    }

    if ($browserBin) {
        $argList = @(
            "--app=`"$fullUrl`"",
            "--window-size=1280,840"
        )
        $global:fullProcess = Start-Process -FilePath $browserBin -ArgumentList $argList -PassThru
    } else {
        Start-Process $fullUrl
    }
}

# Create System Tray NotifyIcon
$notifyIcon = New-Object System.Windows.Forms.NotifyIcon
if (Test-Path $icoPath) {
    $notifyIcon.Icon = New-Object System.Drawing.Icon($icoPath)
} else {
    $notifyIcon.Icon = [System.Drawing.SystemIcons]::Application
}
$notifyIcon.Text = "Project Veronica // Tactical Desktop Agent"
$notifyIcon.Visible = $true

# Context Menu
$contextMenu = New-Object System.Windows.Forms.ContextMenuStrip

$headerItem = New-Object System.Windows.Forms.ToolStripMenuItem
$headerItem.Text = "VERONICA // ONLINE"
$headerItem.Enabled = $false
$contextMenu.Items.Add($headerItem) | Out-Null

$contextMenu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

$miniItem = New-Object System.Windows.Forms.ToolStripMenuItem
$miniItem.Text = "🎙️ Miniature HUD (`"Hey Veronica`")"
$miniItem.add_Click({ Launch-MiniHUD })
$contextMenu.Items.Add($miniItem) | Out-Null

$fullItem = New-Object System.Windows.Forms.ToolStripMenuItem
$fullItem.Text = "🖥️ Full Tactical Deck"
$fullItem.add_Click({ Launch-FullHUD })
$contextMenu.Items.Add($fullItem) | Out-Null

$vitalsItem = New-Object System.Windows.Forms.ToolStripMenuItem
$vitalsItem.Text = "📊 System Vitals Snapshot"
$vitalsItem.add_Click({
    $notifyIcon.ShowBalloonTip(3000, "Veronica Telemetry", "Voice Core: 127.0.0.1:$Port (Active)`nSay 'Hey Veronica' to interact.", [System.Windows.Forms.ToolTipIcon]::Info)
})
$contextMenu.Items.Add($vitalsItem) | Out-Null

$contextMenu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

$exitItem = New-Object System.Windows.Forms.ToolStripMenuItem
$exitItem.Text = "❌ Shutdown Veronica"
$exitItem.add_Click({
    $notifyIcon.Visible = $false
    $notifyIcon.Dispose()
    # Stop Voice Service
    Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -like '*veronica_voice*' } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    [System.Windows.Forms.Application]::Exit()
})
$contextMenu.Items.Add($exitItem) | Out-Null

$notifyIcon.ContextMenuStrip = $contextMenu

# Left-click or double-click tray icon -> Launch / Toggle Miniature HUD
$notifyIcon.add_Click({
    param($sender, $e)
    if ($e.Button -eq [System.Windows.Forms.MouseButtons]::Left) {
        Launch-MiniHUD
    }
})

$notifyIcon.ShowBalloonTip(4000, "Veronica Online", "Veronica is standing by in your system tray.`nSay 'Hey Veronica' or click tray to activate.", [System.Windows.Forms.ToolTipIcon]::Info)

# Background WebSocket Listener for wake-word & window commands
$wsScript = {
    param($Port, $Token, $NotifyIcon)
    try {
        $ws = New-Object System.Net.WebSockets.ClientWebSocket
        $uri = New-Object System.Uri("ws://127.0.0.1:$Port")
        $cts = New-Object System.Threading.CancellationTokenSource
        $ws.ConnectAsync($uri, $cts.Token).Wait()

        $helloJson = "{`"v`":1,`"id`":`"tray_auth`",`"type`":`"hello`",`"payload`":{`"token`":`"$Token`"}}"
        $helloBytes = [System.Text.Encoding]::UTF8.GetBytes($helloJson)
        $segment = New-Object System.ArraySegment[byte] -ArgumentList @(,$helloBytes)
        $ws.SendAsync($segment, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $cts.Token).Wait()

        $buffer = New-Object byte[] 4096
        while ($ws.State -eq [System.Net.WebSockets.WebSocketState]::Open) {
            $recvSegment = New-Object System.ArraySegment[byte] -ArgumentList @(,$buffer)
            $result = $ws.ReceiveAsync($recvSegment, $cts.Token).Result
            if ($result.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Close) {
                break
            }
            $msg = [System.Text.Encoding]::UTF8.GetString($buffer, 0, $result.Count)
            if ($msg.Contains('"show_mini"') -or $msg.Contains('"wake_word.detected"')) {
                # Trigger action file flag
                $flag = Join-Path $env:TEMP "veronica_show_mini.flag"
                Set-Content -Path $flag -Value "1" -Force
            }
        }
    } catch {}
}

# Run background thread with PowerShell Runspace
$runspace = [runspacefactory]::CreateRunspace()
$runspace.Open()
$powershell = [powershell]::Create()
$powershell.Runspace = $runspace
$powershell.AddScript($wsScript).AddArgument($Port).AddArgument($Token).AddArgument($notifyIcon) | Out-Null
$powershell.BeginInvoke() | Out-Null

# Periodic timer in UI thread to check for wake-word trigger flag
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 250
$timer.add_Tick({
    $flag = Join-Path $env:TEMP "veronica_show_mini.flag"
    if (Test-Path $flag) {
        Remove-Item $flag -Force -ErrorAction SilentlyContinue
        Launch-MiniHUD
    }
})
$timer.Start()

# Windows Forms Application Loop
[System.Windows.Forms.Application]::Run()
