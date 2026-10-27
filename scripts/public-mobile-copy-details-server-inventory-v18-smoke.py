from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V11 = ROOT / "backend/app/routers/public_connection_device_actions_v11.py"
V18 = ROOT / "backend/app/routers/public_connection_mobile_server_inventory_v18.py"
V23 = ROOT / "backend/app/routers/public_connection_device_presentation_v23.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    v11 = V11.read_text(encoding="utf-8")
    v18 = V18.read_text(encoding="utf-8")
    v23 = V23.read_text(encoding="utf-8")

    # V18 stays in source for rollback/history, but must not be part of the active V11 render chain.
    require("public_connection_device_presentation_v23" in v11, "V23 authority missing")
    require("refine_public_connection_device_presentation_v23(source)" in v11, "V23 chain missing")
    require("public_connection_mobile_server_inventory_v18" not in v11, "retired V18 re-entered V11")
    require("refine_public_connection_mobile_server_inventory_v18" not in v11, "retired V18 is still executed")

    # Legacy endpoint remains read-only and secret-free for compatibility/rollback.
    require("mobile-server-inventory-v18" in v18, "legacy V18 endpoint missing")
    require("Node.node_type == NodeType.EXIT" in v18, "legacy inventory must remain Exit-only")
    require("Node.retired_at.is_(None)" in v18, "legacy inventory retired-node guard missing")
    require('"password"' not in v18 and '"username"' not in v18, "legacy inventory must not expose secrets")

    # V23 must never reproduce the mobile-only inventory/rebuild behavior.
    require("mobile-server-inventory-v18" not in v23, "V23 must not use mobile inventory")
    require("appendMissingModernServers" not in v23, "V23 must not append synthetic server rows")
    require("v18-not-ready" not in v23, "V23 must not expose placeholder server rows")
    require("آماده‌سازی" not in v23, "V23 must not expose provisioning placeholders")
    require("fetch(" not in v23, "V23 must not fetch device-specific server data")
    require("JSON.parse" not in v23, "V23 must not parse configs")
    require(".protocol-panel" in v23 and ".server-view" in v23, "V23 canonical DOM authority missing")
    require("classList.contains('live-online')" in v23, "V23 must mirror canonical live state")
    require("MutationObserver" in v23, "V23 live-state mirror observer missing")
    require("@media(max-width:720px)" in v23, "V23 visual changes must remain mobile-scoped")

    print("PUBLIC_MOBILE_SERVER_INVENTORY_V18_LEGACY=PASS")
    print("PUBLIC_DEVICE_PRESENTATION_V23_NO_SECOND_DATA_PATH=PASS")


if __name__ == "__main__":
    main()
