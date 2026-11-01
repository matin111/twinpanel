from __future__ import annotations

import asyncio
from pathlib import Path

from app.services.asyncssh_close_guard import install_asyncssh_close_guard


ROOT = Path(__file__).resolve().parents[2]


def test_asyncssh_close_guard_returns_after_bounded_teardown_wait() -> None:
    class FakeConnection:
        async def wait_closed(self) -> None:
            await asyncio.Event().wait()

    async def scenario() -> None:
        assert install_asyncssh_close_guard(
            FakeConnection,
            timeout_seconds=0.25,
        ) is True
        assert install_asyncssh_close_guard(
            FakeConnection,
            timeout_seconds=0.25,
        ) is False

        loop = asyncio.get_running_loop()
        started = loop.time()
        await FakeConnection().wait_closed()
        elapsed = loop.time() - started

        assert elapsed >= 0.20
        assert elapsed < 0.75

    asyncio.run(scenario())


def test_fast_create_installs_ssh_close_guard() -> None:
    source = (ROOT / "backend/app/routers/subscription_create_fast_v1.py").read_text(
        encoding="utf-8"
    )

    assert "from ..services.asyncssh_close_guard import install_asyncssh_close_guard" in source
    assert "install_asyncssh_close_guard()" in source


def test_browser_create_request_has_hard_timeout() -> None:
    source = (ROOT / "lib/subscription-create-fast-api.ts").read_text(encoding="utf-8")

    assert "SUBSCRIPTION_CREATE_REQUEST_TIMEOUT_MS=135_000" in source
    assert "new AbortController()" in source
    assert "signal:controller.signal" in source
    assert "controller.signal.aborted" in source
    assert "رابط از حالت انتظار خارج شد" in source
