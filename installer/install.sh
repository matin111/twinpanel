#!/usr/bin/env bash
set -Eeuo pipefail

say(){ printf '\n\033[1;35m%s\033[0m\n' "$*"; }
fail(){ echo "ERROR: $*" >&2; exit 1; }
free(){ ! ss -lnt "sport = :$1" 2>/dev/null | tail -n +2 | grep -q .; }

[[ $EUID -eq 0 ]] || fail "Installer باید با root اجرا شود"
command -v ss >/dev/null || fail "ss نصب نیست"
command -v ip >/dev/null || fail "iproute2 نصب نیست"
command -v openssl >/dev/null || fail "openssl نصب نیست"

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

# No admin questions during installation. A unique 12-digit numeric password is
# generated per installation. The customer changes email/password after login.
ADMIN_EMAIL="admin@twinpanel.app"
ADMIN_NAME="Administrator"
RANDOM_HEX="$(openssl rand -hex 6)"
ADMIN_PASS="$(printf '%012d' "$((16#$RANDOM_HEX % 1000000000000))")"

read -r -p "License key [leave empty for trial]: " LICENSE

install -d -m 700 /etc/twinpanel
umask 077

cat >/etc/twinpanel/install.env <<ENV
TWINPANEL_WEB_PORT=$WEB
TWINPANEL_API_PORT=$API
TWINPANEL_BACKEND_URL=http://127.0.0.1:$API
TWINPANEL_PUBLIC_IP=$PUBLIC_IP
PUBLIC_API_FALLBACK=http://$PUBLIC_IP
TWINPANEL_ADMIN_EMAIL=$ADMIN_EMAIL
TWINPANEL_LICENSE_KEY=$LICENSE
ENV
chmod 600 /etc/twinpanel/install.env

# Temporary bootstrap secret for the backend installation stage. This file is
# deleted immediately after a successful admin bootstrap.
cat >/etc/twinpanel/bootstrap-admin.env <<ENV
TWINPANEL_ADMIN_EMAIL=$ADMIN_EMAIL
TWINPANEL_ADMIN_PASSWORD=$ADMIN_PASS
TWINPANEL_ADMIN_NAME=$ADMIN_NAME
ENV
chmod 600 /etc/twinpanel/bootstrap-admin.env

# Keep a root-only copy so credentials can be recovered if the SSH session is
# lost before the first login. The user should remove it after changing admin
# credentials from the panel.
cat >/root/twinpanel-initial-admin.txt <<ENV
TwinPanel initial admin
Email: $ADMIN_EMAIL
Password: $ADMIN_PASS
ENV
chmod 600 /root/twinpanel-initial-admin.txt

BACKEND_DIR="/opt/twinpanel/current/backend"
PYTHON_BIN="/opt/twinpanel/venv/bin/python"
BOOTSTRAP="$BACKEND_DIR/scripts/bootstrap_admin.py"

if [[ -x "$PYTHON_BIN" && -f "$BOOTSTRAP" && -f /etc/twinpanel/backend.env ]]; then
  say "Creating default admin"
  set -a
  # shellcheck disable=SC1091
  source /etc/twinpanel/backend.env
  # shellcheck disable=SC1091
  source /etc/twinpanel/bootstrap-admin.env
  set +a

  (cd "$BACKEND_DIR" && "$PYTHON_BIN" scripts/bootstrap_admin.py)
  rm -f /etc/twinpanel/bootstrap-admin.env

  unset TWINPANEL_ADMIN_PASSWORD TWINPANEL_ADMIN_EMAIL TWINPANEL_ADMIN_NAME
else
  echo "Backend runtime is not installed yet; default admin will be created after backend installation."
fi

say "Configuration saved"
printf 'Frontend internal: 127.0.0.1:%s\nAPI internal: 127.0.0.1:%s\n' "$WEB" "$API"
printf 'Initial public API: http://%s\n' "$PUBLIC_IP"
echo
echo "===== Initial Admin ====="
echo "Email: $ADMIN_EMAIL"
echo "Password: $ADMIN_PASS"
echo "Saved in: /root/twinpanel-initial-admin.txt"
echo "After first login, change email/password from the panel and delete that file."

unset ADMIN_PASS RANDOM_HEX
