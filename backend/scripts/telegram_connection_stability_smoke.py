from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "app" / "routers" / "telegram_manager.py"
RUNTIME = ROOT / "app" / "telegram_runtime_bot.py"
CUSTOM_RUNTIME = ROOT / "app" / "telegram_runtime_custom.py"

manager = MANAGER.read_text(encoding="utf-8")
runtime = RUNTIME.read_text(encoding="utf-8")
custom_runtime = CUSTOM_RUNTIME.read_text(encoding="utf-8")

service_start = manager.index('return f"""[Unit]')
service_end = manager.index('"""', service_start + len('return f"""[Unit]'))
service = manager[service_start:service_end]

# Telegram polling must not be terminated just because the local API restarts.
assert f"Requires={{API_SERVICE_NAME}}" not in service
assert "After=network-online.target {API_SERVICE_NAME}" in service
assert "Wants=network-online.target" in service

# A repeated transient failure must never leave the service rate-limited/stopped.
assert "StartLimitIntervalSec=0" in service
assert "Restart=always" in service
assert "RestartSec=4" in service

# The managed service must run the text-aware resilient runtime and must not pin
# the internal API to the legacy 8095 port. The installed port is loaded from
# install.env / runtime configuration instead.
assert "EnvironmentFile=-/etc/twinpanel/install.env" in service
assert "TWINPANEL_API_BASE=http://127.0.0.1:8095" not in service
assert "-m app.telegram_runtime_custom" in service
assert 'return PROJECT_DIR / "app/telegram_runtime_custom.py"' in manager

# Runtime resolves the installed API port and retries only transport failures.
assert 'os.getenv("TWINPANEL_API_PORT", "")' in custom_runtime
assert '"TWINPANEL_API_PORT"' in custom_runtime
assert '"TWINPANEL_BACKEND_URL"' in custom_runtime
assert "httpx.NetworkError" in custom_runtime
assert "httpx.TimeoutException" in custom_runtime
assert "httpx.RemoteProtocolError" in custom_runtime
assert "delays = (0.25, 0.5, 1.0, 2.0, 3.0)" in custom_runtime
assert "runtime.request = resilient_request" in custom_runtime

# Existing runtime-level polling and notification worker must remain intact.
assert "await dp.start_polling(bot)" in runtime
assert "notify_task = asyncio.create_task(" in runtime
assert "await bot.delete_webhook(" in runtime

print("TELEGRAM_CONNECTION_STABILITY_SMOKE_OK")
