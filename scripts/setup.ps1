#!/usr/bin/env pwsh
# Project-local setup only: creates services/voice/.venv and installs pinned-range deps. No system installs.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$svc  = Join-Path $root 'services/voice'
$py   = 'C:\Python313\python.exe'
if (-not (Test-Path $py)) { $py = (py -3.13 -c "import sys;print(sys.executable)") }
if (-not (Test-Path (Join-Path $svc '.venv'))) { & $py -m venv (Join-Path $svc '.venv') }
$vpy = Join-Path $svc '.venv/Scripts/python.exe'
& $vpy -m pip install --disable-pip-version-check -q -e "$svc[dev]" 2>&1 | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }
Write-Host "setup ok: $(& $vpy --version)"
