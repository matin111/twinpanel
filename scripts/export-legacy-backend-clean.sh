#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_ROOT="${1:-/root/vpnshop/vpnshop}"
OUT_DIR="${2:-/root}"
SOURCE_APP="$SOURCE_ROOT/app"
PYTHON_BIN="$SOURCE_ROOT/venv/bin/python"

fail(){ echo "ERROR: $*" >&2; exit 1; }
info(){ echo "[TwinPanel export] $*"; }

[[ $EUID -eq 0 ]] || fail "این Export باید روی سرور قدیمی با root اجرا شود"
[[ -d "$SOURCE_APP" ]] || fail "Source app directory not found: $SOURCE_APP"
[[ -f "$SOURCE_ROOT/requirements.txt" ]] || fail "requirements.txt پیدا نشد"
[[ -x "$PYTHON_BIN" ]] || PYTHON_BIN="$(command -v python3 || true)"
[[ -n "$PYTHON_BIN" ]] || fail "python3 پیدا نشد"
mkdir -p "$OUT_DIR"

STAMP="$(date -u +%Y%m%d-%H%M%S)"
TMP="$(mktemp -d /tmp/twinpanel-backend-export.XXXXXX)"
STAGE="$TMP/twinpanel-backend-clean-$STAMP"
TARGET_BACKEND="$STAGE/backend"
TARGET_APP="$TARGET_BACKEND/app"
TARGET_QUOTA="$STAGE/quota-agent"
OUT="$OUT_DIR/twinpanel-backend-clean-$STAMP.tar.gz"
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TARGET_APP"

copy_python_tree(){
  local source="$1" target="$2"
  mkdir -p "$target"
  (
    cd "$source"
    tar \
      --exclude='__pycache__' \
      --exclude='*.pyc' \
      --exclude='*.pyo' \
      --exclude='*.bak*' \
      --exclude='*.backup*' \
      --exclude='*.old*' \
      --exclude='*.bad*' \
      --exclude='*.broken*' \
      --exclude='*.disabled*' \
      --exclude='*candidate*' \
      --exclude='*zeroed*' \
      --exclude='*before-*' \
      --exclude='*.log' \
      --exclude='.env' \
      --exclude='.env.*' \
      --exclude='config.json' \
      --exclude='pki' \
      --exclude='*.key' \
      --exclude='*.pem' \
      --exclude='*.crt' \
      --exclude='*.cer' \
      --exclude='*.p12' \
      --exclude='*.pfx' \
      --exclude='*.sql' \
      --exclude='*.dump' \
      --exclude='*.sqlite' \
      --exclude='*.sqlite3' \
      -cf - .
  ) | (cd "$target" && tar -xf -)
}

info "Copying active Python runtime"
copy_python_tree "$SOURCE_APP" "$TARGET_APP"
cp -f "$SOURCE_ROOT/requirements.txt" "$TARGET_BACKEND/requirements.txt"

# If the legacy source already has a real Alembic tree, include it. Do not invent one.
if [[ -f "$SOURCE_ROOT/alembic.ini" && -d "$SOURCE_ROOT/alembic" ]]; then
  cp -f "$SOURCE_ROOT/alembic.ini" "$TARGET_BACKEND/alembic.ini"
  cp -a "$SOURCE_ROOT/alembic" "$TARGET_BACKEND/alembic"
fi

# Optional healthy Quota Agent code. Config, PKI and state are deliberately excluded.
QUOTA_SOURCE=""
for candidate in /opt/twinpanel-quota-agent /opt/moviline-quota-agent; do
  if [[ -f "$candidate/agent.py" ]]; then QUOTA_SOURCE="$candidate"; break; fi
done
if [[ -n "$QUOTA_SOURCE" ]]; then
  info "Copying Quota Agent code from $QUOTA_SOURCE (without config/PKI/state)"
  copy_python_tree "$QUOTA_SOURCE" "$TARGET_QUOTA"
fi

