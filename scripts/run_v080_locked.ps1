$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$manifest = Join-Path $root "evaluation\benchmarks\function-rag-locked-v0.8.0.json"

if (-not (Test-Path -LiteralPath $python)) {
    throw "TraceRepair virtual environment is missing: $python"
}

Set-Location $root

Write-Host "[1/2] Offline oracle and frozen-contract preflight"
& $python scripts\run_benchmark.py --manifest $manifest --split locked --dry-run
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if (-not $env:DASHSCOPE_API_KEY -or -not $env:TRACEREPAIR_BAILIAN_BASE_URL) {
    throw "Bailian environment variables are not configured in this PowerShell session."
}

Write-Host "[2/2] Locked pass@1: three repositories, one attempt each, no retry"
& $python scripts\run_benchmark.py --manifest $manifest --split locked
exit $LASTEXITCODE
