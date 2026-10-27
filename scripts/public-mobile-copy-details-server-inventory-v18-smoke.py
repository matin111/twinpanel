from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V11 = ROOT / "backend/app/routers/public_connection_device_actions_v11.py"
V18 = ROOT / "backend/app/routers/public_connection_mobile_server_inventory_v18.py"
V19 = ROOT / "backend/app/routers/public_connection_mobile_live_v19.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    v11 = V11.read_text(encoding="utf-8")
    v18 = V18.read_text(encoding="utf-8")
    v19 = V19.read_text(encoding="utf-8")

    require("public_connection_mobile_server_inventory_v18" in v11, "V11 does not import V18")
    require("public_connection_mobile_live_v19" in v11, "V11 does not import V19")
    require("refine_public_connection_mobile_protocols_v17(source)" in v11, "V17 chain missing")
    require("refine_public_connection_mobile_server_inventory_v18(source)" in v11, "V18 chain missing")
    require("refine_public_connection_mobile_live_v19(source)" in v11, "V19 chain missing")

    require("mobile-server-inventory-v18" in v18, "read-only inventory endpoint missing")
    require("Node.node_type == NodeType.EXIT" in v18, "inventory must be Exit-only")
    require("Node.retired_at.is_(None)" in v18, "retired nodes must not be exposed")
    require("ready_node_ids" in v18 and "node_status" in v18, "truthful readiness fields missing")
    require('"password"' not in v18 and '"username"' not in v18, "inventory must not expose secrets")

    require("[data-tp-copy-target]" in v18, "Modern canonical copy target missing")
    require(".copy-btn[data-copy]" in v18, "URI copy source missing")
    require(".download-config[data-target]" in v18, "classic file copy source missing")
    require("document.execCommand('copy')" in v18, "HTTP/IP clipboard fallback missing")
    require("کپی کانفیگ" in v18, "copy config action missing")
    require("کپی اطلاعات" in v18, "manual credential copy action missing")

    require("row.appendChild(detail)" in v18, "details are not attached to the row DOM")
    require("row.classList.toggle('show-details')" in v18, "details toggle missing")
    require("جزئیات" in v18, "details action missing")

    require("appendMissingModernServers" in v18, "all-Exit Modern inventory rendering missing")
    require("v18-not-ready" in v18, "not-ready server row state missing")
    require("آماده از" in v18, "ready/total server count missing")
    require("کانفیگ این سرور هنوز آماده نشده" in v18, "online-without-config state missing")
    require("پروتکل روی این سرور هنوز آماده نشده" in v18, "missing-runtime state missing")

    require("v19-live-online" in v19, "mobile live-online visual state missing")
    require("classList.contains('live-online')" in v19, "canonical live state is not consumed")
    require("MutationObserver(syncLiveState)" in v19, "mobile live state observer missing")
    require("آنلاین · آماده اتصال" in v19, "mobile online label missing")
    require("attributeFilter:['class']" in v19, "live sync must observe canonical class changes")
    require(".protocol-choice[data-protocol-key]" in v19, "canonical protocol cards must remain live authority")
    require(".v17-protocol-card[data-protocol-key]" in v19, "mobile cards must be keyed for live mirror")

    require("@media(max-width:720px)" in v18, "V18 visual changes must stay mobile-scoped")
    require("@media(max-width:720px)" in v19, "V19 visual changes must stay mobile-scoped")
    require("TWINPANEL_PUBLIC_CONNECT_MOBILE_SERVER_INVENTORY_V18" in v18, "V18 marker missing")
    require("TWINPANEL_PUBLIC_CONNECT_MOBILE_LIVE_V19" in v19, "V19 marker missing")

    print("PUBLIC_MOBILE_COPY_DETAILS_SERVER_INVENTORY_V18=PASS")
    print("PUBLIC_MOBILE_LIVE_V19=PASS")


if __name__ == "__main__":
    main()