info "Rejecting forbidden files"
FORBIDDEN_FILES="$(find "$STAGE" -type f \( \
  -name '.env' -o -name '.env.*' -o -name 'config.json' -o -name '*.key' -o -name '*.pem' -o \
  -name '*.crt' -o -name '*.cer' -o -name '*.p12' -o -name '*.pfx' -o \
  -name '*.sql' -o -name '*.dump' -o -name '*.sqlite' -o -name '*.sqlite3' -o \
  -name '*.tar' -o -name '*.tar.gz' -o -name '*.tgz' -o -name '*.zip' -o -name '*.rar' \
\) -print || true)"
[[ -z "$FORBIDDEN_FILES" ]] || { echo "$FORBIDDEN_FILES"; fail "Forbidden files detected"; }

BAD_NAMES="$(find "$STAGE" -type f | grep -Ei '\.(bak|bad|old|disabled)(-|\.|$)|candidate|zeroed|before-' || true)"
[[ -z "$BAD_NAMES" ]] || { echo "$BAD_NAMES"; fail "Historical/candidate files remain"; }

info "Scanning obvious embedded secrets"
SECRET_HITS="$(grep -RInE \
  'BEGIN ([A-Z0-9 ]+ )?PRIVATE KEY|BEGIN OPENSSH PRIVATE KEY|github_pat_[A-Za-z0-9_]+|ghp_[A-Za-z0-9]+|AKIA[0-9A-Z]{16}|[0-9]{8,12}:[A-Za-z0-9_-]{30,}' \
  "$TARGET_BACKEND" "$TARGET_QUOTA" 2>/dev/null || true)"
[[ -z "$SECRET_HITS" ]] || { echo "$SECRET_HITS"; fail "Potential embedded secret/private key detected"; }

info "Compiling Python runtime"
"$PYTHON_BIN" -m compileall -q "$TARGET_APP"
find "$TARGET_APP" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$TARGET_APP" -type f -name '*.pyc' -delete 2>/dev/null || true

QUOTA_COUNT=0
if [[ -f "$TARGET_QUOTA/agent.py" ]]; then
  python3 -m compileall -q "$TARGET_QUOTA"
  find "$TARGET_QUOTA" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
  find "$TARGET_QUOTA" -type f -name '*.pyc' -delete 2>/dev/null || true
  (cd "$TARGET_QUOTA" && find . -type f -print0 | sort -z | xargs -0 sha256sum > QUOTA_AGENT_MANIFEST.sha256)
  QUOTA_COUNT="$(find "$TARGET_QUOTA" -type f ! -name 'QUOTA_AGENT_MANIFEST.sha256' | wc -l | tr -d ' ')"
fi

(
  cd "$TARGET_BACKEND"
  find app -type f -print0 | sort -z | xargs -0 sha256sum > RUNTIME_MANIFEST.sha256
)

COUNT="$(find "$TARGET_APP" -type f | wc -l | tr -d ' ')"
{
  echo "TwinPanel legacy backend clean export"
  echo "created_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "source_root=$SOURCE_ROOT"
  echo "runtime_file_count=$COUNT"
  echo "quota_agent_file_count=$QUOTA_COUNT"
  echo "python=$($PYTHON_BIN --version 2>&1)"
  echo "hostname=$(hostname -f 2>/dev/null || hostname)"
} > "$STAGE/EXPORT_MANIFEST.txt"

info "Creating archive"
tar -C "$TMP" -czf "$OUT" "$(basename "$STAGE")"
chmod 600 "$OUT"
SHA="$(sha256sum "$OUT" | awk '{print $1}')"

cat <<EOF
COMPILE_OK
CLEAN_NAMES_OK
SECRET_SCAN_OK
RUNTIME_FILE_COUNT=$COUNT
QUOTA_AGENT_FILE_COUNT=$QUOTA_COUNT
EXPORT=$OUT
SHA256=$SHA
CLEAN_BACKEND_EXPORT_READY
EOF
