$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path ".env")) {
    Write-Host "Copie .env.example para .env e configure GEMINI_API_KEY e DATABASE_URL." -ForegroundColor Yellow
    exit 1
}

$python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host "Crie o venv: python -m venv .venv && .\.venv\Scripts\pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

& $python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
