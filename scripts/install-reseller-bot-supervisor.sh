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

[[ -d "$SOURCE_DIR/backend" ]] || {
  echo "source backend directory not found: $SOURCE_DIR/backend" >&2
  exit 1
}

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

[[ -f "$SOURCE_DIR/backend/requirements.txt" ]] || {
  echo "source requirements not found: $SOURCE_DIR/backend/requirements.txt" >&2
  exit 1
}

[[ -f "$TEMPLATE" ]] || {
  echo "service template not found: $TEMPLATE" >&2
  exit 1
}

# Keep the bot supervisor deploy self-contained. These are the runtime modules
# imported by the owned-plan bot flow plus the shared-pool guard/enforcement
# chain used by renewals and account provisioning.
BOT_RUNTIME_FILES=(
  "app/reseller_bot_runtime.py"
  "app/reseller_bot_runtime_owned.py"
  "app/reseller_bot_owned_runtime.py"
  "app/reseller_bot_review.py"
  "app/reseller_bot_crypto.py"
  "app/reseller_bot_order_models.py"
  "app/reseller_owned_plan_models.py"
  "app/reseller_owned_plans.py"
  "app/reseller_pool_models.py"
  "app/mother_access.py"
  "app/subscription_enforcement.py"
  "app/services/subscription_factory.py"
  "app/services/reseller_traffic_pool.py"
  "app/services/quota_refresh.py"
  "app/services/quota_node_sync.py"
  "app/services/quota_key_manager.py"
  "app/routers/reseller_bot.py"
  "app/routers/reseller_bot_orders.py"
  "app/routers/reseller_bot_orders_volume_v2.py"
  "app/routers/reseller_bot_orders_owned_v3.py"
  "app/routers/reseller_subscription_volume_v2.py"
  "app/routers/reseller_pool_guard_v3.py"
)

for rel in "${BOT_RUNTIME_FILES[@]}"; do
  [[ -f "$SOURCE_DIR/backend/$rel" ]] || {
    echo "required reseller bot source missing: $SOURCE_DIR/backend/$rel" >&2
    exit 1
  }
done

printf '\n[1/8] Syncing reseller bot runtime bundle\n'
install -m 0644 "$SOURCE_DIR/backend/requirements.txt" "$BACKEND_DIR/requirements.txt"
for rel in "${BOT_RUNTIME_FILES[@]}"; do
  install -D -m 0644 "$SOURCE_DIR/backend/$rel" "$BACKEND_DIR/$rel"
done
printf 'RESELLER_BOT_RUNTIME_SYNC_OK\n'

for runtime_file in \
  "$BACKEND_DIR/app/reseller_bot_runtime.py" \
  "$BACKEND_DIR/app/reseller_bot_runtime_owned.py" \
  "$BACKEND_DIR/app/reseller_bot_owned_runtime.py" \
  "$BACKEND_DIR/app/routers/reseller_pool_guard_v3.py" \
  "$BACKEND_DIR/app/routers/reseller_subscription_volume_v2.py"; do
  [[ -f "$runtime_file" ]] || {
    echo "reseller bot runtime not found after sync: $runtime_file" >&2
    exit 1
  }
done

printf '\n[2/8] Installing backend dependencies\n'
"$VENV_DIR/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"

printf '\n[3/8] Compiling synced reseller runtime bundle\n'
COMPILE_FILES=()
for rel in "${BOT_RUNTIME_FILES[@]}"; do
  [[ "$rel" == *.py ]] && COMPILE_FILES+=("$BACKEND_DIR/$rel")
done
"$VENV_DIR/bin/python" -m py_compile "${COMPILE_FILES[@]}"
printf 'RESELLER_BOT_RUNTIME_COMPILE_OK\n'

printf '\n[4/8] Ensuring reseller bot encryption key\n'
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

printf '\n[5/8] Verifying reseller bot runtime import\n'
(
  cd "$BACKEND_DIR"
  PYTHONPATH="$BACKEND_DIR" "$VENV_DIR/bin/python" - <<'PY'
from app.reseller_bot_runtime import supervisor
from app.reseller_bot_runtime_owned import build_router, install_runtime_overrides
from app.reseller_bot_owned_runtime import build_owned_plan_router
from app.reseller_bot_review import register_reseller_review_handlers
from app.routers.reseller_bot_orders_owned_v3 import approve_order_owned_v3
from app.routers.reseller_pool_guard_v3 import extend_subscription_pool_guard
from app.reseller_bot_crypto import encrypt_bot_token, decrypt_bot_token

assert callable(build_router)
assert callable(build_owned_plan_router)
assert callable(install_runtime_overrides)
assert callable(supervisor)
assert callable(register_reseller_review_handlers)
assert callable(approve_order_owned_v3)
assert callable(extend_subscription_pool_guard)
probe = "123456789:test-reseller-bot-key"
encrypted = encrypt_bot_token(probe)
assert encrypted != probe
assert decrypt_bot_token(encrypted) == probe
print("RESELLER_BOT_OWNED_RUNTIME_IMPORT_OK")
print("RESELLER_BOT_CRYPTO_ROUNDTRIP_OK")
PY
)

printf '\n[6/8] Installing systemd service\n'
install -m 0644 "$TEMPLATE" "$TARGET"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

printf '\n[7/8] Starting reseller bot supervisor\n'
systemctl restart "$SERVICE_NAME"
sleep 3
systemctl is-active --quiet "$SERVICE_NAME"

printf '\n[8/8] Final status\n'
SYSTEMD_PAGER=cat systemctl status "$SERVICE_NAME" --no-pager -l

echo
printf 'RESELLER_BOT_SUPERVISOR_READY\n'
