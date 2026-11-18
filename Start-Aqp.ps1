param(
    [int]$Port = 8000,
    [switch]$EnableBailianAgent,
    [switch]$PromptBailianKey
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONPATH = Join-Path $PSScriptRoot 'backend'
$env:PYTHONUTF8 = '1'
if (-not (Test-Path -LiteralPath 'frontend/dist/index.html')) { throw '请先执行 frontend 中的 npm run build' }
if ($PromptBailianKey -and -not $EnableBailianAgent) { throw '请输入 -EnableBailianAgent 以启用百炼 Agent' }
if ($EnableBailianAgent) {
    $env:AQP_BAILIAN_AGENT_DB = if ($env:AQP_DB) { $env:AQP_DB } else { Join-Path $PSScriptRoot 'data/aqp.sqlite3' }
}
$worker = Start-Process -FilePath (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') -ArgumentList '-m aqp.paper_worker' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru
try {
if ($PromptBailianKey) {
    $bailianKey = Read-Host '输入百炼 API Key' -AsSecureString
    $bailianKeyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($bailianKey)
    try {
        $env:AQP_MODEL_KEY_BAILIAN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bailianKeyPointer)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bailianKeyPointer)
        $bailianKey.Dispose()
    }
}
& .venv\Scripts\python.exe -m uvicorn aqp.app:create_app --factory --host 127.0.0.1 --port $Port

} finally {
    if ($PromptBailianKey) { Remove-Item Env:AQP_MODEL_KEY_BAILIAN -ErrorAction SilentlyContinue }
    if ($worker -and -not $worker.HasExited) { Stop-Process -Id $worker.Id -ErrorAction SilentlyContinue }
}
