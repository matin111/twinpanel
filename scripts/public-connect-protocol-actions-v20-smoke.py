from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V11 = ROOT / "backend/app/routers/public_connection_device_actions_v11.py"
V13 = ROOT / "backend/app/routers/public_connection_modern_delivery_v13.py"
V20 = ROOT / "backend/app/routers/public_connection_protocol_actions_v20.py"
V21 = ROOT / "backend/app/routers/public_connection_protocol_uri_details_v21.py"
V23 = ROOT / "backend/app/routers/public_connection_device_data_authority_v23.py"
V24 = ROOT / "backend/app/routers/public_connection_canonical_presentation_v24.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_legacy_v23():
    spec = importlib.util.spec_from_file_location("public_connection_device_data_authority_v23", V23)
    require(spec is not None and spec.loader is not None, "legacy V23 import spec missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    v11 = V11.read_text(encoding="utf-8")
    v13 = V13.read_text(encoding="utf-8")
    v20 = V20.read_text(encoding="utf-8")
    v21 = V21.read_text(encoding="utf-8")
    v23 = V23.read_text(encoding="utf-8")
    v24 = V24.read_text(encoding="utf-8")
    legacy_authority = load_legacy_v23()

    # V24 is the sole active device presentation adapter.
    require("public_connection_canonical_presentation_v24" in v11, "V24 import missing")
    require("refine_public_connection_canonical_presentation_v24(source)" in v11, "V24 chain missing")
    for retired in (
        "public_connection_mobile_protocols_v17",
        "refine_public_connection_mobile_protocols_v17",
        "public_connection_mobile_server_inventory_v18",
        "refine_public_connection_mobile_server_inventory_v18",
        "public_connection_protocol_actions_v20",
        "refine_public_connection_protocol_actions_v20",
        "public_connection_protocol_uri_details_v21",
        "refine_public_connection_protocol_uri_details_v21",
        "public_connection_protocol_action_authority_v22",
        "refine_public_connection_protocol_action_authority_v22",
        "public_connection_device_data_authority_v23",
        "refine_public_connection_device_data_authority_v23",
    ):
        require(retired not in v11, f"retired device-specific data mutation re-entered V11: {retired}")

    # Legacy modules remain testable for rollback/history, but they are not active.
    require("document.querySelectorAll('.v18-not-ready').forEach(row=>row.remove())" in v20, "legacy fake-server cleanup missing")
    require("key==='cisco'||key==='l2tp'" in v20, "legacy Cisco/L2TP manual policy missing")
    require("stripInvalidClassicDownloads" in v20, "legacy invalid classic config cleanup missing")
    require("new URL(String(raw||''))" in v21, "legacy URI parser missing")
    require("TWINPANEL_PUBLIC_CONNECT_DEVICE_DATA_AUTHORITY_V23" in v23, "legacy V23 marker missing")

    # Preserve the useful pure semantic regression helper from legacy V23.
    require(legacy_authority.canonical_role("Server & Port") == "endpoint", "Server & Port semantic role broken")
    projection = legacy_authority.canonical_manual_projection(
        [
            ("Server & Port", "193.39.9.222:20005"),
            ("Username", "example-user"),
            ("Password", "example-pass"),
        ],
        "cisco",
    )
    require(projection["valid"] is True, "legacy canonical manual projection broken")
    require(projection["endpoint"] == "193.39.9.222:20005", "legacy endpoint projection duplicated or rewritten")

    # Active V24 reuses the canonical HTML/DOM and does not reconstruct data/actions.
    require(".protocol-panel" in v24 and ".server-view" in v24, "V24 canonical DOM authority missing")
    require(".server-tab" in v24, "V24 canonical server labels missing")
    for forbidden in (
        "fetch(",
        "JSON.parse",
        "mobile-server-inventory-v18",
        "appendMissingModernServers",
        "actions.replaceChildren",
        "createElement('button')",
        'createElement("button")',
        "createElement('a')",
        'createElement("a")',
    ):
        require(forbidden not in v24, f"V24 reconstructed device-specific data/action path: {forbidden}")

    # Device detection selects apps/UI only. Canonical connection facts do not branch by platform.
    for platform in ("windows", "macos", "android", "ios", "linux"):
        require(f"'{platform}'" in v11 or f"{platform}:" in v11, f"device detection missing: {platform}")
    require("sourceAppLinks" in v11 and "platform-group[data-platform=" in v11, "global platform app filtering missing")
    require("data-v13-platform" in v24 and "data-tp-platform" in v24, "protocol app presentation filter missing")
    require('"cisco": {' in v13, "Cisco app recommendations missing")
    require('"android": ("OpenConnect"' in v13, "Cisco Android app recommendation missing")
    require('"ios": ("Cisco Secure Client"' in v13, "Cisco iOS app recommendation missing")
    require('"openvpn": {p: ("OpenVPN Connect"' in v13, "OpenVPN client recommendation missing")
    require('"wireguard": {p: ("WireGuard"' in v13, "WireGuard client recommendation missing")

    # Canonical live state is mirrored visually without a second poller/API.
    require("classList.contains('live-online')" in v24, "canonical live-online state not consumed")
    require("MutationObserver" in v24, "canonical live state observer missing")

    # Readability belongs to V24 presentation; reject historical 6-9px mobile text.
    require("font-size:12px!important" in v24, "V24 readable fact/action text missing")
    require("font-size:13px" in v24, "V24 readable server text missing")
    require("font-size:16px!important" in v24, "V24 readable protocol title missing")
    for tiny in ("font-size:6px", "font-size:6.5px", "font-size:7px", "font-size:8px", "font-size:9px"):
        require(tiny not in v24, f"tiny V24 mobile scale reintroduced: {tiny}")

    print("PUBLIC_CONNECT_V20_V21_V23_LEGACY=PASS")
    print("PUBLIC_CONNECT_CANONICAL_PRESENTATION_V24=PASS")
    print("DEVICE_NEUTRAL_CONNECTION_DATA=PASS")


if __name__ == "__main__":
    main()
