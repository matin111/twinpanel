#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="${TWINPANEL_SOURCE_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_root
[[ ! -e "$TP_CURRENT" && ! -f "$TP_INSTALL_ENV" ]] || fail "TwinPanel قبلاً نصب شده است؛ برای تغییر نسخه از installer/update.sh و برای تعمیر از installer/repair.sh استفاده کنید."
[[ -f "$SOURCE_ROOT/package.json" ]] || fail "package.json پیدا نشد: $SOURCE_ROOT"
[[ -f "$SOURCE_ROOT/backend/app/main.py" ]] || fail "backend/app هنوز وارد نشده است. ابتدا import سالم Backend سرور قدیمی را انجام دهید."

say "TwinPanel 2027 Installer"

read -r -p "Domain (example.com): " DOMAIN
DOMAIN="${DOMAIN,,}"
[[ "$DOMAIN" =~ ^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$ ]] || fail "دامنه نامعتبر است"

read -r -p "Frontend port [3000]: " WEB_PORT
WEB_PORT="${WEB_PORT:-3000}"
read -r -p "API port [8095]: " API_PORT
API_PORT="${API_PORT:-8095}"
is_port "$WEB_PORT" || fail "Frontend port نامعتبر است (1024-65535)"
is_port "$API_PORT" || fail "API port نامعتبر است (1024-65535)"
[[ "$WEB_PORT" != "$API_PORT" ]] || fail "پورت Frontend و API نباید یکسان باشند"

read -r -p "Admin display name / username: " ADMIN_NAME
[[ -n "${ADMIN_NAME// }" ]] || fail "Admin name خالی است"
read -r -p "Admin email: " ADMIN_EMAIL
[[ "$ADMIN_EMAIL" =~ ^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$ ]] || fail "Admin email نامعتبر است"

