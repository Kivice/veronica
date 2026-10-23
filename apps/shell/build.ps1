#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Builds the Native Microsoft .NET WPF Application (Veronica.Shell.exe)
  using the Microsoft C# Compiler (csc.exe) and native .NET Framework assemblies.
#>

$ErrorActionPreference = 'Stop'
$shellRoot = $PSScriptRoot
$srcDir = Join-Path $shellRoot 'src'
$binDir = Join-Path $shellRoot 'bin'

if (-not (Test-Path $binDir)) {
    New-Item -ItemType Directory -Path $binDir -Force | Out-Null
}

$csc = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $csc)) {
    throw "Microsoft C# Compiler not found at $csc"
}

# Resolve GAC and system assemblies via Windows PowerShell
Write-Host "[1/3] Resolving native Microsoft .NET Framework assemblies..." -ForegroundColor Cyan

function Get-GacPath($name) {
    $res = powershell.exe -NoProfile -Command "[System.Reflection.Assembly]::LoadWithPartialName('$name').Location"
    return $res.Trim()
}

$pf = Get-GacPath "PresentationFramework"
$pc = Get-GacPath "PresentationCore"
$wb = Get-GacPath "WindowsBase"
$xaml = Get-GacPath "System.Xaml"
$speech = Get-GacPath "System.Speech"

$refs = @(
    "/r:System.dll",
    "/r:System.Core.dll",
    "/r:System.Drawing.dll",
    "/r:System.Windows.Forms.dll",
    "/r:`"$pf`"",
    "/r:`"$pc`"",
    "/r:`"$wb`"",
    "/r:`"$xaml`"",
    "/r:`"$speech`""
)

$srcFiles = Get-ChildItem -Path $srcDir -Filter "*.cs" | ForEach-Object { "`"$($_.FullName)`"" }
$outputExe = Join-Path $binDir "Veronica.Shell.exe"
$icoPath = Join-Path $shellRoot "..\desktop\assets\veronica.ico"

Write-Host "[2/3] Compiling native Microsoft .NET desktop application..." -ForegroundColor Cyan

$args = @(
    "/target:winexe",
    "/optimize+",
    "/platform:x64",
    "/out:`"$outputExe`""
)
if (Test-Path $icoPath) {
    $args += "/win32icon:`"$icoPath`""
}
$args += $refs
$args += $srcFiles

$proc = Start-Process -FilePath $csc -ArgumentList ($args -join " ") -NoNewWindow -Wait -PassThru

if ($proc.ExitCode -ne 0) {
    throw "Compilation failed with exit code $($proc.ExitCode)"
}

Write-Host "[3/3] Native Microsoft .NET Application Built Successfully!" -ForegroundColor Green
Write-Host "Binary: $outputExe" -ForegroundColor White

# Copy assets next to binary for runtime resolution
$binAssets = Join-Path $binDir "assets"
if (-not (Test-Path $binAssets)) {
    New-Item -ItemType Directory -Path $binAssets -Force | Out-Null
}
Copy-Item (Join-Path $shellRoot "..\desktop\assets\*") $binAssets -Force
