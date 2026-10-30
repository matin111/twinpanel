from __future__ import annotations

from pathlib import Path


path = Path("app/transport_manager_service_v12.py")
source = path.read_text(encoding="utf-8")
compile(source, str(path), "exec")

assert "import threading" in source
assert "def _ensure_transport_manager_service_v12_blocking()" in source
assert "target=_ensure_transport_manager_service_v12_blocking" in source
assert 'name="twinpanel-transport-manager-activation"' in source
assert "daemon=True" in source
assert '"reason": "activation_deferred"' in source
assert "manager_pid == os.getpid()" in source
assert '"restart"' in source
assert '"--no-block"' in source
assert "timeout=20" in source

print("API_STARTUP_TRANSPORT_MANAGER_DEFER_V1_OK")
