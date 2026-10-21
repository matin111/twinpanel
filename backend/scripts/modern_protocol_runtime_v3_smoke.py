from __future__ import annotations

import asyncio
from pathlib import Path

from app import modern_protocol_dispatch, singbox_service_runtime
from app.modern_protocol_dispatch import SINGBOX_PROTOCOLS, redacted_preview
from app.protocol_catalog import PROTOCOL_CATALOG, catalog_payload, resolve_settings


STANDALONE = {"mieru", "trusttunnel", "amneziawg", "sudoku"}
EXPECTED_READY = {
    "hysteria2",
    "tuic",
    "anytls",
    "naive",
    "shadowtls",
    "snell",
    *STANDALONE,
}


def _assert_singbox_service_bootstrap() -> None:
    captured: list[tuple[str, int]] = []

    async def fake_cmd(_conn, command: str, *, timeout: int = 30, **_kwargs):
        captured.append((command, timeout))
        return ""

    original = singbox_service_runtime.cmd
    singbox_service_runtime.cmd = fake_cmd
    try:
        result = asyncio.run(singbox_service_runtime.ensure_singbox_service_unit(object()))
    finally:
        singbox_service_runtime.cmd = original

    assert result["service"] == "twinpanel-sing-box"
    assert result["unit"] == "/etc/systemd/system/twinpanel-sing-box.service"
    assert len(captured) == 1
    command, timeout = captured[0]
    assert timeout == 120
    assert "/etc/systemd/system/twinpanel-sing-box.service" in command
    assert "systemctl daemon-reload" in command
    assert "systemctl enable twinpanel-sing-box.service" in command
    assert "systemctl restart" not in command
    assert "systemctl start" not in command
    assert "cmp -s" in command
    assert "mv \"$tmp\" \"$target\"" in command

    unit = singbox_service_runtime.SERVICE_UNIT
    assert "Description=TwinPanel Modern VPN Core (sing-box)" in unit
    assert (
        "ExecStart=/usr/local/bin/twinpanel-sing-box run -c "
        "/etc/twinpanel/sing-box/config.json"
    ) in unit
    assert "Restart=on-failure" in unit


def _assert_singbox_readiness_retry() -> None:
    samples = [False, False, True]
    calls: list[tuple[str, int | None]] = []

    async def fake_health(_conn, protocol: str, port: int | None = None):
        calls.append((protocol, port))
        ok = samples.pop(0)
        return {
            "ok": ok,
            "protocol": protocol,
            "service": "twinpanel-sing-box",
            "service_active": True,
            "listener": ok,
            "port": port,
            "transport": "tcp",
        }

    original = modern_protocol_dispatch._singbox_health
    modern_protocol_dispatch._singbox_health = fake_health
    try:
        result = asyncio.run(
            modern_protocol_dispatch._wait_for_singbox_health(
                object(),
                "anytls",
                8446,
                attempts=5,
                delay_seconds=0,
            )
        )
    finally:
        modern_protocol_dispatch._singbox_health = original

    assert result["ok"] is True
    assert result["listener"] is True
    assert calls == [("anytls", 8446)] * 3

    failures: list[int] = []

    async def always_unhealthy(_conn, protocol: str, port: int | None = None):
        failures.append(1)
        return {
            "ok": False,
            "protocol": protocol,
            "service": "twinpanel-sing-box",
            "service_active": True,
            "listener": False,
            "port": port,
            "transport": "tcp",
        }

    modern_protocol_dispatch._singbox_health = always_unhealthy
    try:
        result = asyncio.run(
            modern_protocol_dispatch._wait_for_singbox_health(
                object(),
                "anytls",
                8446,
                attempts=3,
                delay_seconds=0,
            )
        )
    finally:
        modern_protocol_dispatch._singbox_health = original

    assert result["ok"] is False
    assert len(failures) == 3


