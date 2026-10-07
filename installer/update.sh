#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="${TWINPANEL_SOURCE_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_root
load_install_env
load_backend_env
need rsync; need python3; need npm; need runuser; need pg_dump

CURRENT="$(current_release)"
[[ -n "$CURRENT" && -d "$CURRENT" ]] || fail "Release فعلی پیدا نشد"
[[ -f "$SOURCE_ROOT/backend/app/main.py" ]] || fail "سورس جدید فاقد backend/app/main.py است"
[[ -f "$SOURCE_ROOT/package.json" ]] || fail "سورس جدید فاقد package.json است"
if [[ "$(readlink -f "$SOURCE_ROOT")" == "$CURRENT" ]]; then
  fail "update.sh باید از سورس/Release جدید اجرا شود، نه از Release فعلی"
fi

say "TwinPanel update"
info "Current: $CURRENT"
info "Source : $SOURCE_ROOT"

install -d -m 700 "$TP_STATE/update-backups"
DB_BACKUP="$TP_STATE/update-backups/twinpanel-before-$(date -u +%Y%m%d-%H%M%S).dump"
umask 077
say "Creating pre-update database backup"
runuser -u postgres -- pg_dump -Fc twinpanel > "$DB_BACKUP"
chmod 600 "$DB_BACKUP"
info "DB_BACKUP=$DB_BACKUP"

VERSION="$(tr -cd '0-9A-Za-z._-' < "$SOURCE_ROOT/VERSION" 2>/dev/null || true)"
VERSION="${VERSION:-2027}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
RELEASE="$TP_RELEASES/${VERSION}-${STAMP}"
[[ ! -e "$RELEASE" ]] || fail "Release path already exists: $RELEASE"
install -d -m 755 "$RELEASE"

say "Staging new release"
rsync -a --delete \
  --exclude='.git/' \
  --exclude='.github/' \
  --exclude='.env' \
  --exclude='.env.*' \
  --exclude='node_modules/' \
  --exclude='.next/' \
  --exclude='backend/venv/' \
  --exclude='*.log' \
  "$SOURCE_ROOT/" "$RELEASE/"

python3 -m compileall -q "$RELEASE/backend/app" "$RELEASE/backend/create_admin.py"
find "$RELEASE/backend" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$RELEASE/backend" -type f -name '*.pyc' -delete 2>/dev/null || true

say "Installing backend dependencies"
python3 -m venv "$RELEASE/backend/venv"
"$RELEASE/backend/venv/bin/python" -m pip install --upgrade pip wheel
"$RELEASE/backend/venv/bin/pip" install -r "$RELEASE/backend/requirements.txt"

say "Building frontend"
cd "$RELEASE"
if [[ -f package-lock.json ]]; then npm ci; else npm install --no-audit --no-fund; fi
set -a
# shellcheck disable=SC1090
source "$TP_FRONTEND_ENV"
set +a
npm run build
chown -R www-data:www-data "$RELEASE/.next"

say "Checking database migration gate"
if [[ -f "$RELEASE/backend/alembic.ini" ]]; then
  (cd "$RELEASE/backend" && "$RELEASE/backend/venv/bin/alembic" -c alembic.ini upgrade head)
elif [[ "${TWINPANEL_ALLOW_EXISTING_SCHEMA:-0}" == "1" ]]; then
  warn "No Alembic baseline: existing schema explicitly accepted; no create_all bootstrap is run during update."
else
  fail "Alembic baseline موجود نیست؛ Update برای جلوگیری از Schema drift متوقف شد. DB backup: $DB_BACKUP"
fi

record_previous_release "$CURRENT"
atomic_activate "$RELEASE"

export TWINPANEL_DOMAIN TWINPANEL_WEB_PORT TWINPANEL_API_PORT
render "$RELEASE/deploy/systemd/twinpanel-api.service.tpl" /etc/systemd/system/twinpanel-api.service
render "$RELEASE/deploy/systemd/twinpanel-web.service.tpl" /etc/systemd/system/twinpanel-web.service
chmod 644 /etc/systemd/system/twinpanel-api.service /etc/systemd/system/twinpanel-web.service
systemctl daemon-reload
systemctl restart twinpanel-api.service twinpanel-web.service

if bash "$RELEASE/installer/healthcheck.sh"; then
  prune_releases 3
  echo "UPDATE_OK release=$RELEASE db_backup=$DB_BACKUP"
  exit 0
fi

warn "New release failed healthcheck; switching code back to $CURRENT"
atomic_activate "$CURRENT"
record_previous_release "$RELEASE"
systemctl daemon-reload
systemctl restart twinpanel-api.service twinpanel-web.service
systemctl reload nginx || true
bash "$CURRENT/installer/healthcheck.sh" || true
fail "UPDATE_FAILED_ROLLED_BACK_CODE. Database was not auto-restored. Backup: $DB_BACKUP"