while :; do
  read -r -s -p "Admin password (min 12 chars): " ADMIN_PASSWORD; echo
  read -r -s -p "Confirm admin password: " ADMIN_PASSWORD_CONFIRM; echo
  [[ ${#ADMIN_PASSWORD} -ge 12 ]] || { warn "رمز باید حداقل ۱۲ کاراکتر باشد"; continue; }
  [[ "$ADMIN_PASSWORD" == "$ADMIN_PASSWORD_CONFIRM" ]] || { warn "رمزها یکسان نیستند"; continue; }
  break
done
unset ADMIN_PASSWORD_CONFIRM

read -r -p "License key: " LICENSE_KEY
[[ -n "${LICENSE_KEY// }" ]] || fail "License key خالی است"
read -r -p "Enable HTTPS with Let's Encrypt? [Y/n]: " SSL_REPLY
case "${SSL_REPLY:-Y}" in
  n|N|no|NO) WANT_SSL=0 ;;
  *) WANT_SSL=1 ;;
esac

say "Installing system dependencies"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl gnupg nginx postgresql postgresql-client redis-server \
  python3 python3-venv python3-pip rsync openssl certbot python3-certbot-nginx

if ! command -v node >/dev/null 2>&1 || ! node -e 'process.exit(Number(process.versions.node.split(".")[0])>=22?0:1)' >/dev/null 2>&1; then
  say "Installing Node.js 22"
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi
need node; need npm; need python3; need rsync; need psql; need nginx; need redis-cli; need runuser

python3 - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit("Python 3.12+ required")
PY
node -e 'if(Number(process.versions.node.split(".")[0])<22){throw new Error("Node.js 22+ required")}'

port_free "$WEB_PORT" || fail "پورت $WEB_PORT اشغال است"
port_free "$API_PORT" || fail "پورت $API_PORT اشغال است"

systemctl enable --now postgresql redis-server nginx

say "Creating protected configuration"
install -d -m 700 "$TP_ETC" "$TP_STATE" "$TP_RELEASES"
umask 077

APP_SECRET_KEY="$(openssl rand -hex 48)"
NODE_AGENT_SHARED_SECRET="$(openssl rand -hex 48)"
PAYMENT_SMS_RELAY_SECRET="$(openssl rand -hex 48)"
DB_PASSWORD="$(openssl rand -hex 32)"
INSTALLATION_ID="$(cat /proc/sys/kernel/random/uuid 2>/dev/null || python3 -c 'import uuid;print(uuid.uuid4())')"

write_kv(){ printf '%s=%q\n' "$1" "$2"; }
{
  write_kv TWINPANEL_DOMAIN "$DOMAIN"
  write_kv TWINPANEL_WEB_PORT "$WEB_PORT"
  write_kv TWINPANEL_API_PORT "$API_PORT"
  write_kv TWINPANEL_ADMIN_NAME "$ADMIN_NAME"
  write_kv TWINPANEL_ADMIN_EMAIL "$ADMIN_EMAIL"
  write_kv TWINPANEL_LICENSE_KEY "$LICENSE_KEY"
  write_kv TWINPANEL_INSTALLATION_ID "$INSTALLATION_ID"
  write_kv TWINPANEL_SSL_ENABLED "0"
} > "$TP_INSTALL_ENV"
chmod 600 "$TP_INSTALL_ENV"

say "Preparing PostgreSQL and Redis"
if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='twinpanel'" | grep -q 1; then
  runuser -u postgres -- psql -v ON_ERROR_STOP=1 -c "CREATE ROLE twinpanel LOGIN PASSWORD '$DB_PASSWORD';"
else
  runuser -u postgres -- psql -v ON_ERROR_STOP=1 -c "ALTER ROLE twinpanel WITH LOGIN PASSWORD '$DB_PASSWORD';"
fi
if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname='twinpanel'" | grep -q 1; then
  runuser -u postgres -- createdb -O twinpanel twinpanel
fi

DATABASE_URL="postgresql+psycopg2://twinpanel:${DB_PASSWORD}@127.0.0.1:5432/twinpanel"
{
  write_kv APP_NAME "TwinPanel"
  write_kv APP_ENV "production"
  write_kv APP_SECRET_KEY "$APP_SECRET_KEY"
  write_kv ACCESS_TOKEN_EXPIRE_MINUTES "10080"
  write_kv DATABASE_URL "$DATABASE_URL"
  write_kv REDIS_URL "redis://127.0.0.1:6379/0"
  write_kv NODE_AGENT_SHARED_SECRET "$NODE_AGENT_SHARED_SECRET"
  write_kv PAYMENT_SMS_RELAY_SECRET "$PAYMENT_SMS_RELAY_SECRET"
  write_kv TWINPANEL_LICENSE_KEY "$LICENSE_KEY"
  write_kv TWINPANEL_INSTALLATION_ID "$INSTALLATION_ID"
} > "$TP_BACKEND_ENV"
chmod 600 "$TP_BACKEND_ENV"

say "Staging release"
VERSION="$(tr -cd '0-9A-Za-z._-' < "$SOURCE_ROOT/VERSION" 2>/dev/null || true)"
VERSION="${VERSION:-2027}"
STAMP="$(date -u +%Y%m%d-%H%M%S)"
RELEASE="$TP_RELEASES/${VERSION}-${STAMP}"
install -d -m 755 "$RELEASE"
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

[[ -f "$RELEASE/backend/app/main.py" ]] || fail "Release فاقد backend/app/main.py است"
python3 -m compileall -q "$RELEASE/backend/app" "$RELEASE/backend/create_admin.py"
find "$RELEASE/backend" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$RELEASE/backend" -type f -name '*.pyc' -delete 2>/dev/null || true

say "Installing backend dependencies"
python3 -m venv "$RELEASE/backend/venv"
"$RELEASE/backend/venv/bin/python" -m pip install --upgrade pip wheel
"$RELEASE/backend/venv/bin/pip" install -r "$RELEASE/backend/requirements.txt"

say "Configuring Nginx"
export TWINPANEL_DOMAIN="$DOMAIN" TWINPANEL_WEB_PORT="$WEB_PORT" TWINPANEL_API_PORT="$API_PORT"
render "$RELEASE/deploy/nginx/twinpanel.conf.tpl" /etc/nginx/sites-available/twinpanel.conf
ln -sfn /etc/nginx/sites-available/twinpanel.conf /etc/nginx/sites-enabled/twinpanel.conf
nginx -t
systemctl reload nginx

SSL_ENABLED=0
PUBLIC_SCHEME="http"
if ((WANT_SSL)); then
  say "Requesting Let's Encrypt certificate"
  if certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email "$ADMIN_EMAIL" --redirect; then
    SSL_ENABLED=1
    PUBLIC_SCHEME="https"
    info "SSL_READY"
  else
    warn "صدور SSL ناموفق بود (DNS/Firewall را بررسی کنید)."
    if [[ -t 0 ]]; then
      read -r -p "Continue temporarily with HTTP? [y/N]: " FALLBACK
    else
      FALLBACK="${TWINPANEL_ALLOW_HTTP_FALLBACK:-N}"
    fi
    case "$FALLBACK" in y|Y|yes|YES) warn "نصب با HTTP ادامه پیدا می‌کند";; *) fail "SSL صادر نشد؛ نصب متوقف شد";; esac
  fi
