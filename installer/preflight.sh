#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_root
say "TwinPanel preflight"

for cmd in bash ss curl openssl sed awk grep find readlink ln mv; do need "$cmd"; done

SOURCE_ROOT="${TWINPANEL_SOURCE_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
[[ -f "$SOURCE_ROOT/package.json" ]] || fail "package.json پیدا نشد: $SOURCE_ROOT"
[[ -f "$SOURCE_ROOT/backend/requirements.txt" ]] || fail "backend/requirements.txt پیدا نشد"
[[ -f "$SOURCE_ROOT/backend/create_admin.py" ]] || fail "backend/create_admin.py پیدا نشد"
[[ -f "$SOURCE_ROOT/backend/app/main.py" ]] || fail "Backend runtime هنوز به backend/app وارد نشده است. ابتدا import سالم سرور قدیمی را انجام دهید."

python3 - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit("Python 3.12+ required")
print("PYTHON_OK", sys.version.split()[0])
PY

if command -v node >/dev/null 2>&1; then
  node - <<'JS'
const major=Number(process.versions.node.split('.')[0]);
if(major<22){console.error('Node.js 22+ required');process.exit(1)}
console.log('NODE_OK',process.versions.node)
JS
else
  fail "Node.js 22+ نصب نیست"
fi

if command -v npm >/dev/null 2>&1; then npm --version >/dev/null; else fail "npm نصب نیست"; fi
if command -v nginx >/dev/null 2>&1; then nginx -v 2>&1; else warn "nginx هنوز نصب نیست؛ install.sh آن را نصب می‌کند"; fi
if command -v psql >/dev/null 2>&1; then psql --version; else warn "PostgreSQL client هنوز نصب نیست؛ install.sh آن را نصب می‌کند"; fi
if command -v redis-cli >/dev/null 2>&1; then redis-cli --version; else warn "Redis client هنوز نصب نیست؛ install.sh آن را نصب می‌کند"; fi

[[ ! -e "$SOURCE_ROOT/.env" ]] || warn "فایل .env در سورس وجود دارد؛ Installer آن را به Release کپی نمی‌کند"

forbidden="$(find "$SOURCE_ROOT/backend" -type f \( \
  -name '*.key' -o -name '*.pem' -o -name '*.p12' -o -name '*.pfx' -o \
  -name '*.sql' -o -name '*.dump' -o -name '*.sqlite' -o -name '*.sqlite3' -o \
  -name '*.bak*' -o -name '*candidate*' -o -name '*before-*' \
\) -print 2>/dev/null || true)"
[[ -z "$forbidden" ]] || { printf '%s\n' "$forbidden"; fail "فایل ممنوع داخل backend پیدا شد"; }

python3 -m compileall -q "$SOURCE_ROOT/backend/app" "$SOURCE_ROOT/backend/create_admin.py"
find "$SOURCE_ROOT/backend" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$SOURCE_ROOT/backend" -type f -name '*.pyc' -delete 2>/dev/null || true

info "PREFLIGHT_OK"
