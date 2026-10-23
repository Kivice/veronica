#!/usr/bin/env pwsh
# One command to verify the foundation: Python unit/server tests, then Node<->Python integration test.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$vpy  = Join-Path $root 'services/voice/.venv/Scripts/python.exe'
Push-Location (Join-Path $root 'services/voice')
try { & $vpy -m pytest -q; if ($LASTEXITCODE -ne 0) { throw 'pytest failed' } } finally { Pop-Location }
Push-Location $root
try { node --test "tests/integration/*.test.mjs"; if ($LASTEXITCODE -ne 0) { throw 'node integration failed' } } finally { Pop-Location }
Write-Host 'VERIFY OK'
