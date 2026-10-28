[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if ([IO.Path]::GetPathRoot($ProjectRoot) -ne "D:\") {
    throw "TraceRepair development evaluation must run from D:."
}

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "D: virtual environment is missing. Run scripts\setup.ps1 first."
}
if (-not $env:DASHSCOPE_API_KEY -or -not $env:TRACEREPAIR_BAILIAN_BASE_URL) {
    throw "Configure DASHSCOPE_API_KEY and TRACEREPAIR_BAILIAN_BASE_URL in this PowerShell session."
}

Set-Location -LiteralPath $ProjectRoot
$env:TEMP = Join-Path $ProjectRoot "tmp"
$env:TMP = $env:TEMP
$env:PYTHONPYCACHEPREFIX = Join-Path $ProjectRoot ".cache\pycache"
New-Item -ItemType Directory -Force -Path $env:TEMP, $env:PYTHONPYCACHEPREFIX | Out-Null

Write-Host "Activated RAG development repair evaluation (five known tasks; no locked tasks)"
& $Python scripts\run_benchmark.py `
    --manifest evaluation\benchmarks\rag-repair-v0.8.0-dev2.1.json `
    --split development
if ($LASTEXITCODE -ne 0) { throw "RAG development repair benchmark failed." }

Write-Host "RAG development repair evaluation completed. No locked task was run." -ForegroundColor Green
