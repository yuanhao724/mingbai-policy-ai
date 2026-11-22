$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $root "backend")

Write-Host "Mori running at http://127.0.0.1:8000"
Write-Host "Local mode works without an API key. Add OPENAI_API_KEY in .env for the online model."

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
