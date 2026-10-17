[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if ([IO.Path]::GetPathRoot($ProjectRoot) -ne "D:\") {
    throw "TraceRepair verification must run from D:. Current path: $ProjectRoot"
}

Set-Location -LiteralPath $ProjectRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "D: virtual environment is missing. Run scripts\setup.ps1 first."
}

$env:TEMP = Join-Path $ProjectRoot "tmp"
$env:TMP = $env:TEMP
$env:PIP_CACHE_DIR = Join-Path $ProjectRoot ".cache\pip"
$env:PYTHONPYCACHEPREFIX = Join-Path $ProjectRoot ".cache\pycache"
New-Item -ItemType Directory -Force -Path $env:TEMP, $env:PIP_CACHE_DIR, $env:PYTHONPYCACHEPREFIX | Out-Null

& $Python scripts\export_web_demo.py
if ($LASTEXITCODE -ne 0) { throw "Demo export failed." }
& $Python scripts\verify_release.py
if ($LASTEXITCODE -ne 0) { throw "Release safety checks failed." }
& $Python -m pytest -q --basetemp (Join-Path $ProjectRoot "tmp\pytest-verify")
if ($LASTEXITCODE -ne 0) { throw "Test suite failed." }
git diff --check
if ($LASTEXITCODE -ne 0) { throw "Git whitespace check failed." }
Write-Host "TraceRepair verification completed successfully." -ForegroundColor Green
