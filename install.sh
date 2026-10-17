#!/usr/bin/env bash
set -Eeuo pipefail

PRODUCT="TwinPanel"
DEFAULT_MANIFEST_URL="https://raw.githubusercontent.com/matin111/twinpanel/main/releases/stable.json"
MANIFEST_URL="${TWINPANEL_RELEASE_MANIFEST_URL:-$DEFAULT_MANIFEST_URL}"
WORKDIR=""

say(){ printf '\n\033[1;35m%s\033[0m\n' "$*"; }
info(){ printf '\033[1;34m%s\033[0m\n' "$*"; }
fail(){ printf '\nERROR: %s\n' "$*" >&2; exit 1; }
cleanup(){ [[ -n "${WORKDIR:-}" && -d "$WORKDIR" ]] && rm -rf "$WORKDIR" || true; }
trap cleanup EXIT

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

for cmd in curl python3 sha256sum tar awk; do
  command -v "$cmd" >/dev/null 2>&1 || fail "Missing command: $cmd"
done

say "$PRODUCT public installer"
echo "فارسی: نصب مستقیم TwinPanel از Release عمومی رسمی"
echo "English: direct TwinPanel installation from the official public release"

WORKDIR="$(mktemp -d -t twinpanel-public-install-XXXXXX)"
MANIFEST_FILE="$WORKDIR/stable.json"
PACKAGE_FILE="$WORKDIR/twinpanel-release.tar.gz"
EXTRACT_DIR="$WORKDIR/release"
mkdir -p "$EXTRACT_DIR"

say "Resolving Stable release"
curl -fsSL --connect-timeout 10 --max-time 30 "$MANIFEST_URL" -o "$MANIFEST_FILE" \
  || fail "Could not download release manifest"

mapfile -t RELEASE < <(python3 - "$MANIFEST_FILE" <<'PY'
import json,sys
obj=json.load(open(sys.argv[1],encoding='utf-8'))
installable=obj.get('installable') is True
version=str(obj.get('version') or '').strip()
url=str(obj.get('package_url') or '').strip()
sha=str(obj.get('sha256') or '').strip().lower()
channel=str(obj.get('channel') or 'stable').strip()
if not installable:
    raise SystemExit('release is not installable')
if not version:
    raise SystemExit('release version missing')
if not url:
    raise SystemExit('release package_url missing')
if len(sha) != 64 or any(ch not in '0123456789abcdef' for ch in sha):
    raise SystemExit('release sha256 invalid')
print(version)
print(url)
print(sha)
print(channel)
PY
) || fail "Release manifest is not installable or is incomplete"

VERSION="${RELEASE[0]}"
PACKAGE_URL="${RELEASE[1]}"
EXPECTED_SHA="${RELEASE[2]}"
CHANNEL="${RELEASE[3]}"

info "Version: $VERSION"
info "Channel: $CHANNEL"

say "Downloading TwinPanel $VERSION"
curl -fL --retry 3 --connect-timeout 10 --max-time 1200 \
  "$PACKAGE_URL" -o "$PACKAGE_FILE"

ACTUAL_SHA="$(sha256sum "$PACKAGE_FILE" | awk '{print tolower($1)}')"
[[ "$ACTUAL_SHA" == "$EXPECTED_SHA" ]] || fail "Package SHA256 mismatch"
info "SHA256 verified"

say "Extracting verified release"
python3 - "$PACKAGE_FILE" "$EXTRACT_DIR" <<'PY'
from pathlib import Path
import sys,tarfile
archive=Path(sys.argv[1])
dest=Path(sys.argv[2]).resolve()
with tarfile.open(archive,'r:gz') as tar:
    for member in tar.getmembers():
        target=(dest/member.name).resolve()
        if target != dest and dest not in target.parents:
            raise SystemExit('unsafe release archive')
    tar.extractall(dest)
PY

ENTRY="$(find "$EXTRACT_DIR" -maxdepth 4 -type f -path '*/installer/install.sh' -print -quit)"
[[ -n "$ENTRY" ]] || fail "installer/install.sh missing from release package"
RELEASE_ROOT="$(cd "$(dirname "$ENTRY")/.." && pwd)"

PACKAGE_VERSION="$(tr -d '[:space:]' < "$RELEASE_ROOT/VERSION" 2>/dev/null || true)"
[[ "$PACKAGE_VERSION" == "$VERSION" ]] || fail "Release VERSION mismatch"

chmod +x "$ENTRY"
export TWINPANEL_RELEASE_CHANNEL="$CHANNEL"
export TWINPANEL_RELEASE_MANIFEST_URL="$MANIFEST_URL"

say "Installing TwinPanel $VERSION"
bash "$ENTRY"

# The historical installer may come from an older package that wrote the old
# public-manifest location. Canonicalize runtime release settings after install.
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

systemctl daemon-reload
systemctl restart twinpanel-api.service twinpanel-web.service 2>/dev/null || true
systemctl restart nginx 2>/dev/null || true

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
echo "Version: $VERSION"
echo "Panel: http://${PUBLIC_IP:-SERVER_IP}"
echo "SSH management: twinpanel  (or: tp)"
echo "Initial admin: /root/twinpanel-initial-admin.txt"
echo "Release manifest: $MANIFEST_URL"
echo "نسخه: $VERSION"
echo "منوی SSH: twinpanel"
echo "اطلاعات ورود اولیه: /root/twinpanel-initial-admin.txt"
