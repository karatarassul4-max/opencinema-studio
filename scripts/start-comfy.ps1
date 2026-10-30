param([string]$ComfyRoot = "$env:LOCALAPPDATA\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI")
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
if (-not (Test-Path -LiteralPath "$ComfyRoot\.venv\Scripts\python.exe")) { throw 'Existing ComfyUI Python not found. Pass -ComfyRoot.' }
try {
    $null = Invoke-RestMethod 'http://127.0.0.1:8188/system_stats' -TimeoutSec 2
    Write-Host 'ComfyUI is already running. Verify its model paths and reserve-vram configuration.'
    exit 0
} catch { }
New-Item -ItemType Directory -Force "$projectRoot\artifacts\input", "$projectRoot\artifacts\output" | Out-Null
Push-Location $ComfyRoot
try {
    & '.\.venv\Scripts\python.exe' main.py --extra-model-paths-config "$projectRoot\config\extra_model_paths.yaml" --output-directory "$projectRoot\artifacts\output" --input-directory "$projectRoot\artifacts\input" --reserve-vram 2
} finally { Pop-Location }
