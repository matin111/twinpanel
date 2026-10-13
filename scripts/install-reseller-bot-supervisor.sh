#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR="${SOURCE_DIR:-/opt/twinpanel-preview}"
BACKEND_DIR="${BACKEND_DIR:-/opt/twinpanel/current/backend}"
VENV_DIR="${VENV_DIR:-/opt/twinpanel/venv}"
SERVICE_NAME="${SERVICE_NAME:-twinpanel-reseller-bots.service}"
TEMPLATE="$SOURCE_DIR/deploy/systemd/twinpanel-reseller-bots.service.tpl"
TARGET="/etc/systemd/system/$SERVICE_NAME"

for cmd in install systemctl grep; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "missing command: $cmd" >&2
    exit 1
  }
done

[[ -d "$BACKEND_DIR" ]] || {
  echo "backend directory not found: $BACKEND_DIR" >&2
  exit 1
}

[[ -x "$VENV_DIR/bin/python" ]] || {
  echo "python venv not found: $VENV_DIR" >&2
  exit 1
}

[[ -x "$VENV_DIR/bin/pip" ]] || {
  echo "pip not found: $VENV_DIR/bin/pip" >&2
  exit 1
}

[[ -f "$BACKEND_DIR/requirements.txt" ]] || {
  echo "requirements not found: $BACKEND_DIR/requirements.txt" >&2
  exit 1
}

[[ -f "$BACKEND_DIR/app/reseller_bot_runtime.py" ]] || {
  echo "reseller bot runtime not found" >&2
  exit 1
}

[[ -f "$TEMPLATE" ]] || {
  echo "service template not found: $TEMPLATE" >&2
  exit 1
}

printf '\n[1/5] Installing backend dependencies\n'
"$VENV_DIR/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"

printf '\n[2/5] Verifying reseller bot runtime import\n'
(
  cd "$BACKEND_DIR"
  PYTHONPATH="$BACKEND_DIR" "$VENV_DIR/bin/python" - <<'PY'
from app.reseller_bot_runtime import build_router, supervisor
from app.reseller_bot_review import register_reseller_review_handlers
print("RESELLER_BOT_RUNTIME_IMPORT_OK")
print(build_router.__name__, supervisor.__name__, register_reseller_review_handlers.__name__)
PY
)

printf '\n[3/5] Installing systemd service\n'
install -m 0644 "$TEMPLATE" "$TARGET"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

printf '\n[4/5] Starting reseller bot supervisor\n'
systemctl restart "$SERVICE_NAME"
sleep 3
systemctl is-active --quiet "$SERVICE_NAME"

printf '\n[5/5] Final status\n'
systemctl status "$SERVICE_NAME" --no-pager -l

echo
printf 'RESELLER_BOT_SUPERVISOR_READY\n'
