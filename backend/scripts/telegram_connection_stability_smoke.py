from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "app" / "routers" / "telegram_manager.py"
RUNTIME = ROOT / "app" / "telegram_runtime_bot.py"

manager = MANAGER.read_text(encoding="utf-8")
runtime = RUNTIME.read_text(encoding="utf-8")

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

# Existing runtime-level polling and notification worker must remain intact.
assert "await dp.start_polling(bot)" in runtime
assert "notify_task = asyncio.create_task(" in runtime
assert "await bot.delete_webhook(" in runtime

print("TELEGRAM_CONNECTION_STABILITY_SMOKE_OK")
