#!/usr/bin/env bash
set -Eeuo pipefail

PRODUCT="TwinPanel"
DEFAULT_MANIFEST_URL="https://raw.githubusercontent.com/matin111/twinpanel/main/releases/stable.json"
MANIFEST_URL="${TWINPANEL_RELEASE_MANIFEST_URL:-$DEFAULT_MANIFEST_URL}"
WORKDIR=""
EXISTING_INSTALL=0
PROTOCOL_SETUP_STATUS="skipped"
[[ -f /etc/twinpanel/backend.env ]] && EXISTING_INSTALL=1

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
  C_PURPLE='\033[1;35m'
  C_BLUE='\033[1;36m'
  C_GREEN='\033[1;32m'
  C_YELLOW='\033[1;33m'
  C_DIM='\033[2m'
  C_RESET='\033[0m'
else
  C_PURPLE=''
  C_BLUE=''
  C_GREEN=''
  C_YELLOW=''
  C_DIM=''
  C_RESET=''
fi

say(){ printf '\n%b%s%b\n' "$C_PURPLE" "$*" "$C_RESET"; }
info(){ printf '%b%s%b\n' "$C_BLUE" "$*" "$C_RESET"; }
warn(){ printf '%bWARNING: %s%b\n' "$C_YELLOW" "$*" "$C_RESET" >&2; }
fail(){ printf '\nERROR: %s\n' "$*" >&2; exit 1; }
cleanup(){ [[ -n "${WORKDIR:-}" && -d "$WORKDIR" ]] && rm -rf "$WORKDIR" || true; }
trap cleanup EXIT

brand_splash(){
  [[ -t 1 ]] && clear 2>/dev/null || true
  printf '%b' "$C_PURPLE"
  cat <<'BANNER'

  ████████╗██╗    ██╗██╗███╗   ██╗██████╗  █████╗ ███╗   ██╗███████╗██╗
  ╚══██╔══╝██║    ██║██║████╗  ██║██╔══██╗██╔══██╗████╗  ██║██╔════╝██║
     ██║   ██║ █╗ ██║██║██╔██╗ ██║██████╔╝███████║██╔██╗ ██║█████╗  ██║
     ██║   ██║███╗██║██║██║╚██╗██║██╔═══╝ ██╔══██║██║╚██╗██║██╔══╝  ██║
     ██║   ╚███╔███╔╝██║██║ ╚████║██║     ██║  ██║██║ ╚████║███████╗███████╗
     ╚═╝    ╚══╝╚══╝ ╚═╝╚═╝  ╚═══╝╚═╝     ╚═╝  ╚═╝╚═╝  ╚═══╝╚══════╝╚══════╝
BANNER
  printf '%b' "$C_RESET"
  printf '\n  %bSelf-Hosted VPN Control Plane%b\n' "$C_BLUE" "$C_RESET"
  printf '  %bControl • Connect • Operate%b\n\n' "$C_DIM" "$C_RESET"
  printf '  %b●%b Official installer is starting...\n\n' "$C_GREEN" "$C_RESET"
}

normalize_protocol_selection(){
  local raw="${1:-}" token
  raw="${raw//,/ }"

  case "${raw,,}" in
    0|skip|none|no) printf '%s' ""; return 0 ;;
    6|all|'*') printf '%s' "all"; return 0 ;;
  esac

  local selected=()
  for token in $raw; do
    case "${token,,}" in
      1|cisco|openconnect) selected+=("cisco") ;;
      2|openvpn) selected+=("openvpn") ;;
      3|wireguard|wg) selected+=("wireguard") ;;
      4|l2tp|ipsec) selected+=("l2tp") ;;
      5|v2ray|xray) selected+=("v2ray") ;;
      *) return 2 ;;
    esac
  done

  local joined="" item
  for item in "${selected[@]}"; do
    if [[ ",$joined," == *",$item,"* ]]; then
      continue
    fi
    joined="${joined:+$joined,}$item"
  done
  printf '%s' "$joined"
}

