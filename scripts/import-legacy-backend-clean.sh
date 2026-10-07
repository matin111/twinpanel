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
if [ "$CURRENT_BRANCH" != "feat/backend-runtime-clean" ]; then
  fail "Checkout feat/backend-runtime-clean first. Current branch: ${CURRENT_BRANCH:-detached}"
fi

echo "============================================================"
echo " TwinPanel Legacy Backend Clean Import"
echo "============================================================"
echo "Source : $SOURCE_ROOT"
echo "Target : $TARGET_ROOT"
echo "Branch : $CURRENT_BRANCH"
echo

mkdir -p "$TARGET_BACKEND"
rm -rf "$TARGET_APP"
mkdir -p "$TARGET_APP"

# Copy the runtime app tree while excluding known historical/build artifacts.
(
  cd "$SOURCE_APP"
  tar \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='*.bak' \
    --exclude='*.bak-*' \
    --exclude='*.backup' \
    --exclude='*.backup-*' \
    --exclude='*.old' \
    --exclude='*.old-*' \
    --exclude='*.bad' \
    --exclude='*.bad-*' \
    --exclude='*.broken*' \
    --exclude='*.disabled*' \
    --exclude='*candidate*' \
    --exclude='*.log' \
    -cf - .
) | (cd "$TARGET_APP" && tar -xf -)

# Remove explicitly known non-runtime historical copies.
find "$TARGET_APP" -type f \( \
  -name '*zeroed*' -o \
  -name '*before-*' -o \
  -name '*candidate*' -o \
  -name '*.bak*' -o \
  -name '*.bad*' -o \
  -name '*.broken*' -o \
  -name '*.disabled*' \
\) -delete

# Never allow environment files, private material, dumps or archives into backend source.
FORBIDDEN_FILES="$(find "$TARGET_BACKEND" -type f \( \
  -name '.env' -o \
  -name '.env.*' -o \
  -name '*.key' -o \
  -name '*.pem' -o \
  -name '*.crt' -o \
  -name '*.cer' -o \
  -name '*.p12' -o \
  -name '*.pfx' -o \
  -name '*.sql' -o \
  -name '*.dump' -o \
  -name '*.sqlite' -o \
  -name '*.sqlite3' -o \
  -name '*.tar' -o \
  -name '*.tar.gz' -o \
  -name '*.tgz' -o \
  -name '*.zip' -o \
  -name '*.rar' \
\) -print)"

if [ -n "$FORBIDDEN_FILES" ]; then
  echo "$FORBIDDEN_FILES"
  fail "Forbidden files detected in backend import"
fi

# Copy dependency lock/source list only; never copy the old project root wholesale.
if [ -f "$SOURCE_ROOT/requirements.txt" ]; then
  cp -f "$SOURCE_ROOT/requirements.txt" "$TARGET_BACKEND/requirements.txt"
fi

# Preserve the repository-safe env example already maintained in Git.
if [ ! -f "$TARGET_BACKEND/.env.example" ]; then
  fail "backend/.env.example is missing from repository"
fi

# Secret/private-key scan. Variable names are allowed; obvious embedded credentials are not.
SECRET_HITS="$(grep -RInE \
  'BEGIN ([A-Z0-9 ]+ )?PRIVATE KEY|BEGIN OPENSSH PRIVATE KEY|github_pat_[A-Za-z0-9_]+|ghp_[A-Za-z0-9]+|AKIA[0-9A-Z]{16}' \
  "$TARGET_APP" 2>/dev/null || true)"
if [ -n "$SECRET_HITS" ]; then
  echo "$SECRET_HITS"
  fail "Potential embedded secret/private key detected"
fi

# Compile every Python module before allowing a commit.
echo "===== PYTHON COMPILE CHECK ====="
python3 -m compileall -q "$TARGET_APP"
find "$TARGET_APP" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$TARGET_APP" -type f -name '*.pyc' -delete

echo "COMPILE_OK"

echo
echo "===== RUNTIME FILE COUNT ====="
find "$TARGET_APP" -type f | wc -l

echo
echo "===== FORBIDDEN NAME CHECK ====="
BAD_NAMES="$(find "$TARGET_APP" -type f | grep -Ei '\.(bak|bad|old|disabled)(-|\.|$)|candidate|zeroed|before-' || true)"
if [ -n "$BAD_NAMES" ]; then
  echo "$BAD_NAMES"
  fail "Historical file names remain after cleanup"
fi
echo "CLEAN_NAMES_OK"

# Create deterministic source manifest for review.
(
  cd "$TARGET_BACKEND"
  find app -type f -print0 | sort -z | xargs -0 sha256sum > RUNTIME_MANIFEST.sha256
)

echo
echo "===== GIT STATUS ====="
git -C "$TARGET_ROOT" status --short backend

echo
echo "============================================================"
echo " CLEAN BACKEND IMPORT READY"
echo "============================================================"
echo "Review the diff before committing:"
echo "  git -C '$TARGET_ROOT' diff --stat"
echo "  git -C '$TARGET_ROOT' status --short"
echo
echo "This script intentionally does NOT commit or push automatically."
