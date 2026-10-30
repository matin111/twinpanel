from __future__ import annotations

import importlib
import inspect


mod = importlib.import_module("app.transport_manager_service_v12")

captured: dict[str, object] = {}


class FakeThread:
    def __init__(self, *, target, name: str, daemon: bool):
        captured["target"] = target
        captured["name"] = name
        captured["daemon"] = daemon

    def start(self) -> None:
        captured["started"] = True


original_thread = mod.threading.Thread
mod.threading.Thread = FakeThread
try:
    result = mod.ensure_transport_manager_service_v12()
finally:
    mod.threading.Thread = original_thread

assert result["ok"] is True
assert result["reason"] == "activation_deferred"
assert captured["started"] is True
assert captured["daemon"] is True
assert captured["name"] == "twinpanel-transport-manager-activation"
assert captured["target"] is mod._ensure_transport_manager_service_v12_blocking

ensure_locked_source = inspect.getsource(mod._ensure_locked)
run_source = inspect.getsource(mod._run)
assert "manager_pid == os.getpid()" in ensure_locked_source
assert '"restart"' in ensure_locked_source
assert '"--no-block"' in ensure_locked_source
assert "timeout=20" in run_source

print("API_STARTUP_TRANSPORT_MANAGER_DEFER_V1_OK")
