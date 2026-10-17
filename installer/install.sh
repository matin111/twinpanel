#!/usr/bin/env bash
set -Eeuo pipefail

say(){ printf '\n\033[1;35m%s\033[0m\n' "$*"; }
info(){ printf '\033[1;34m%s\033[0m\n' "$*"; }
fail(){ echo "ERROR: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || fail "Installer must run as root / نصب باید با root اجرا شود"

OFFICIAL=0
for arg in "$@"; do
  case "$arg" in
    --official) OFFICIAL=1 ;;
  esac
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "$SOURCE_ROOT/VERSION" 2>/dev/null || true)"
[[ -n "$VERSION" ]] || fail "VERSION file is missing"

WEB_PORT="${TWINPANEL_WEB_PORT:-3000}"
API_PORT="${TWINPANEL_API_PORT:-8095}"
LICENSE_API_URL="${TWINPANEL_LICENSE_API_URL:-}"

if [[ -f /etc/twinpanel/install.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source /etc/twinpanel/install.env
  set +a
  WEB_PORT="${TWINPANEL_WEB_PORT:-$WEB_PORT}"
  API_PORT="${TWINPANEL_API_PORT:-$API_PORT}"
  LICENSE_API_URL="${TWINPANEL_LICENSE_API_URL:-$LICENSE_API_URL}"
fi

[[ "$WEB_PORT" =~ ^[0-9]+$ ]] || fail "Invalid web port"
[[ "$API_PORT" =~ ^[0-9]+$ ]] || fail "Invalid API port"
[[ "$WEB_PORT" != "$API_PORT" ]] || fail "Web and API ports must differ"

if (( OFFICIAL )); then
  [[ -n "$LICENSE_API_URL" ]] || fail "Official bootstrap did not configure TWINPANEL_LICENSE_API_URL"
  [[ -s /var/lib/twinpanel-license/state.json ]] || fail "Official bootstrap license/trial state is missing"
  [[ -s /etc/twinpanel/installation-id ]] || fail "Installation ID is missing"
fi

say "TwinPanel $VERSION — Self-hosted installer"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y \
  ca-certificates curl gnupg jq openssl rsync \
  nginx postgresql postgresql-contrib redis-server \
  python3 python3-venv python3-pip build-essential

NODE_MAJOR=0
if command -v node >/dev/null 2>&1; then
  NODE_MAJOR="$(node -p 'Number(process.versions.node.split(".")[0])' 2>/dev/null || echo 0)"
fi
if (( NODE_MAJOR < 22 )); then
  say "Installing Node.js 22"
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y nodejs
fi

systemctl enable --now postgresql redis-server nginx

PUBLIC_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++)if($i=="src"){print $(i+1);exit}}')"
if [[ -z "$PUBLIC_IP" ]]; then
  PUBLIC_IP="$(hostname -I 2>/dev/null | tr ' ' '\n' | awk '/^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/ {print;exit}')"
