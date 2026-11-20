param(
    [int]$Port = 8000,
    [switch]$EnableBailianAgent,
    [switch]$PromptBailianKey,
    [switch]$SaveBailianKey
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYTHONPATH = Join-Path $PSScriptRoot 'backend'
$env:PYTHONUTF8 = '1'
if ($SaveBailianKey) {
    $Host.UI.RawUI.WindowTitle = 'AQP-PGS 保存百炼凭证'
    $key = Read-Host '输入百炼 API Key（输入隐藏，留空取消）' -AsSecureString
    $keyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($key)
    $previousKey = $env:AQP_MODEL_KEY_BAILIAN
    try {
        $env:AQP_MODEL_KEY_BAILIAN = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPointer)
        & .venv\Scripts\python.exe tools\bailian_credential.py --save
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPointer)
        $key.Dispose()
        $env:AQP_MODEL_KEY_BAILIAN = $previousKey
    }
    return
}
if (-not (Test-Path -LiteralPath 'frontend/dist/index.html')) { throw '请先执行 frontend 中的 npm run build' }
if ($PromptBailianKey -and -not $EnableBailianAgent) { throw '请输入 -EnableBailianAgent 以启用百炼 Agent' }
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
$serverArgs = @('--port', "$Port")
if ($EnableBailianAgent) { $serverArgs += '--enable-agent' }
& .venv\Scripts\python.exe tools\bailian_credential.py @serverArgs

} finally {
    if ($PromptBailianKey) { Remove-Item Env:AQP_MODEL_KEY_BAILIAN -ErrorAction SilentlyContinue }
    if ($worker -and -not $worker.HasExited) { Stop-Process -Id $worker.Id -ErrorAction SilentlyContinue }
}
