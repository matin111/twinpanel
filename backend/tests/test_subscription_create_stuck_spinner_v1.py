from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_PATH = ROOT / "backend/app/services/hard_async_timeout.py"


def _load_timeout_module():
    spec = importlib.util.spec_from_file_location(
        "twinpanel_hard_async_timeout_test",
        TIMEOUT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_hard_timeout_returns_even_when_cancel_cleanup_stalls() -> None:
    await_hard_timeout = _load_timeout_module().await_hard_timeout

    async def operation() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.Event().wait()

    async def scenario() -> None:
        loop = asyncio.get_running_loop()
        started = loop.time()
        try:
            await await_hard_timeout(
                operation(),
                timeout_seconds=0.20,
                cancel_grace_seconds=0.10,
            )
        except asyncio.TimeoutError:
            pass
        else:
            raise AssertionError("hard timeout did not raise")

        elapsed = loop.time() - started
        assert elapsed >= 0.25
        assert elapsed < 0.80

    asyncio.run(scenario())


def test_subscription_provisioning_uses_scoped_hard_timeout() -> None:
    source = (ROOT / "backend/app/routers/modern_account_delivery_v1.py").read_text(
        encoding="utf-8"
    )

    assert "from ..services.hard_async_timeout import await_hard_timeout" in source
    assert source.count("await await_hard_timeout(") >= 2
    assert "timeout_seconds=timeout" in source
    assert "timeout_seconds=QUOTA_SYNC_TIMEOUT_SECONDS" in source
    assert "TOTAL_PROVISION_TIMEOUT_SECONDS" not in source


def test_browser_create_request_returns_on_backend_acceptance() -> None:
    client = (ROOT / "lib/subscription-create-fast-api.ts").read_text(encoding="utf-8")
    endpoint = (ROOT / "backend/app/routers/subscription_create_fast_v1.py").read_text(
        encoding="utf-8"
    )

    assert "SUBSCRIPTION_CREATE_REQUEST_TIMEOUT_MS=135_000" not in client
    assert "new AbortController()" not in client
    assert "signal:controller.signal" not in client
    assert '@router.post("/admin-create-fast-v1", status_code=202)' in endpoint
    assert "background_tasks.add_task(" in endpoint
    assert '"queued": True' in endpoint
    assert '"provisioning_complete": False' in endpoint