fi
[[ "$PUBLIC_IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || fail "Could not detect public IPv4"

say "Preparing release layout"
install -d -m 755 /opt/twinpanel/releases
TARGET_RELEASE="/opt/twinpanel/releases/$VERSION"
SOURCE_REAL="$(readlink -f "$SOURCE_ROOT")"
TARGET_REAL="$(readlink -f "$TARGET_RELEASE" 2>/dev/null || true)"

if [[ "$SOURCE_REAL" != "$TARGET_REAL" ]]; then
  rm -rf "$TARGET_RELEASE"
  install -d -m 755 "$TARGET_RELEASE"
  rsync -a --delete --exclude='.git' --exclude='.env' --exclude='.env.local' "$SOURCE_ROOT/" "$TARGET_RELEASE/"
fi

if [[ -e /opt/twinpanel/current && ! -L /opt/twinpanel/current ]]; then
  LEGACY="/opt/twinpanel/releases/legacy-$(date +%Y%m%d-%H%M%S)"
  mv /opt/twinpanel/current "$LEGACY"
  info "Previous non-symlink current moved to $LEGACY"
fi
ln -sfn "$TARGET_RELEASE" /opt/twinpanel/current
RELEASE_ROOT="/opt/twinpanel/current"

say "Creating runtime directories"
install -d -m 700 /etc/twinpanel /var/lib/twinpanel-backups /var/lib/twinpanel-license
install -d -m 755 /opt/twinpanel/runtime

if [[ ! -s /etc/twinpanel/installation-id ]]; then
  python3 - <<'PY'
from pathlib import Path
import os, uuid
path=Path('/etc/twinpanel/installation-id')
path.write_text(str(uuid.uuid4())+'\n',encoding='utf-8')
os.chmod(path,0o600)
PY
fi

say "Configuring PostgreSQL"
if [[ -f /etc/twinpanel/backend.env ]]; then
  DB_URL="$(grep -E '^DATABASE_URL=' /etc/twinpanel/backend.env | tail -1 | cut -d= -f2- || true)"
else
  DB_PASS="$(openssl rand -hex 24)"
  APP_SECRET="$(openssl rand -hex 48)"
  NODE_SECRET="$(openssl rand -hex 48)"
  DB_URL="postgresql+psycopg2://twinpanel:${DB_PASS}@127.0.0.1:5432/twinpanel"

  if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='twinpanel'" | grep -q 1; then
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c "ALTER ROLE twinpanel WITH LOGIN PASSWORD '${DB_PASS}';"
  else
    sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE ROLE twinpanel WITH LOGIN PASSWORD '${DB_PASS}';"
  fi
  if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='twinpanel'" | grep -q 1; then
    sudo -u postgres createdb -O twinpanel twinpanel
  fi

  cat >/etc/twinpanel/backend.env <<ENV
APP_NAME=TwinPanel
APP_ENV=production
APP_SECRET_KEY=$APP_SECRET
ACCESS_TOKEN_EXPIRE_MINUTES=10080
DATABASE_URL=$DB_URL
REDIS_URL=redis://127.0.0.1:6379/0
NODE_AGENT_SHARED_SECRET=$NODE_SECRET
PUBLIC_API_FALLBACK=http://$PUBLIC_IP
TWINPANEL_RELEASE_CHANNEL=stable
TWINPANEL_RELEASE_MANIFEST_URL=https://raw.githubusercontent.com/matin111/tp27-core/main/twinpanel/releases/stable.json
TWINPANEL_LICENSE_API_URL=$LICENSE_API_URL
TWINPANEL_LICENSE_PUBLIC_KEY_FILE=/etc/twinpanel/license-public.pem
TWINPANEL_LICENSE_ENFORCE=$([[ -n "$LICENSE_API_URL" ]] && echo 1 || echo 0)
TWINPANEL_LICENSE_OFFLINE_GRACE_SECONDS=172800
TWINPANEL_VERSION_FILE=/opt/twinpanel/current/VERSION
ENV
  chmod 600 /etc/twinpanel/backend.env
fi

# Ensure a pre-existing backend.env receives release/license variables without
# overwriting application/database secrets.
python3 - <<PY
from pathlib import Path
path=Path('/etc/twinpanel/backend.env')
text=path.read_text(encoding='utf-8') if path.exists() else ''
updates={
'TWINPANEL_RELEASE_CHANNEL':'stable',
'TWINPANEL_RELEASE_MANIFEST_URL':'https://raw.githubusercontent.com/matin111/tp27-core/main/twinpanel/releases/stable.json',
'TWINPANEL_LICENSE_API_URL':'''$LICENSE_API_URL''',
'TWINPANEL_LICENSE_PUBLIC_KEY_FILE':'/etc/twinpanel/license-public.pem',
'TWINPANEL_LICENSE_ENFORCE':'1' if '''$LICENSE_API_URL''' else '0',
'TWINPANEL_LICENSE_OFFLINE_GRACE_SECONDS':'172800',
'TWINPANEL_VERSION_FILE':'/opt/twinpanel/current/VERSION',
}
lines=text.splitlines()
seen=set()
out=[]
for line in lines:
    if '=' in line and not line.lstrip().startswith('#'):
        key=line.split('=',1)[0].strip()
        if key in updates:
            out.append(f'{key}={updates[key]}'); seen.add(key); continue
    out.append(line)
for key,value in updates.items():
    if key not in seen: out.append(f'{key}={value}')
path.write_text('\n'.join(out).rstrip()+'\n',encoding='utf-8')
PY
chmod 600 /etc/twinpanel/backend.env

cat >/etc/twinpanel/frontend.env <<ENV
NODE_ENV=production
TWINPANEL_BACKEND_URL=http://127.0.0.1:$API_PORT
NEXT_PUBLIC_API_BASE=
ENV
chmod 640 /etc/twinpanel/frontend.env
chown root:www-data /etc/twinpanel/frontend.env

cat >"$RELEASE_ROOT/.env.local" <<ENV
TWINPANEL_BACKEND_URL=http://127.0.0.1:$API_PORT
NEXT_PUBLIC_API_BASE=
ENV
chmod 640 "$RELEASE_ROOT/.env.local"

say "Installing Backend"
if [[ ! -x /opt/twinpanel/venv/bin/python3 ]]; then
  python3 -m venv /opt/twinpanel/venv
fi
/opt/twinpanel/venv/bin/python3 -m pip install --upgrade pip
/opt/twinpanel/venv/bin/python3 -m pip install -r "$RELEASE_ROOT/backend/requirements.txt"

set -a
# shellcheck disable=SC1091
source /etc/twinpanel/backend.env
set +a
(
  cd "$RELEASE_ROOT/backend"
  /opt/twinpanel/venv/bin/python3 -m compileall -q app scripts
  /opt/twinpanel/venv/bin/python3 -c 'from app.main import app; print("API_SCHEMA_OK", app.title)'
)

say "Building Frontend"
cd "$RELEASE_ROOT"
if [[ -f package-lock.json ]]; then
  npm ci --include=optional
else
  npm install --no-audit --no-fund
fi
npm run build
chown -R www-data:www-data "$TARGET_RELEASE/.next" "$TARGET_RELEASE/node_modules" 2>/dev/null || true

say "Creating initial administrator"
ADMIN_EMAIL="admin@twinpanel.app"
ADMIN_NAME="Administrator"
ADMIN_PASS="$(python3 - <<'PY'
import secrets
import string
alphabet=string.ascii_letters+string.digits+'-_.@'
print(''.join(secrets.choice(alphabet) for _ in range(20)))
PY
)"
export TWINPANEL_ADMIN_EMAIL="$ADMIN_EMAIL"
export TWINPANEL_ADMIN_PASSWORD="$ADMIN_PASS"
export TWINPANEL_ADMIN_NAME="$ADMIN_NAME"
ADMIN_RESULT="$((
  cd "$RELEASE_ROOT/backend"
  /opt/twinpanel/venv/bin/python3 scripts/bootstrap_admin.py
) 2>&1)"
printf '%s\n' "$ADMIN_RESULT"
ADMIN_CREATED=0
if grep -q 'action=created' <<<"$ADMIN_RESULT"; then
  ADMIN_CREATED=1
  cat >/root/twinpanel-initial-admin.txt <<ENV