def _assert_standalone_readiness_retry() -> None:
    samples = [False, False, True]
    calls: list[tuple[str, int | None]] = []

    async def fake_health(_conn, protocol: str, port: int | None = None):
        calls.append((protocol, port))
        ok = samples.pop(0)
        return {
            "ok": ok,
            "protocol": protocol,
            "service": "twinpanel-sudoku",
            "service_active": True,
            "listener": ok,
            "port": port,
            "transport": "tcp",
        }

    original = modern_protocol_dispatch.standalone_health
    modern_protocol_dispatch.standalone_health = fake_health
    try:
        result = asyncio.run(
            modern_protocol_dispatch._wait_for_standalone_health(
                object(),
                "sudoku",
                8453,
                attempts=5,
                delay_seconds=0,
            )
        )
    finally:
        modern_protocol_dispatch.standalone_health = original

    assert result["ok"] is True
    assert result["listener"] is True
    assert calls == [("sudoku", 8453)] * 3

    failures: list[int] = []

    async def always_unhealthy(_conn, protocol: str, port: int | None = None):
        failures.append(1)
        return {
            "ok": False,
            "protocol": protocol,
            "service": "twinpanel-sudoku",
            "service_active": True,
            "listener": False,
            "port": port,
            "transport": "tcp",
        }

    modern_protocol_dispatch.standalone_health = always_unhealthy
    try:
        result = asyncio.run(
            modern_protocol_dispatch._wait_for_standalone_health(
                object(),
                "sudoku",
                8453,
                attempts=3,
                delay_seconds=0,
            )
        )
    finally:
        modern_protocol_dispatch.standalone_health = original

    assert result["ok"] is False
    assert len(failures) == 3


def main() -> None:
    assert STANDALONE <= SINGBOX_PROTOCOLS
    assert EXPECTED_READY <= SINGBOX_PROTOCOLS

    by_key = {item["key"]: item for item in catalog_payload()}
    for key in EXPECTED_READY:
        assert key in by_key, key
        assert by_key[key]["runtime_status"] == "ready", key
        assert by_key[key]["installable"] is True, key

        preset, settings, _warnings = resolve_settings(key, "recommended", {})
        assert preset == "recommended"
        preview = redacted_preview(
            key,
            int(PROTOCOL_CATALOG[key]["default_port"]),
            settings,
        )
        assert preview["listen_port"] == int(PROTOCOL_CATALOG[key]["default_port"])

    assert PROTOCOL_CATALOG["sudoku"]["transport"] == "tcp"
    assert int(PROTOCOL_CATALOG["mieru"]["default_port"]) == 8450
    assert int(PROTOCOL_CATALOG["trusttunnel"]["default_port"]) == 8451
    assert int(PROTOCOL_CATALOG["amneziawg"]["default_port"]) == 8452
    assert int(PROTOCOL_CATALOG["sudoku"]["default_port"]) == 8453

    root = Path(__file__).resolve().parents[2]
    main_py = (root / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    v3 = "app.include_router(modern_protocol_admin_v3_router)"
    legacy = "app.include_router(vpn_settings_router)"
    assert v3 in main_py
    assert legacy in main_py
    assert main_py.index(v3) < main_py.index(legacy)

    dispatch_py = (root / "backend" / "app" / "modern_protocol_dispatch.py").read_text(
        encoding="utf-8"
    )
    bootstrap_call = "await ensure_singbox_service_unit(conn)"
    apply_call = "singbox = await _apply_singbox_profiles(conn, node, singbox_profiles)"
    readiness_call = "await _wait_for_singbox_health("
    standalone_apply_call = "standalone = await apply_standalone_profile(conn, node, profile)"
    standalone_readiness_call = "await _wait_for_standalone_health("
    assert bootstrap_call in dispatch_py
    assert apply_call in dispatch_py
    assert readiness_call in dispatch_py
    assert standalone_apply_call in dispatch_py
    assert standalone_readiness_call in dispatch_py
    assert dispatch_py.index(bootstrap_call) < dispatch_py.index(apply_call)
    assert dispatch_py.index(apply_call) < dispatch_py.index(readiness_call)
    assert dispatch_py.index(standalone_apply_call) < dispatch_py.index(standalone_readiness_call)

    runtime_py = (root / "backend" / "app" / "standalone_protocol_runtime.py").read_text(
        encoding="utf-8"
    )
    for version in ("3.38.1", "1.1.0", "0.5.1"):
        assert version in runtime_py
    for digest in (
        "2c7c0be33d34cf126187d97c17484a34b5c62b764c96b0a88ec4cbc7660d72c9",
        "91c2ea3db7416a01b5258a4c047ec22890490bc55e1b194206031aa75144f0e7",
        "a9ebfb7e359d7f667062400a098e117e4e2bed55c65aea099e949129953028d0",
    ):
        assert digest in runtime_py

    _assert_singbox_service_bootstrap()
    _assert_singbox_readiness_retry()
    _assert_standalone_readiness_retry()

    print("MODERN_PROTOCOL_RUNTIME_V3_SMOKE_OK")


if __name__ == "__main__":
    main()
