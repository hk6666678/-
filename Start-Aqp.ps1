param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONPATH = Join-Path $PSScriptRoot 'backend'
$env:PYTHONUTF8 = '1'
if (-not (Test-Path -LiteralPath 'frontend/dist/index.html')) { throw '请先执行 frontend 中的 npm run build' }
& .venv\Scripts\python.exe -m uvicorn aqp.app:create_app --factory --host 127.0.0.1 --port $Port