setup_local_protocols(){
  local raw="${TWINPANEL_INSTALL_PROTOCOLS:-}"

  if (( EXISTING_INSTALL )) && [[ -z "$raw" ]]; then
    PROTOCOL_SETUP_STATUS="preserved-existing-install"
    info "Existing installation detected; protocol runtime was preserved."
    return 0
  fi

  if [[ -z "$raw" ]]; then
    raw="all"
    info "Fresh installation detected; all VPN protocols will be installed automatically."
  fi

  local selected
  if ! selected="$(normalize_protocol_selection "$raw")"; then
    warn "Invalid TWINPANEL_INSTALL_PROTOCOLS value '$raw'. Protocol setup was skipped."
    PROTOCOL_SETUP_STATUS="invalid-selection"
    return 0
  fi

  if [[ -z "$selected" ]]; then
    PROTOCOL_SETUP_STATUS="skipped"
    info "VPN protocol installation was explicitly skipped."
    return 0
  fi

  say "Installing VPN protocols automatically"
  info "Target: Local / This server"
  info "Protocols: $selected"

  set -a
  # shellcheck disable=SC1091
  source /etc/twinpanel/backend.env
  set +a

  if (
    cd /opt/twinpanel/current/backend
    export PYTHONPATH="/opt/twinpanel/current/backend${PYTHONPATH:+:$PYTHONPATH}"
    /opt/twinpanel/venv/bin/python3 scripts/twinpanel_installer_protocols.py --protocols "$selected"
  ); then
    PROTOCOL_SETUP_STATUS="completed:$selected"
    info "VPN protocols are installed and healthy."
  else
    PROTOCOL_SETUP_STATUS="partial-or-failed:$selected"
    warn "TwinPanel itself is installed, but one or more VPN protocols need attention."
    warn "Open 'twinpanel', choose 3 (VPN protocols), then use Status/Repair for the failed protocol."
  fi
}

brand_splash

[[ ${EUID:-$(id -u)} -eq 0 ]] || fail "Run as root / با دسترسی root اجرا کنید"

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
else
  fail "Unsupported system: /etc/os-release missing"
fi

[[ "${ID:-}" == "ubuntu" ]] || fail "Ubuntu 22.04/24.04 is required / فقط Ubuntu 22.04/24.04 پشتیبانی می‌شود"
case "${VERSION_ID:-}" in
  22.04|24.04) ;;
  *) fail "Unsupported Ubuntu version: ${VERSION_ID:-unknown}" ;;
esac

for cmd in curl python3 awk; do
  command -v "$cmd" >/dev/null 2>&1 || fail "Missing command: $cmd"
done

if ! command -v git >/dev/null 2>&1; then
  say "Installing Git"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y git ca-certificates
fi

say "$PRODUCT public installer"
echo "فارسی: نصب مستقیم TwinPanel از Release عمومی رسمی"
echo "English: direct TwinPanel installation from the official public release"

WORKDIR="$(mktemp -d -t twinpanel-public-install-XXXXXX)"
MANIFEST_FILE="$WORKDIR/stable.json"
SOURCE_DIR="$WORKDIR/source"

say "Resolving Stable release"
curl -fsSL --connect-timeout 10 --max-time 30 "$MANIFEST_URL" -o "$MANIFEST_FILE" \
  || fail "Could not download release manifest"

mapfile -t RELEASE < <(python3 - "$MANIFEST_FILE" <<'PY'
import json,sys
obj=json.load(open(sys.argv[1],encoding='utf-8'))
if obj.get('installable') is not True:
    raise SystemExit('release is not installable')
version=str(obj.get('version') or '').strip()
repo=str(obj.get('repository_url') or '').strip()
sha=str(obj.get('source_sha') or '').strip().lower()
channel=str(obj.get('channel') or 'stable').strip()
if not version:
    raise SystemExit('release version missing')
if not repo.startswith('https://github.com/') or not repo.endswith('.git'):
    raise SystemExit('release repository_url invalid')
if len(sha) != 40 or any(ch not in '0123456789abcdef' for ch in sha):
    raise SystemExit('release source_sha invalid')
print(version)
print(repo)
print(sha)
print(channel)
PY
) || fail "Release manifest is not installable or is incomplete"

VERSION="${RELEASE[0]}"
REPOSITORY_URL="${RELEASE[1]}"
SOURCE_SHA="${RELEASE[2]}"
CHANNEL="${RELEASE[3]}"

info "Version: $VERSION"
info "Channel: $CHANNEL"
info "Source: $SOURCE_SHA"

say "Fetching verified TwinPanel source"
git init -q "$SOURCE_DIR"
git -C "$SOURCE_DIR" remote add origin "$REPOSITORY_URL"
git -C "$SOURCE_DIR" -c advice.detachedHead=false fetch --depth 1 origin "$SOURCE_SHA"
git -C "$SOURCE_DIR" checkout -q --detach FETCH_HEAD

