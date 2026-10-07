#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-3010}"
HOST="${HOST:-127.0.0.1}"

if ! command -v node >/dev/null 2>&1; then
  echo "ERROR: Node.js is not installed. Node >=22.13 is required."
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: npm is not installed."
  exit 1
fi

if ss -ltn "sport = :${PORT}" 2>/dev/null | grep -q LISTEN; then
  echo "ERROR: Preview port ${PORT} is already in use."
  exit 1
fi

echo "[TwinPanel] Installing dependencies..."
if [ -f package-lock.json ]; then
  npm ci
else
  npm install --no-audit --no-fund
fi

echo "[TwinPanel] Building UI..."
npm run build

echo "[TwinPanel] Preview: http://${HOST}:${PORT}"
echo "[TwinPanel] Stop with Ctrl+C"
exec ./node_modules/.bin/next start -H "${HOST}" -p "${PORT}"
