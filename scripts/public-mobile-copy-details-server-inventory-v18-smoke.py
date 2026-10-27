from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V11 = ROOT / "backend/app/routers/public_connection_device_actions_v11.py"
V18 = ROOT / "backend/app/routers/public_connection_mobile_server_inventory_v18.py"
V24 = ROOT / "backend/app/routers/public_connection_canonical_presentation_v24.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    v11 = V11.read_text(encoding="utf-8")
    v18 = V18.read_text(encoding="utf-8")
    v24 = V24.read_text(encoding="utf-8")

    require("public_connection_canonical_presentation_v24" in v11, "V24 authority missing")
    require("refine_public_connection_canonical_presentation_v24(source)" in v11, "V24 chain missing")
    require("public_connection_mobile_server_inventory_v18" not in v11, "retired V18 re-entered V11")
    require("refine_public_connection_mobile_server_inventory_v18" not in v11, "retired V18 is still executed")

    # Legacy V18 remains read-only and secret-free for rollback/history.
    require("mobile-server-inventory-v18" in v18, "legacy V18 endpoint missing")
    require("Node.node_type == NodeType.EXIT" in v18, "legacy inventory must remain Exit-only")
    require("Node.retired_at.is_(None)" in v18, "legacy inventory retired-node guard missing")
    require('"password"' not in v18 and '"username"' not in v18, "legacy inventory must not expose secrets")

    # V24 explicitly forbids the mobile-only inventory/rebuild pattern.
    require("mobile-server-inventory-v18" not in v24, "V24 must not use mobile inventory")
    require("appendMissingModernServers" not in v24, "V24 must not append synthetic servers")
    require("v18-not-ready" not in v24, "V24 must not expose placeholder server rows")
    require("آماده‌سازی" not in v24, "V24 must not expose provisioning placeholders")
    require("fetch(" not in v24, "V24 must not fetch device-specific server data")
    require("JSON.parse" not in v24, "V24 must not parse configs")
    require(".protocol-panel" in v24 and ".server-view" in v24, "V24 canonical DOM authority missing")
    require("classList.contains('live-online')" in v24, "V24 must mirror canonical live state")
    require("MutationObserver" in v24, "V24 live-state observer missing")
    require("@media(max-width:720px)" in v24, "V24 visual changes must stay mobile-scoped")

    print("PUBLIC_MOBILE_SERVER_INVENTORY_V18_LEGACY=PASS")
    print("PUBLIC_CANONICAL_PRESENTATION_V24_NO_SECOND_DATA_PATH=PASS")


if __name__ == "__main__":
    main()
