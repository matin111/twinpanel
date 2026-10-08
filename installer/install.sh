#!/usr/bin/env bash
set -Eeuo pipefail

say(){ printf '\n\033[1;35m%s\033[0m\n' "$*"; }
fail(){ echo "ERROR: $*" >&2; exit 1; }
free(){ ! ss -lnt "sport = :$1" 2>/dev/null | tail -n +2 | grep -q .; }

[[ $EUID -eq 0 ]] || fail "Installer باید با root اجرا شود"
command -v ss >/dev/null || fail "ss نصب نیست"
command -v ip >/dev/null || fail "iproute2 نصب نیست"

say "TwinPanel 2027 Installer"
echo "دامنه در زمان نصب اجباری نیست. بعد از ورود از بخش «دامنه و SSL» مدیریت می‌شود."

# Public IPv4 is detected automatically from the server itself.
# The installer must never contain a hard-coded deployment IP.
PUBLIC_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"

if [[ -z "$PUBLIC_IP" ]]; then
  PUBLIC_IP="$(hostname -I 2>/dev/null | tr ' ' '\n' | awk '/^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$/ {print; exit}')"
fi

[[ "$PUBLIC_IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || fail "IPv4 عمومی سرور تشخیص داده نشد"

echo "Server public IP detected: $PUBLIC_IP"
echo "تا قبل از ثبت API Domain، API عمومی از همین IP استفاده می‌کند."

read -r -p "Frontend port [3000]: " WEB
WEB=${WEB:-3000}
read -r -p "API port [8095]: " API
API=${API:-8095}

[[ "$WEB" =~ ^[0-9]+$ && "$API" =~ ^[0-9]+$ ]] || fail "پورت نامعتبر"
[[ "$WEB" != "$API" ]] || fail "پورت Frontend و API نباید یکسان باشند"
free "$WEB" || fail "پورت $WEB اشغال است"
free "$API" || fail "پورت $API اشغال است"

read -r -p "Admin username: " ADMIN
read -r -p "Admin email: " EMAIL
[[ -n "$ADMIN" && -n "$EMAIL" ]] || fail "اطلاعات ادمین ناقص است"

while :; do
  read -r -s -p "Admin password: " PASS; echo
  read -r -s -p "Confirm password: " PASS2; echo
  [[ -n "$PASS" && "$PASS" == "$PASS2" ]] && break
  echo "رمزها یکسان نیستند"
done

read -r -p "License key: " LICENSE

install -d -m 700 /etc/twinpanel
umask 077
cat >/etc/twinpanel/install.env <<ENV
TWINPANEL_WEB_PORT=$WEB
TWINPANEL_API_PORT=$API
TWINPANEL_BACKEND_URL=http://127.0.0.1:$API
TWINPANEL_PUBLIC_IP=$PUBLIC_IP
PUBLIC_API_FALLBACK=http://$PUBLIC_IP
TWINPANEL_ADMIN_USER=$ADMIN
TWINPANEL_ADMIN_EMAIL=$EMAIL
TWINPANEL_LICENSE_KEY=$LICENSE
ENV
chmod 600 /etc/twinpanel/install.env

unset PASS PASS2

say "Configuration saved"
printf 'Frontend internal: 127.0.0.1:%s\nAPI internal: 127.0.0.1:%s\n' "$WEB" "$API"
printf 'Initial public API: http://%s\n' "$PUBLIC_IP"
echo "وقتی ادمین Domain با نقش API ثبت کند، Public API به همان دامنه منتقل می‌شود."
echo "پس از فعال شدن SSL، آدرس API خودکار HTTPS خواهد شد."
echo "پس از ورود: تنظیمات → دامنه و SSL"
echo "از همان بخش نقش‌های Panel / Store / API / Subscription را اضافه و SSL را صادر کنید."
echo "Admin password is not persisted. Backend bootstrap will consume it after backend migration."
