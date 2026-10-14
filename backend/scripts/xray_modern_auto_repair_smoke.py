from __future__ import annotations

import asyncio

from app import xray_modern_repair_runtime as runtime


class DummyNode:
    pass


async def main() -> None:
    original_ensure = runtime._ensure_modern_xray
    calls = 0

    async def flaky_ensure(
        conn,
        base_port,
        node,
        *,
        bootstrap_done=False,
    ):
        nonlocal calls
        calls += 1
        assert base_port == 2056
        assert bootstrap_done is True
        if calls == 1:
            raise RuntimeError("transient first-attempt failure")
        return {"ok": True}

    runtime._ensure_modern_xray = flaky_ensure

    try:
        ok, error = await runtime._ensure_with_retry(
            None,
            2056,
            DummyNode(),
            bootstrap_done=True,
            attempts=2,
        )
    finally:
        runtime._ensure_modern_xray = original_ensure

    assert ok is True
    assert error is None
    assert calls == 2

    probe = runtime._health_probe_script(2056)

    for expected in (
        '"legacy": base_port',
        '"xhttp_reality": base_port + 1',
        '"grpc_reality": base_port + 2',
        '"websocket_tls": base_port + 3',
        '"httpupgrade_tls": base_port + 4',
        '"reality_private_key_present"',
        '"reality_public_key_present"',
        '"missing": missing',
    ):
        assert expected in probe, expected

    assert "print(state)" not in probe
    assert "reality_private_key\": state.get" not in probe
    assert "reality_password\": state.get" not in probe

    print("XRAY_MODERN_AUTO_REPAIR_RETRY_OK")
    print("XRAY_MODERN_HEALTH_PROBE_SAFE_OK")


if __name__ == "__main__":
    asyncio.run(main())