fi
sed -i "s/^TWINPANEL_SSL_ENABLED=.*/TWINPANEL_SSL_ENABLED=$SSL_ENABLED/" "$TP_INSTALL_ENV"

PUBLIC_BASE="${PUBLIC_SCHEME}://${DOMAIN}"
{
  write_kv NEXT_PUBLIC_API_BASE "$PUBLIC_BASE"
  write_kv NEXT_PUBLIC_APP_NAME "TwinPanel"
} > "$TP_FRONTEND_ENV"
chmod 640 "$TP_FRONTEND_ENV"
chown root:www-data "$TP_FRONTEND_ENV"

say "Building TwinPanel web"
cd "$RELEASE"
if [[ -f package-lock.json ]]; then npm ci; else npm install --no-audit --no-fund; fi
set -a
# shellcheck disable=SC1090
source "$TP_FRONTEND_ENV"
set +a
npm run build
chown -R www-data:www-data "$RELEASE/.next"

say "Preparing database schema"
set -a
# shellcheck disable=SC1090
source "$TP_BACKEND_ENV"
set +a
TABLE_COUNT="$(runuser -u postgres -- psql -d twinpanel -tAc "SELECT count(*) FROM pg_tables WHERE schemaname='public'" | tr -d '[:space:]')"
TABLE_COUNT="${TABLE_COUNT:-0}"
if [[ -f "$RELEASE/backend/alembic.ini" ]]; then
  (cd "$RELEASE/backend" && "$RELEASE/backend/venv/bin/alembic" -c alembic.ini upgrade head)
elif ((TABLE_COUNT == 0)); then
  info "Fresh database detected; bootstrapping verified ORM schema"
  (cd "$RELEASE/backend" && "$RELEASE/backend/venv/bin/python" -c 'from app.main import app; print("SCHEMA_BOOTSTRAP_OK")')
elif [[ "${TWINPANEL_ALLOW_EXISTING_SCHEMA:-0}" == "1" ]]; then
  warn "Existing schema accepted explicitly without Alembic. No create_all bootstrap is executed."
else
  fail "DB دارای $TABLE_COUNT جدول است اما Alembic baseline موجود نیست. برای جلوگیری از تغییر حدسی Schema متوقف شد. پس از تأیید تطابق دقیق، فقط یک‌بار با TWINPANEL_ALLOW_EXISTING_SCHEMA=1 اجرا کنید."
fi

say "Creating administrator"
TWINPANEL_ADMIN_EMAIL="$ADMIN_EMAIL" \
TWINPANEL_ADMIN_NAME="$ADMIN_NAME" \
TWINPANEL_ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  "$RELEASE/backend/venv/bin/python" "$RELEASE/backend/create_admin.py"
unset ADMIN_PASSWORD

say "Activating release"
atomic_activate "$RELEASE"

render "$RELEASE/deploy/systemd/twinpanel-api.service.tpl" /etc/systemd/system/twinpanel-api.service
render "$RELEASE/deploy/systemd/twinpanel-web.service.tpl" /etc/systemd/system/twinpanel-web.service
chmod 644 /etc/systemd/system/twinpanel-api.service /etc/systemd/system/twinpanel-web.service
systemctl daemon-reload
systemctl enable twinpanel-api.service twinpanel-web.service
systemctl restart twinpanel-api.service
systemctl restart twinpanel-web.service
systemctl reload nginx

if ! bash "$RELEASE/installer/healthcheck.sh"; then
  fail "Healthcheck ناموفق بود؛ journalctl -u twinpanel-api -u twinpanel-web را بررسی کنید"
fi

prune_releases 2

say "TwinPanel installed"
printf 'Panel: %s\nAPI health: %s/health\nRelease: %s\nInstallation ID: %s\n' "$PUBLIC_BASE" "$PUBLIC_BASE" "$RELEASE" "$INSTALLATION_ID"
if ((SSL_ENABLED==0)); then warn "HTTPS هنوز فعال نیست. بعد از اصلاح DNS، installer/repair.sh را اجرا کنید."; fi
