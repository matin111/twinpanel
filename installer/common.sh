#!/usr/bin/env bash
set -Eeuo pipefail

TP_ROOT="${TP_ROOT:-/opt/twinpanel}"
TP_ETC="${TP_ETC:-/etc/twinpanel}"
TP_STATE="${TP_STATE:-/var/lib/twinpanel}"
TP_CURRENT="$TP_ROOT/current"
TP_RELEASES="$TP_ROOT/releases"
TP_INSTALL_ENV="$TP_ETC/install.env"
TP_BACKEND_ENV="$TP_ETC/twinpanel.env"
TP_FRONTEND_ENV="$TP_ETC/frontend.env"

say(){ printf '\n\033[1;35m%s\033[0m\n' "$*"; }
info(){ printf '\033[1;36m%s\033[0m\n' "$*"; }
warn(){ printf '\033[1;33mWARN: %s\033[0m\n' "$*" >&2; }
fail(){ printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }
require_root(){ [[ ${EUID:-$(id -u)} -eq 0 ]] || fail "این دستور باید با root اجرا شود"; }
need(){ command -v "$1" >/dev/null 2>&1 || fail "دستور لازم پیدا نشد: $1"; }

is_port(){ [[ "$1" =~ ^[0-9]+$ ]] && ((10#$1 >= 1024 && 10#$1 <= 65535)); }
port_free(){ ! ss -lnt "sport = :$1" 2>/dev/null | tail -n +2 | grep -q .; }

load_install_env(){
  [[ -f "$TP_INSTALL_ENV" ]] || fail "فایل تنظیمات نصب پیدا نشد: $TP_INSTALL_ENV"
  set -a
  # shellcheck disable=SC1090
  source "$TP_INSTALL_ENV"
  set +a
}

load_backend_env(){
  [[ -f "$TP_BACKEND_ENV" ]] || fail "فایل محیط Backend پیدا نشد: $TP_BACKEND_ENV"
  set -a
  # shellcheck disable=SC1090
  source "$TP_BACKEND_ENV"
  set +a
}

render(){
  local src="$1" dst="$2"
  sed \
    -e "s|__DOMAIN__|${TWINPANEL_DOMAIN}|g" \
    -e "s|__WEB_PORT__|${TWINPANEL_WEB_PORT}|g" \
    -e "s|__API_PORT__|${TWINPANEL_API_PORT}|g" \
    "$src" > "$dst"
}

current_release(){ readlink -f "$TP_CURRENT" 2>/dev/null || true; }
record_previous_release(){
  local value="$1"
  install -d -m 700 "$TP_STATE"
  printf '%s\n' "$value" > "$TP_STATE/previous_release"
  chmod 600 "$TP_STATE/previous_release"
}
previous_release(){ [[ -f "$TP_STATE/previous_release" ]] && cat "$TP_STATE/previous_release" || true; }

atomic_activate(){
  local release="$1"
  ln -sfn "$release" "$TP_ROOT/.current.new"
  mv -Tf "$TP_ROOT/.current.new" "$TP_CURRENT"
}

wait_http(){
  local url="$1" attempts="${2:-30}" delay="${3:-1}"
  local i
  for ((i=1;i<=attempts;i++)); do
    if curl -fsS --max-time 4 "$url" >/dev/null 2>&1; then return 0; fi
    sleep "$delay"
  done
  return 1
}

prune_releases(){
  local keep="${1:-3}" current previous
  current="$(current_release)"
  previous="$(previous_release)"
  [[ -d "$TP_RELEASES" ]] || return 0
  mapfile -t releases < <(find "$TP_RELEASES" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' | sort -nr | awk '{print $2}')
  local count=0 item
  for item in "${releases[@]}"; do
    [[ "$item" == "$current" || "$item" == "$previous" ]] && continue
    ((count+=1))
    if ((count > keep)); then rm -rf --one-file-system "$item"; fi
  done
}
