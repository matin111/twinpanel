#!/usr/bin/env bash
set -euo pipefail

SOURCE_ROOT="${1:-/root/vpnshop/vpnshop}"
TARGET_ROOT="${2:-$(pwd)}"
SOURCE_APP="$SOURCE_ROOT/app"
TARGET_BACKEND="$TARGET_ROOT/backend"
TARGET_APP="$TARGET_BACKEND/app"

fail(){ echo "ERROR: $*" >&2; exit 1; }

[ -d "$SOURCE_APP" ] || fail "Source app directory not found: $SOURCE_APP"
[ -d "$TARGET_ROOT/.git" ] || fail "Target must be a TwinPanel git clone: $TARGET_ROOT"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"
command -v git >/dev/null 2>&1 || fail "git is required"

CURRENT_BRANCH="$(git -C "$TARGET_ROOT" branch --show-current)"
case "$CURRENT_BRANCH" in
  feat/backend-runtime-import-*) ;;
  *) fail "Use a feat/backend-runtime-import-* branch. Current: ${CURRENT_BRANCH:-detached}" ;;
esac

mkdir -p "$TARGET_BACKEND"
rm -rf "$TARGET_APP"
mkdir -p "$TARGET_APP"

(
  cd "$SOURCE_APP"
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
    -cf - .
) | (cd "$TARGET_APP" && tar -xf -)

FORBIDDEN_FILES="$(find "$TARGET_APP" -type f \( \
  -name '.env' -o -name '.env.*' -o -name '*.key' -o -name '*.pem' -o \
  -name '*.crt' -o -name '*.cer' -o -name '*.p12' -o -name '*.pfx' -o \
  -name '*.sql' -o -name '*.dump' -o -name '*.sqlite' -o -name '*.sqlite3' -o \
  -name '*.tar' -o -name '*.tar.gz' -o -name '*.tgz' -o -name '*.zip' -o -name '*.rar' \
\) -print || true)"
[ -z "$FORBIDDEN_FILES" ] || { echo "$FORBIDDEN_FILES"; fail "Forbidden files detected"; }

if [ -f "$SOURCE_ROOT/requirements.txt" ]; then
  cp -f "$SOURCE_ROOT/requirements.txt" "$TARGET_BACKEND/requirements.txt"
fi

SECRET_HITS="$(grep -RInE 'BEGIN ([A-Z0-9 ]+ )?PRIVATE KEY|BEGIN OPENSSH PRIVATE KEY|github_pat_[A-Za-z0-9_]+|ghp_[A-Za-z0-9]+|AKIA[0-9A-Z]{16}' "$TARGET_APP" 2>/dev/null || true)"
[ -z "$SECRET_HITS" ] || { echo "$SECRET_HITS"; fail "Potential embedded secret/private key detected"; }

python3 -m compileall -q "$TARGET_APP"
find "$TARGET_APP" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$TARGET_APP" -type f -name '*.pyc' -delete

BAD_NAMES="$(find "$TARGET_APP" -type f | grep -Ei '\.(bak|bad|old|disabled)(-|\.|$)|candidate|zeroed|before-' || true)"
[ -z "$BAD_NAMES" ] || { echo "$BAD_NAMES"; fail "Historical files remain"; }

(
  cd "$TARGET_BACKEND"
  find app -type f -print0 | sort -z | xargs -0 sha256sum > RUNTIME_MANIFEST.sha256
)

COUNT="$(find "$TARGET_APP" -type f | wc -l)"
echo "COMPILE_OK"
echo "CLEAN_NAMES_OK"
echo "RUNTIME_FILE_COUNT=$COUNT"
echo "CLEAN_BACKEND_IMPORT_READY"
echo
git -C "$TARGET_ROOT" status --short backend
