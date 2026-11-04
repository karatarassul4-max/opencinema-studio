$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$python = Join-Path (Get-Location) '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = 'python' }
# Inference defaults off. UVICORN_HOST/UVICORN_PORT are process-local overrides.
if (-not $env:UVICORN_HOST) { $env:UVICORN_HOST = '127.0.0.1' }
if (-not $env:UVICORN_PORT) { $env:UVICORN_PORT = '8001' }
& $python -B -m uvicorn app.main:app --workers 1
