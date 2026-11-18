$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
Push-Location -LiteralPath (Join-Path $PSScriptRoot '..')
try {
    & .\.venv\Scripts\python.exe -m pytest -q `
        backend/tests/test_model_connection.py::test_external_config_cannot_send_from_ordinary_app `
        backend/tests/test_agent.py::test_agent_does_not_send_summary_after_tool_scope_changes `
        backend/tests/test_live_harness.py::test_live_harness_offline
    $testExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $testExitCode
