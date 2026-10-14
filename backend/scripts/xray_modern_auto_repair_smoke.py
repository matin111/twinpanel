from __future__ import annotations

import asyncio

from app import xray_modern_repair_runtime as runtime
from app import xray_modern_runtime as modern_runtime
from app import xray_modern_temp_config_runtime as temp_runtime


class DummyNode:
    pass


class DummyConn:
    def __init__(self) -> None:
        self.command = ""

    async def run(self, command, *args, **kwargs):
        self.command = str(command)
        return object()


async def main() -> None:
    temp_runtime.apply_xray_modern_temp_config_runtime()

    # Production regression: Xray 26.x must see a candidate path ending in
    # `.json`; otherwise it refuses to infer the config format.
    merged = modern_runtime._merge_clients_script()
    assert temp_runtime.JSON_TEMP_CONFIG in merged
    assert temp_runtime.LEGACY_TEMP_CONFIG not in merged

    dummy = DummyConn()
    proxy = temp_runtime._JsonTempPathConnection(dummy)
    await proxy.run(
        "xray run -test -config "
        + temp_runtime.LEGACY_TEMP_CONFIG
    )
    assert temp_runtime.JSON_TEMP_CONFIG in dummy.command
    assert temp_runtime.LEGACY_TEMP_CONFIG not in dummy.command

    assert (
        modern_runtime._ensure_modern_xray
        is temp_runtime._ensure_modern_xray_json_temp
    )
    assert (
        runtime._ensure_modern_xray
        is temp_runtime._ensure_modern_xray_json_temp
    )

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

    print("XRAY_MODERN_JSON_TEMP_CONFIG_OK")
    print("XRAY_MODERN_AUTO_REPAIR_RETRY_OK")
    print("XRAY_MODERN_HEALTH_PROBE_SAFE_OK")


if __name__ == "__main__":
    asyncio.run(main())