TwinPanel initial admin — first login only
Email: $ADMIN_EMAIL
Password: $ADMIN_PASS
Panel: http://$PUBLIC_IP
Version: $VERSION

Change the email/password after first login, then delete this file.
ENV
  chmod 600 /root/twinpanel-initial-admin.txt
fi
unset TWINPANEL_ADMIN_PASSWORD TWINPANEL_ADMIN_EMAIL TWINPANEL_ADMIN_NAME

say "Installing SSH management menu"
cat >/usr/local/bin/twinpanel <<'SH'
#!/usr/bin/env bash
exec bash /opt/twinpanel/current/scripts/twinpanel-menu.sh "$@"
SH
chmod 755 /usr/local/bin/twinpanel
ln -sfn /usr/local/bin/twinpanel /usr/local/bin/tp

say "Installing systemd units"
sed "s/__API_PORT__/$API_PORT/g" "$RELEASE_ROOT/deploy/systemd/twinpanel-api.service.tpl" >/etc/systemd/system/twinpanel-api.service
sed "s/__WEB_PORT__/$WEB_PORT/g" "$RELEASE_ROOT/deploy/systemd/twinpanel-web.service.tpl" >/etc/systemd/system/twinpanel-web.service
install -m 644 "$RELEASE_ROOT/deploy/systemd/twinpanel-updater.service.tpl" /etc/systemd/system/twinpanel-updater.service