ACTUAL_SHA="$(git -C "$SOURCE_DIR" rev-parse HEAD | tr '[:upper:]' '[:lower:]')"
[[ "$ACTUAL_SHA" == "$SOURCE_SHA" ]] || fail "Release source SHA mismatch"
info "Git commit verified: $ACTUAL_SHA"

PACKAGE_VERSION="$(tr -d '[:space:]' < "$SOURCE_DIR/VERSION" 2>/dev/null || true)"
[[ "$PACKAGE_VERSION" == "$VERSION" ]] || fail "Release VERSION mismatch"
[[ -x "$SOURCE_DIR/installer/install.sh" || -f "$SOURCE_DIR/installer/install.sh" ]] || fail "installer/install.sh missing"

chmod +x "$SOURCE_DIR/installer/install.sh"
export TWINPANEL_RELEASE_CHANNEL="$CHANNEL"
export TWINPANEL_RELEASE_MANIFEST_URL="$MANIFEST_URL"

say "Installing TwinPanel $VERSION"
bash "$SOURCE_DIR/installer/install.sh"

# Canonicalize runtime release settings. Older release installers may still
# carry a historical public-manifest default.
if [[ -f /etc/twinpanel/backend.env ]]; then
  python3 - "$MANIFEST_URL" "$CHANNEL" <<'PY'
from pathlib import Path
import sys
manifest,channel=sys.argv[1:]
path=Path('/etc/twinpanel/backend.env')
text=path.read_text(encoding='utf-8')
updates={
    'TWINPANEL_RELEASE_CHANNEL':channel,
    'TWINPANEL_RELEASE_MANIFEST_URL':manifest,
}
lines=text.splitlines(); seen=set(); out=[]
for line in lines:
    if '=' in line and not line.lstrip().startswith('#'):
        key=line.split('=',1)[0].strip()
        if key in updates:
            out.append(f'{key}={updates[key]}'); seen.add(key); continue
    out.append(line)
for key,value in updates.items():
    if key not in seen:
        out.append(f'{key}={value}')
path.write_text('\n'.join(out).rstrip()+'\n',encoding='utf-8')
PY
  chmod 600 /etc/twinpanel/backend.env
fi

install -d -m 700 /etc/twinpanel
cat >/etc/twinpanel/install.env <<ENV
TWINPANEL_RELEASE_CHANNEL=$CHANNEL
TWINPANEL_RELEASE_MANIFEST_URL=$MANIFEST_URL
ENV
chmod 600 /etc/twinpanel/install.env

# Fresh public installs use the public-release updater. The licensed updater
# remains in source for future vendor-license deployments.
cat >/etc/systemd/system/twinpanel-updater.service <<'UNIT'
[Unit]
Description=TwinPanel Public Release Updater
After=network-online.target twinpanel-api.service
Wants=network-online.target

[Service]
Type=oneshot
User=root
Group=root
WorkingDirectory=/opt/twinpanel/current/backend
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=/etc/twinpanel/backend.env
EnvironmentFile=-/etc/twinpanel/install.env
ExecStart=/opt/twinpanel/venv/bin/python3 /opt/twinpanel/current/backend/scripts/twinpanel_public_updater.py
TimeoutStartSec=3600
Nice=5
IOSchedulingClass=best-effort
IOSchedulingPriority=6

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl restart twinpanel-api.service twinpanel-web.service 2>/dev/null || true
systemctl restart nginx 2>/dev/null || true

setup_local_protocols

say "Final health check"
for i in $(seq 1 60); do
  if curl -fsS --max-time 4 http://127.0.0.1/health >/dev/null 2>&1; then
    break
  fi
  [[ "$i" == 60 ]] && fail "Public health check failed after installation"
  sleep 2
done

PUBLIC_IP="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++)if($i=="src"){print $(i+1);exit}}')"

say "TwinPanel installation complete"
printf '%b%s%b\n' "$C_GREEN" "Installation finished successfully." "$C_RESET"
echo "Version: $VERSION"
echo "Source SHA: $SOURCE_SHA"
echo "Panel: http://${PUBLIC_IP:-SERVER_IP}"
echo "SSH management: twinpanel  (or: tp)"
echo "VPN protocols: $PROTOCOL_SETUP_STATUS"
echo "Initial admin: /root/twinpanel-initial-admin.txt"
echo "Release manifest: $MANIFEST_URL"
echo "نسخه: $VERSION"
echo "منوی SSH: twinpanel"
echo "اطلاعات ورود اولیه: /root/twinpanel-initial-admin.txt"
