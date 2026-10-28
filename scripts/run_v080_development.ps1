[CmdletBinding()]
param(
    [switch]$SkipFunctionBenchmark,
    [switch]$SkipRetrieval
)

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

Write-Host "[0/5] Verify deterministic prompt security evidence"
& $Python scripts\evaluate_prompt_security.py --verify
if ($LASTEXITCODE -ne 0) { throw "Prompt security evidence verification failed." }

if (-not $SkipFunctionBenchmark) {
    Write-Host "[1/5] Native Function Calling connectivity probe (one provider request)"
    & $Python scripts\function_calling_probe.py
    if ($LASTEXITCODE -ne 0) { throw "Function Calling probe failed safely." }

    Write-Host "[2/5] Paired five-task development benchmark (no locked tasks)"
    & $Python scripts\run_benchmark.py `
        --manifest evaluation\benchmarks\function-calling-v0.8.0-dev1.json `
        --split development
    if ($LASTEXITCODE -ne 0) { throw "Function Calling development benchmark failed." }

    Write-Host "[3/5] Custom JSON versus native Function Calling report"
    & $Python scripts\compare_planner_protocols.py
    if ($LASTEXITCODE -ne 0) { throw "Planner protocol comparison failed." }
}

if (-not $SkipRetrieval) {
    Write-Host "[4/5] Semantic retrieval development evaluation"
    & $Python scripts\evaluate_retrieval.py --embedding bailian
    if ($LASTEXITCODE -ne 0) { throw "Semantic retrieval evaluation failed safely." }

    Write-Host "[5/5] Enforce semantic retrieval activation gate"
    & $Python scripts\evaluate_retrieval_gate.py
    if ($LASTEXITCODE -ne 0) { throw "Semantic retrieval did not pass the dev2 activation gate." }
}

Write-Host "0.8 development evaluation completed. No locked task was run." -ForegroundColor Green
