from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.services.hard_async_timeout import await_hard_timeout


ROOT = Path(__file__).resolve().parents[1]


def test_wait_for_cancel_drains_cleanup_before_timeout_returns() -> None:
    events: list[str] = []

    async def operation() -> None:
        try:
            await asyncio.sleep(60)
        finally:
            await asyncio.sleep(0.01)
            events.append("cleanup")

    async def scenario() -> None:
        with pytest.raises(asyncio.TimeoutError):
            await await_hard_timeout(
                operation(),
                timeout_seconds=0.01,
                cancel_grace_seconds=0,
                wait_for_cancel=True,
            )
        assert events == ["cleanup"]

    asyncio.run(scenario())


def test_account_delivery_uses_session_safe_per_node_timeouts() -> None:
    source = (ROOT / "app/routers/modern_account_delivery_v1.py").read_text()

    assert source.count("wait_for_cancel=True") >= 3
    assert "Provisioning timeout on this server after" in source
    assert '"node": "provisioning"' not in source


def test_reseller_order_has_no_global_120_second_provision_timeout() -> None:
    source = (ROOT / "app/routers/reseller_bot_orders_owned_v3.py").read_text()

    assert "RESELLER_ORDER_PROVISION_TIMEOUT_SECONDS" not in source
    assert "await_hard_timeout" not in source
    assert "provision = await legacy.provision_account(" in source
