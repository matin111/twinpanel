from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.protocol_adapter_registry import (  # noqa: E402
    CLASSIC_ADAPTER,
    CLASSIC_PROTOCOL_KEYS,
    CLASSIC_PROTOCOL_REGISTRY,
    REGISTRY_SCHEMA_VERSION,
    unified_registry_payload,
)
from app.protocol_catalog import PROTOCOL_CATALOG  # noqa: E402


EXPECTED_CLASSIC = {"cisco", "openvpn", "wireguard", "l2tp", "v2ray"}


def main() -> None:
    assert REGISTRY_SCHEMA_VERSION == 1
    assert set(CLASSIC_PROTOCOL_KEYS) == EXPECTED_CLASSIC
    assert set(CLASSIC_PROTOCOL_REGISTRY) == EXPECTED_CLASSIC

    for protocol in CLASSIC_PROTOCOL_KEYS:
        definition = CLASSIC_PROTOCOL_REGISTRY[protocol]
        capabilities = definition["capabilities"]

        assert definition["kind"] == "classic"
        assert definition["adapter"] == CLASSIC_ADAPTER
        assert definition["runtime_status"] == "ready"

        for action in ("install", "health", "restart", "repair"):
            assert capabilities[action] is True, (protocol, action)

        assert capabilities["disable"] is False, protocol
        assert capabilities["uninstall"] is False, protocol

        editable = {field["key"] for field in definition["fields"]}
        managed = set(definition["managed_not_editable"])
        assert not editable.intersection(managed), protocol

        for preset_name in ("recommended", "performance", "compatibility"):
            preset = definition["presets"][preset_name]
            assert set(preset).issubset(editable), (protocol, preset_name, preset)

    assert CLASSIC_PROTOCOL_REGISTRY["l2tp"]["capabilities"]["update_config"] is False
    assert CLASSIC_PROTOCOL_REGISTRY["l2tp"]["fields"] == []
    assert CLASSIC_PROTOCOL_REGISTRY["openvpn"]["presets"]["compatibility"]["transport"] == "tcp"
    assert CLASSIC_PROTOCOL_REGISTRY["v2ray"]["capabilities"]["domain_tls"] is True

    registry = unified_registry_payload()
    assert registry["ok"] is True
    rows = registry["protocols"]
    classic_rows = {row["key"]: row for row in rows if row["kind"] == "classic"}
    modern_rows = {row["key"]: row for row in rows if row["kind"] == "modern"}

    assert set(classic_rows) == EXPECTED_CLASSIC
    assert set(modern_rows) == set(PROTOCOL_CATALOG)

    for protocol, source in PROTOCOL_CATALOG.items():
        capabilities = modern_rows[protocol]["capabilities"]
        ready = source["runtime_status"] == "ready"
        assert capabilities["install"] is ready, protocol
        assert capabilities["health"] is ready, protocol
        assert capabilities["uninstall"] is ready, protocol

    router = (ROOT / "backend/app/routers/classic_protocol_admin_v1.py").read_text(encoding="utf-8")
    assert "from ..protocol_adapter_registry import (" in router
    assert '@router.get("/protocol-registry")' in router
    assert 'preset: ClassicPreset = "custom"' in router
    assert "provision_protocols(" in router
    assert "repair=True" in router
    assert '@router.delete(' not in router
    assert '"uninstall": True' not in router

    modern_router = (ROOT / "backend/app/routers/modern_protocol_admin_v2.py").read_text(encoding="utf-8")
    for route in (
        '@router.get("/modern-protocols")',
        '@router.post("/modern-protocols/{node_id}/preview")',
        '@router.post("/modern-protocols/{node_id}/install")',
        '@router.post("/modern-protocols/{node_id}/health")',
        '@router.delete("/modern-protocols/{node_id}/{protocol}")',
    ):
        assert route in modern_router, route

    command_center = (ROOT / "components/protocol-command-center.tsx").read_text(encoding="utf-8")
    assert "legacyAdminApi.classicProtocols()" in command_center
    assert '"/v1/settings/vpn/modern-protocols"' in command_center

    print("UNIFIED_PROTOCOL_ADAPTER_REGISTRY_V1_OK")
    print("classic=", ",".join(CLASSIC_PROTOCOL_KEYS))
    print("modern=", ",".join(sorted(PROTOCOL_CATALOG)))
    print("classic_destructive_actions=fail_closed")


if __name__ == "__main__":
    main()
