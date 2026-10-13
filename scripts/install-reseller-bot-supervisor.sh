#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR="${SOURCE_DIR:-/opt/twinpanel-preview}"
BACKEND_DIR="${BACKEND_DIR:-/opt/twinpanel/current/backend}"
VENV_DIR="${VENV_DIR:-/opt/twinpanel/venv}"
SERVICE_NAME="${SERVICE_NAME:-twinpanel-reseller-bots.service}"
KEY_FILE="${KEY_FILE:-/etc/twinpanel-reseller-bot.key}"
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

for runtime_file in \
  "$BACKEND_DIR/app/reseller_bot_runtime.py" \
  "$BACKEND_DIR/app/reseller_bot_runtime_owned.py" \
  "$BACKEND_DIR/app/reseller_bot_owned_runtime.py"; do
  [[ -f "$runtime_file" ]] || {
    echo "reseller bot runtime not found: $runtime_file" >&2
    exit 1
  }
done

[[ -f "$TEMPLATE" ]] || {
  echo "service template not found: $TEMPLATE" >&2
  exit 1
}

printf '\n[1/6] Installing backend dependencies\n'
"$VENV_DIR/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"

printf '\n[2/6] Ensuring reseller bot encryption key\n'
install -d -m 0755 "$(dirname "$KEY_FILE")"
KEY_FILE="$KEY_FILE" "$VENV_DIR/bin/python" - <<'PY'
import os
from pathlib import Path
from cryptography.fernet import Fernet

path = Path(os.environ["KEY_FILE"])

if path.exists():
    key = path.read_bytes().strip()
    if not key:
        raise SystemExit(f"reseller bot key is empty: {path}")
    try:
        Fernet(key)
    except Exception as exc:
        raise SystemExit(f"reseller bot key is invalid: {path}: {exc}") from exc
    os.chmod(path, 0o600)
    print(f"RESELLER_BOT_KEY_OK existing={path}")
else:
    key = Fernet.generate_key()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(key + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink(missing_ok=True)
        finally:
            raise
    os.chmod(path, 0o600)
    print(f"RESELLER_BOT_KEY_CREATED path={path}")
PY

printf '\n[3/6] Verifying reseller bot runtime import\n'
(
  cd "$BACKEND_DIR"
  PYTHONPATH="$BACKEND_DIR" "$VENV_DIR/bin/python" - <<'PY'
from app.reseller_bot_runtime import supervisor
from app.reseller_bot_runtime_owned import build_router, install_runtime_overrides
from app.reseller_bot_owned_runtime import build_owned_plan_router
from app.reseller_bot_review import register_reseller_review_handlers
from app.routers.reseller_bot_orders_owned_v3 import approve_order_owned_v3
from app.reseller_bot_crypto import encrypt_bot_token, decrypt_bot_token

assert callable(build_router)
assert callable(build_owned_plan_router)
assert callable(install_runtime_overrides)
assert callable(supervisor)
assert callable(register_reseller_review_handlers)
assert callable(approve_order_owned_v3)
probe = "123456789:test-reseller-bot-key"
encrypted = encrypt_bot_token(probe)
assert encrypted != probe
assert decrypt_bot_token(encrypted) == probe
print("RESELLER_BOT_OWNED_RUNTIME_IMPORT_OK")
print("RESELLER_BOT_CRYPTO_ROUNDTRIP_OK")
PY
)

printf '\n[4/6] Installing systemd service\n'
install -m 0644 "$TEMPLATE" "$TARGET"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

printf '\n[5/6] Starting reseller bot supervisor\n'
systemctl restart "$SERVICE_NAME"
sleep 3
systemctl is-active --quiet "$SERVICE_NAME"

printf '\n[6/6] Final status\n'
systemctl status "$SERVICE_NAME" --no-pager -l

echo
printf 'RESELLER_BOT_SUPERVISOR_READY\n'
