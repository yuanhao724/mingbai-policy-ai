#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/backend"
echo "Mori running at http://127.0.0.1:8000"
echo "Local mode works without an API key. Add OPENAI_API_KEY in .env for the online model."

python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
