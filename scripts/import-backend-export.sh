#!/usr/bin/env bash
set -Eeuo pipefail

ARCHIVE="${1:-}"
TARGET_ROOT="${2:-$(pwd)}"

fail(){ echo "ERROR: $*" >&2; exit 1; }
info(){ echo "[TwinPanel import] $*"; }

[[ -n "$ARCHIVE" ]] || fail "Usage: $0 /path/to/twinpanel-backend-clean-*.tar.gz [repo-root]"
[[ -f "$ARCHIVE" ]] || fail "Archive not found: $ARCHIVE"
[[ -d "$TARGET_ROOT/.git" ]] || fail "Target must be a TwinPanel git clone: $TARGET_ROOT"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"
command -v tar >/dev/null 2>&1 || fail "tar is required"
command -v git >/dev/null 2>&1 || fail "git is required"

CURRENT_BRANCH="$(git -C "$TARGET_ROOT" branch --show-current)"
case "$CURRENT_BRANCH" in
  feat/backend-runtime-import-*) ;;
  *) fail "Use a feat/backend-runtime-import-* branch. Current: ${CURRENT_BRANCH:-detached}" ;;
esac

info "Validating archive member paths"
MEMBERS="$(tar -tzf "$ARCHIVE")"
[[ -n "$MEMBERS" ]] || fail "Archive is empty"
if printf '%s\n' "$MEMBERS" | grep -E '(^/|(^|/)\.\.(/|$))' >/dev/null; then
  printf '%s\n' "$MEMBERS" | grep -E '(^/|(^|/)\.\.(/|$))' || true
  fail "Unsafe archive path detected"
fi

TMP="$(mktemp -d /tmp/twinpanel-backend-import.XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

tar -xzf "$ARCHIVE" -C "$TMP"
TOPS=("$TMP"/twinpanel-backend-clean-*)
[[ ${#TOPS[@]} -eq 1 && -d "${TOPS[0]}" ]] || fail "Expected one twinpanel-backend-clean-* directory"
STAGE="${TOPS[0]}"
SRC_BACKEND="$STAGE/backend"
SRC_APP="$SRC_BACKEND/app"
SRC_QUOTA="$STAGE/quota-agent"
[[ -f "$SRC_APP/main.py" ]] || fail "Export does not contain backend/app/main.py"
[[ -f "$SRC_BACKEND/requirements.txt" ]] || fail "Export does not contain backend/requirements.txt"

info "Rejecting forbidden files"
FORBIDDEN_FILES="$(find "$STAGE" -type f \( \
  -name '.env' -o -name '.env.*' -o -name 'config.json' -o -name '*.key' -o -name '*.pem' -o \
  -name '*.crt' -o -name '*.cer' -o -name '*.p12' -o -name '*.pfx' -o \
  -name '*.sql' -o -name '*.dump' -o -name '*.sqlite' -o -name '*.sqlite3' -o \
  -name '*.zip' -o -name '*.rar' -o -name '*.tgz' -o -name '*.tar' -o -name '*.tar.gz' \
\) -print || true)"
[[ -z "$FORBIDDEN_FILES" ]] || { echo "$FORBIDDEN_FILES"; fail "Forbidden file detected in export"; }

BAD_NAMES="$(find "$STAGE" -type f | grep -Ei '\.(bak|bad|old|disabled)(-|\.|$)|candidate|zeroed|before-' || true)"
[[ -z "$BAD_NAMES" ]] || { echo "$BAD_NAMES"; fail "Historical/candidate file detected in export"; }

SECRET_HITS="$(grep -RInE \
  'BEGIN ([A-Z0-9 ]+ )?PRIVATE KEY|BEGIN OPENSSH PRIVATE KEY|github_pat_[A-Za-z0-9_]+|ghp_[A-Za-z0-9]+|AKIA[0-9A-Z]{16}|[0-9]{8,12}:[A-Za-z0-9_-]{30,}' \
  "$SRC_BACKEND" "$SRC_QUOTA" 2>/dev/null || true)"
[[ -z "$SECRET_HITS" ]] || { echo "$SECRET_HITS"; fail "Potential embedded secret/private key detected"; }

info "Compiling exported runtime"
python3 -m compileall -q "$SRC_APP"
find "$SRC_APP" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$SRC_APP" -type f -name '*.pyc' -delete 2>/dev/null || true
if [[ -f "$SRC_QUOTA/agent.py" ]]; then
  python3 -m compileall -q "$SRC_QUOTA"
  find "$SRC_QUOTA" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
  find "$SRC_QUOTA" -type f -name '*.pyc' -delete 2>/dev/null || true
fi

TARGET_BACKEND="$TARGET_ROOT/backend"
TARGET_APP="$TARGET_BACKEND/app"
TARGET_QUOTA="$TARGET_ROOT/quota-agent"
rm -rf "$TARGET_APP"
mkdir -p "$TARGET_APP"
cp -a "$SRC_APP/." "$TARGET_APP/"
cp -f "$SRC_BACKEND/requirements.txt" "$TARGET_BACKEND/requirements.txt"

if [[ -f "$SRC_BACKEND/alembic.ini" && -d "$SRC_BACKEND/alembic" ]]; then
  rm -rf "$TARGET_BACKEND/alembic"
  cp -f "$SRC_BACKEND/alembic.ini" "$TARGET_BACKEND/alembic.ini"
  cp -a "$SRC_BACKEND/alembic" "$TARGET_BACKEND/alembic"
fi

rm -rf "$TARGET_QUOTA"
if [[ -f "$SRC_QUOTA/agent.py" ]]; then
  mkdir -p "$TARGET_QUOTA"
  cp -a "$SRC_QUOTA/." "$TARGET_QUOTA/"
fi

(
  cd "$TARGET_BACKEND"
  find app -type f -print0 | sort -z | xargs -0 sha256sum > RUNTIME_MANIFEST.sha256
)

python3 -m compileall -q "$TARGET_APP"
find "$TARGET_APP" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$TARGET_APP" -type f -name '*.pyc' -delete 2>/dev/null || true
if [[ -f "$TARGET_QUOTA/agent.py" ]]; then
  python3 -m compileall -q "$TARGET_QUOTA"
  find "$TARGET_QUOTA" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
  find "$TARGET_QUOTA" -type f -name '*.pyc' -delete 2>/dev/null || true
fi

COUNT="$(find "$TARGET_APP" -type f | wc -l | tr -d ' ')"
QUOTA_COUNT=0
[[ -d "$TARGET_QUOTA" ]] && QUOTA_COUNT="$(find "$TARGET_QUOTA" -type f | wc -l | tr -d ' ')"
echo "COMPILE_OK"
echo "CLEAN_NAMES_OK"
echo "SECRET_SCAN_OK"
echo "RUNTIME_FILE_COUNT=$COUNT"
echo "QUOTA_AGENT_FILE_COUNT=$QUOTA_COUNT"
echo "BACKEND_EXPORT_IMPORTED"
echo
git -C "$TARGET_ROOT" status --short backend quota-agent 2>/dev/null || true