if [[ -f "$RELEASE_ROOT/deploy/systemd/twinpanel-reseller-bots.service.tpl" ]]; then
  install -m 644 "$RELEASE_ROOT/deploy/systemd/twinpanel-reseller-bots.service.tpl" /etc/systemd/system/twinpanel-reseller-bots.service
fi
if [[ -f "$RELEASE_ROOT/deploy/systemd/twinpanel-backup.service" ]]; then
  install -m 644 "$RELEASE_ROOT/deploy/systemd/twinpanel-backup.service" /etc/systemd/system/twinpanel-backup.service
fi
if [[ -f "$RELEASE_ROOT/deploy/systemd/twinpanel-backup.timer" ]]; then
  install -m 644 "$RELEASE_ROOT/deploy/systemd/twinpanel-backup.timer" /etc/systemd/system/twinpanel-backup.timer
fi

say "Configuring automatic backup defaults"
if [[ ! -f /var/lib/twinpanel-backups/settings.json ]]; then
  cat >/var/lib/twinpanel-backups/settings.json <<'JSON'
{
  "enabled": true,
  "frequency": "daily",
  "hour": 3,
  "minute": 0,
  "weekday": 0,
  "timezone": "Asia/Tehran",
  "send_telegram": false,
  "telegram_chat_id": "",
  "retention": 14
}
JSON
  chmod 600 /var/lib/twinpanel-backups/settings.json
fi

say "Configuring Nginx"
rm -f /etc/nginx/sites-enabled/default
sed -e "s/__DOMAIN__/$PUBLIC_IP/g" -e "s/__API_PORT__/$API_PORT/g" -e "s/__WEB_PORT__/$WEB_PORT/g" \
  "$RELEASE_ROOT/deploy/nginx/twinpanel.conf.tpl" >/etc/nginx/sites-available/twinpanel
ln -sfn /etc/nginx/sites-available/twinpanel /etc/nginx/sites-enabled/twinpanel
nginx -t

systemctl daemon-reload
systemctl enable --now twinpanel-api.service twinpanel-web.service
if systemctl cat twinpanel-backup.timer >/dev/null 2>&1; then
  systemctl enable --now twinpanel-backup.timer
fi
if systemctl cat twinpanel-reseller-bots.service >/dev/null 2>&1; then
  systemctl enable twinpanel-reseller-bots.service >/dev/null 2>&1 || true
fi
systemctl restart nginx

say "Health checks"
for i in $(seq 1 60); do
  if curl -fsS --max-time 3 "http://127.0.0.1:$API_PORT/health/ready" >/dev/null 2>&1; then break; fi
  [[ "$i" == 60 ]] && { journalctl -u twinpanel-api.service -n 100 --no-pager; fail "API health failed"; }
  sleep 2
done
for i in $(seq 1 60); do
  if curl -fsS --max-time 3 "http://127.0.0.1:$WEB_PORT/health" >/dev/null 2>&1; then break; fi
  [[ "$i" == 60 ]] && { journalctl -u twinpanel-web.service -n 100 --no-pager; fail "Web health failed"; }
  sleep 2
done
curl -fsS --max-time 5 http://127.0.0.1/health >/dev/null || fail "Nginx/API public health failed"

say "TwinPanel installation complete"
echo "Version: $VERSION"
echo "Panel: http://$PUBLIC_IP"
echo "SSH management: twinpanel  (or: tp)"
if (( ADMIN_CREATED )); then
  echo "Admin email: $ADMIN_EMAIL"
  echo "Admin password: $ADMIN_PASS"
  echo "Credentials file: /root/twinpanel-initial-admin.txt"
  echo "This account is for first login only. Change the admin email/password after login and delete the credentials file."
else
  echo "Existing administrator preserved; no admin credentials were changed."
fi
echo "نسخه: $VERSION"
echo "آدرس پنل: http://$PUBLIC_IP"
echo "منوی مدیریت SSH: twinpanel"
if (( ADMIN_CREATED )); then
  echo "این اطلاعات فقط برای ورود اولیه است؛ بعد از ورود ایمیل و رمز مدیر را تغییر دهید."
else
  echo "ادمین قبلی بدون تغییر حفظ شد."
fi
