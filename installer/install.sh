#!/usr/bin/env bash
set -Eeuo pipefail

say(){ printf '\n\033[1;35m%s\033[0m\n' "$*"; }
fail(){ echo "ERROR: $*" >&2; exit 1; }
free(){ ! ss -lnt "sport = :$1" 2>/dev/null | tail -n +2 | grep -q .; }

[[ $EUID -eq 0 ]] || fail "Installer باید با root اجرا شود"
command -v ss >/dev/null || fail "ss نصب نیست"
command -v ip >/dev/null || fail "iproute2 نصب نیست"

say "TwinPanel Installer"
echo "دامنه در زمان نصب اجباری نیست. بعد از ورود از بخش دامنه و SSL مدیریت می‌شود."

PUBLIC_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"
if [[ -z "$PUBLIC_IP" ]]; then
  PUBLIC_IP="$(hostname -I 2>/dev/null | tr ' ' '\n' | awk '/^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/ {print; exit}')"
fi
[[ "$PUBLIC_IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || fail "IPv4 عمومی سرور تشخیص داده نشد"

echo "Server public IP: $PUBLIC_IP"

read -r -p "Frontend port [3000]: " WEB
WEB=${WEB:-3000}
read -r -p "API port [8095]: " API
API=${API:-8095}

[[ "$WEB" =~ ^[0-9]+$ && "$API" =~ ^[0-9]+$ ]] || fail "پورت نامعتبر"
[[ "$WEB" != "$API" ]] || fail "پورت Frontend و API نباید یکسان باشند"
free "$WEB" || fail "پورت $WEB اشغال است"
free "$API" || fail "پورت $API اشغال است"

printf '\n===== Admin account =====\n'
while :; do
  read -r -p "Admin email: " EMAIL
  [[ -n "$EMAIL" ]] && break
  echo "ایمیل نمی‌تواند خالی باشد"
done

while :; do
  read -r -s -p "Admin password (typing is hidden): " PASS
  echo
  [[ ${#PASS} -ge 10 ]] || { echo "رمز باید حداقل 10 کاراکتر باشد"; continue; }

  read -r -s -p "Confirm password: " PASS2
  echo
  [[ "$PASS" == "$PASS2" ]] && break
  echo "رمزها یکسان نیستند"
done

read -r -p "License key [leave empty for trial]: " LICENSE

install -d -m 700 /etc/twinpanel
umask 077
cat >/etc/twinpanel/install.env <<ENV
TWINPANEL_WEB_PORT=$WEB
TWINPANEL_API_PORT=$API
TWINPANEL_BACKEND_URL=http://127.0.0.1:$API
TWINPANEL_PUBLIC_IP=$PUBLIC_IP
PUBLIC_API_FALLBACK=http://$PUBLIC_IP
TWINPANEL_ADMIN_EMAIL=$EMAIL
TWINPANEL_LICENSE_KEY=$LICENSE
ENV
chmod 600 /etc/twinpanel/install.env

# When the backend runtime already exists (upgrade/reinstall/current development
# server), create or update the admin immediately. The password is never written
# to install.env and is removed from the shell environment after bootstrap.
BACKEND_DIR="/opt/twinpanel/current/backend"
PYTHON_BIN="/opt/twinpanel/venv/bin/python"
BOOTSTRAP="$BACKEND_DIR/scripts/bootstrap_admin.py"

if [[ -x "$PYTHON_BIN" && -f "$BOOTSTRAP" && -f /etc/twinpanel/backend.env ]]; then
  say "Creating admin account"
  set -a
  # shellcheck disable=SC1091
  source /etc/twinpanel/backend.env
  set +a

  export TWINPANEL_ADMIN_EMAIL="$EMAIL"
  export TWINPANEL_ADMIN_PASSWORD="$PASS"
  export TWINPANEL_ADMIN_NAME="Administrator"

  (cd "$BACKEND_DIR" && "$PYTHON_BIN" scripts/bootstrap_admin.py)

  unset TWINPANEL_ADMIN_PASSWORD TWINPANEL_ADMIN_EMAIL TWINPANEL_ADMIN_NAME
else
  echo "Backend runtime is not installed yet; admin bootstrap will run after backend installation."
fi

unset PASS PASS2

say "Configuration saved"
printf 'Frontend internal: 127.0.0.1:%s\nAPI internal: 127.0.0.1:%s\n' "$WEB" "$API"
printf 'Initial public API: http://%s\n' "$PUBLIC_IP"
echo "Admin email: $EMAIL"
echo "Admin password was not stored on disk."
