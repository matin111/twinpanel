#!/usr/bin/env bash
set -Eeuo pipefail

# TwinPanel preview deploy for CLY871416.
# IMPORTANT: this script is intentionally WEB-ONLY.
# It must never copy preview/backend into /opt/twinpanel/current/backend,
# restart twinpanel-api.service, restart reseller bots, or touch tunnel runtimes.

EXPECTED_HOST="CLY871416"
REPO_DIR="${REPO_DIR:-/opt/twinpanel-preview}"
BRANCH="${BRANCH:-fix/customer-panel-entry-crash-v2}"
WEB_SERVICE="${WEB_SERVICE:-twinpanel-preview.service}"
WEB_URL="${WEB_URL:-http://127.0.0.1:3010}"
API_URL="${API_URL:-http://127.0.0.1:8095}"

log() {
  printf '\n[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

fail() {
  echo "ERROR: $*" >&2
  return 1
}

wait_http_ok() {
  local url="$1"
  local tries="${2:-50}"
  local i code
  for ((i=1; i<=tries; i++)); do
    code="$(curl -sS -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true)"
    case "$code" in
      200|301|302|307|308) return 0 ;;
    esac
    sleep 1
  done
  return 1
}

install_frontend_dependencies() {
  cd "$REPO_DIR"
  if [[ -f package-lock.json || -f npm-shrinkwrap.json ]]; then
    npm ci --include=optional --no-audit --no-fund
  else
    npm install --include=optional --no-audit --no-fund --package-lock=false
  fi
}

for cmd in git curl systemctl npm node; do
  command -v "$cmd" >/dev/null 2>&1 || fail "missing command: $cmd"
done

ACTUAL_HOST="$(hostname)"
[[ "$ACTUAL_HOST" == "$EXPECTED_HOST" || "${ALLOW_HOST_MISMATCH:-0}" == "1" ]] \
  || fail "this deploy is pinned to $EXPECTED_HOST, current host is $ACTUAL_HOST"

[[ -d "$REPO_DIR/.git" ]] || fail "git repository not found: $REPO_DIR"
[[ -f "$REPO_DIR/package.json" ]] || fail "package.json not found: $REPO_DIR/package.json"
systemctl cat "$WEB_SERVICE" >/dev/null

cd "$REPO_DIR"

log "PRE-FLIGHT: VERIFY PREVIEW WORKTREE"
CURRENT_BRANCH="$(git branch --show-current)"
[[ "$CURRENT_BRANCH" == "$BRANCH" ]] || fail "wrong branch: $CURRENT_BRANCH"

# Generated local lockfiles are not source and may safely be removed when untracked.
if [[ -f package-lock.json ]] && ! git ls-files --error-unmatch package-lock.json >/dev/null 2>&1; then
  rm -f package-lock.json
fi

# Never hide tracked source changes during deployment.
git diff --quiet || fail "tracked preview worktree has unstaged changes"
git diff --cached --quiet || fail "tracked preview worktree has staged changes"

OLD_HEAD="$(git rev-parse HEAD)"

log "FETCHING PREVIEW BRANCH"
git fetch origin --prune
git rev-parse --verify "origin/$BRANCH" >/dev/null
TARGET_HEAD="$(git rev-parse "origin/$BRANCH")"

echo "OLD_HEAD=$OLD_HEAD"
echo "TARGET_HEAD=$TARGET_HEAD"
echo "BRANCH=$BRANCH"

log "FAST-FORWARDING PREVIEW SOURCE"
git merge --ff-only "origin/$BRANCH"
NEW_HEAD="$(git rev-parse HEAD)"
[[ "$NEW_HEAD" == "$TARGET_HEAD" ]] || fail "preview head mismatch after fast-forward"

log "ASSERTING DEPLOY IS WEB-ONLY"
# These paths are informational guards: no command below writes to or restarts them.
LIVE_BACKEND="$(readlink -f /opt/twinpanel/current/backend 2>/dev/null || true)"
echo "LIVE_BACKEND=${LIVE_BACKEND:-unknown}"
echo "API_STATE=$(systemctl is-active twinpanel-api.service 2>/dev/null || true)"
echo "BOT_STATE=$(systemctl is-active twinpanel-reseller-bots.service 2>/dev/null || true)"
echo "MANAGER_STATE=$(systemctl is-active twinpanel-transport-manager.service 2>/dev/null || true)"

log "INSTALLING FRONTEND DEPENDENCIES"
install_frontend_dependencies

log "BUILDING FRONTEND"
npm run build

# Next may rewrite generated TypeScript metadata. Keep the tracked source clean.
git restore next-env.d.ts tsconfig.json 2>/dev/null || true
if [[ -f package-lock.json ]] && ! git ls-files --error-unmatch package-lock.json >/dev/null 2>&1; then
  rm -f package-lock.json
fi

log "RESTARTING PREVIEW WEB ONLY"
OLD_WEB_PID="$(systemctl show -p MainPID --value "$WEB_SERVICE")"
systemctl restart "$WEB_SERVICE"
sleep 3
NEW_WEB_PID="$(systemctl show -p MainPID --value "$WEB_SERVICE")"

echo "OLD_WEB_PID=$OLD_WEB_PID"
echo "NEW_WEB_PID=$NEW_WEB_PID"
systemctl is-active --quiet "$WEB_SERVICE" || fail "$WEB_SERVICE is not active"
wait_http_ok "$WEB_URL/login" || fail "preview /login health check failed"

log "READ-ONLY API HEALTH CHECK"
# Do not restart or mutate API here.
curl -fsS "$API_URL/health" >/dev/null || fail "API health check failed"

log "FINAL"
git status --short

echo "HEAD=$NEW_HEAD"
echo "WEB=$(systemctl is-active "$WEB_SERVICE")"
echo "API=$(systemctl is-active twinpanel-api.service 2>/dev/null || true)"
echo "BOT=$(systemctl is-active twinpanel-reseller-bots.service 2>/dev/null || true)"
echo "MANAGER=$(systemctl is-active twinpanel-transport-manager.service 2>/dev/null || true)"
echo "PREVIEW_WEB_ONLY_DEPLOY_OK"
