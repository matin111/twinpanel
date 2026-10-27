from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V11 = ROOT / "backend/app/routers/public_connection_device_actions_v11.py"
V13 = ROOT / "backend/app/routers/public_connection_modern_delivery_v13.py"
V20 = ROOT / "backend/app/routers/public_connection_protocol_actions_v20.py"
V21 = ROOT / "backend/app/routers/public_connection_protocol_uri_details_v21.py"
V23 = ROOT / "backend/app/routers/public_connection_device_data_authority_v23.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_v23():
    spec = importlib.util.spec_from_file_location("public_connection_device_data_authority_v23", V23)
    require(spec is not None and spec.loader is not None, "V23 import spec missing")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> None:
    v11 = V11.read_text(encoding="utf-8")
    v13 = V13.read_text(encoding="utf-8")
    v20 = V20.read_text(encoding="utf-8")
    v21 = V21.read_text(encoding="utf-8")
    v23 = V23.read_text(encoding="utf-8")
    authority = load_v23()

    require("public_connection_protocol_actions_v20" in v11, "V20 import missing")
    require("refine_public_connection_protocol_actions_v20(source)" in v11, "V20 chain missing")
    require("public_connection_protocol_uri_details_v21" in v11, "V21 import missing")
    require("refine_public_connection_protocol_uri_details_v21(source)" in v11, "V21 chain missing")
    require("public_connection_device_data_authority_v23" in v11, "V23 import missing")
    require("refine_public_connection_device_data_authority_v23(source)" in v11, "V23 chain missing")
    require("public_connection_protocol_action_authority_v22" not in v11, "legacy V22 authority must not stay in execution chain")

    # Never expose fake public server rows or internal pending provisioning cards.
    require("document.querySelectorAll('.v18-not-ready').forEach(row=>row.remove())" in v20, "fake server cleanup missing")
    require("protocol-choice.v13-pending" in v20 and "tp-v20-hidden-pending" in v20, "pending protocol cleanup missing")
    require("realRows.length+' سرور'" in v20, "real server count missing")

    # Manual protocols stay manual; no invented downloadable files.
    require("key==='cisco'||key==='l2tp'" in v20, "Cisco/L2TP manual policy missing")
    require("کپی اطلاعات" in v20, "manual connection copy missing")
    require("stripInvalidClassicDownloads" in v20, "invalid classic config cleanup missing")

    # V23 is the final device-data authority and must remain device-neutral.
    require("TWINPANEL_PUBLIC_CONNECT_DEVICE_DATA_AUTHORITY_V23" in v23, "V23 marker missing")
    require("MutationObserver" in v23 and "reconnectObserver" in v23, "V23 rebuild observer missing")
    require("actions.replaceChildren()" in v23, "V23 action dedupe missing")
    require("row.appendChild(detail)" in v23, "V23 detail DOM attachment missing")
    require("key==='cisco'||key==='l2tp'" in v23, "V23 manual protocol authority missing")
    require("v23-manual-invalid" in v23, "invalid manual server suppression missing")
    require("کپی اطلاعات" in v23 and "جزئیات" in v23, "manual actions missing")
    require("کپی کانفیگ" in v23, "config protocols copy action missing")
    require("دانلود کانفیگ" in v23, "file protocol download action missing")
    require("tpPlatform" not in v23 and "navigator.userAgent" not in v23, "connection-data authority must not branch by device")

    # Server rows bind to the canonical source view by stable source id/name, not array index.
    require("data-source-view-id" in v23, "stable source-view binding missing")
    require(".server-tab[data-server]" in v23, "canonical server-tab source mapping missing")
    require("rowName(row)" in v23, "server identity mapping missing")
    require("views[index]" not in v23, "positional source-view mapping reintroduced")

    # Exact field roles are mutually exclusive. Never infer Server and Port from the same label.
    require('"server & port": "endpoint"' in v23, "composite Cisco endpoint role missing")
    require("t.includes('port')" not in v23 and 't.includes("port")' not in v23, "fuzzy port matching reintroduced")
    require(authority.canonical_role("Server & Port") == "endpoint", "Server & Port must be one endpoint fact")
    require(authority.canonical_role("Server") == "server", "Server role broken")
    require(authority.canonical_role("Port") == "port", "Port role broken")

    cisco = authority.canonical_manual_projection(
        [
            ("Server & Port", "193.39.9.222:20005"),
            ("Username", "example-user"),
            ("Password", "example-pass"),
        ],
        "cisco",
    )
    require(cisco["valid"] is True, "Cisco canonical facts should be valid")
    require(cisco["endpoint"] == "193.39.9.222:20005", "Cisco endpoint was rewritten or duplicated")
    cisco_rows = cisco["rows"]
    require(isinstance(cisco_rows, list), "Cisco rows missing")
    require(sum(1 for row in cisco_rows if row["label"] == "Server & Port") == 1, "Cisco endpoint fact duplicated")
    require(all(row["value"] != "193.39.9.222:20005:193.39.9.222:20005" for row in cisco_rows), "duplicated Cisco endpoint regression")

    separate = authority.canonical_manual_projection(
        [
            ("Server", "vpn.example.test"),
            ("Port", "443"),
            ("Username", "example-user"),
            ("Password", "example-pass"),
        ],
        "cisco",
    )
    require(separate["endpoint"] == "vpn.example.test:443", "separate Server + Port projection broken")

    already_joined = authority.canonical_manual_projection(
        [
            ("Server", "vpn.example.test:443"),
            ("Port", "443"),
            ("Username", "example-user"),
            ("Password", "example-pass"),
        ],
        "cisco",
    )
    require(already_joined["endpoint"] == "vpn.example.test:443", "endpoint port was appended twice")

    l2tp = authority.canonical_manual_projection(
        [
            ("Server", "203.0.113.10"),
            ("Username", "example-user"),
            ("Password", "example-pass"),
            ("PSK", "example-psk"),
        ],
        "l2tp",
    )
    require(l2tp["valid"] is True and l2tp["endpoint"] == "203.0.113.10", "L2TP projection broken")
    require(sum(1 for row in l2tp["rows"] if row["role"] == "secret") == 1, "L2TP PSK missing or duplicated")

    # Device detection may only select UI/apps. Connection facts live in V23 and are platform-independent.
    for platform in ("windows", "macos", "android", "ios", "linux"):
        require(f"{platform}:" in v11 or f"'{platform}'" in v11, f"device detection missing: {platform}")
    require("sourceAppLinks" in v11 and "platform-group[data-platform=" in v11, "platform app filtering missing")
    require('"cisco": {' in v13, "Cisco app recommendations missing")
    require('"android": ("OpenConnect"' in v13, "Cisco Android app recommendation missing")
    require('"ios": ("Cisco Secure Client"' in v13, "Cisco iOS app recommendation missing")
    require('"openvpn": {p: ("OpenVPN Connect"' in v13, "OpenVPN client recommendation missing")
    require('"wireguard": {p: ("WireGuard"' in v13, "WireGuard client recommendation missing")

    # File/link based protocol families keep their canonical delivery actions.
    require("['openvpn','wireguard','amneziawg']" in v20, "file-based protocol policy missing")
    require("key==='xray'" in v20, "Xray URI policy missing")
    for protocol in (
        "hysteria2", "tuic", "anytls", "naive", "shadowtls",
        "snell", "mieru", "trusttunnel", "sudoku",
    ):
        require(protocol in v20, f"modern protocol policy missing: {protocol}")
        require(protocol in v23, f"V23 modern protocol policy missing: {protocol}")

    # JSON/config detail schemas handled directly by V20/V21 remain unchanged.
    require("line('Username',out?.username)" in v20, "Naive username detail missing")
    require("line('User Key',out?.userkey)" in v20, "Snell user key detail missing")
    require("line('Handshake / SNI',tlsSni(out))" in v20, "ShadowTLS SNI detail missing")
    require("profile?.user?.name" in v20 and "profile?.user?.password" in v20, "Mieru identity detail missing")
    require("Server Public Key" in v20, "AmneziaWG endpoint detail missing")
    require("new URL(String(raw||''))" in v21, "standard URI parser missing")
    require("key==='hysteria2'" in v21 and "Password" in v21, "Hysteria2 URI details missing")
    require("key==='tuic'" in v21 and "UUID" in v21, "TUIC URI details missing")
    require("key==='anytls'" in v21 and "SNI" in v21, "AnyTLS URI details missing")
    require("startsWith('sudoku://')" in v21, "Sudoku deeplink parser missing")
    require("TextDecoder" in v21 and "AEAD" in v21, "Sudoku decoded details missing")

    # Direct-IP HTTP pages still need usable clipboard actions.
    require("document.execCommand('copy')" in v20, "clipboard fallback missing")
    require("document.execCommand('copy')" in v23, "V23 clipboard fallback missing")

    # Readability regression guard.
    require(".v17-title b{font-size:15px" in v20, "mobile title readability missing")
    require(".v17-action{min-height:38px" in v20, "mobile action readability missing")
    require(".v17-details{padding:10px;font-size:12px" in v20, "mobile details readability missing")
    require(".fact strong{font-size:14px" in v20, "desktop fact readability missing")
    require(".v17-action{font-size:12px;min-height:40px" in v23, "V23 mobile action readability missing")

    require("TWINPANEL_PUBLIC_CONNECT_PROTOCOL_ACTIONS_V20" in v20, "V20 marker missing")
    require("TWINPANEL_PUBLIC_CONNECT_PROTOCOL_URI_DETAILS_V21" in v21, "V21 marker missing")

    print("PUBLIC_CONNECT_PROTOCOL_ACTIONS_V20=PASS")
    print("PUBLIC_CONNECT_PROTOCOL_URI_DETAILS_V21=PASS")
    print("PUBLIC_CONNECT_DEVICE_DATA_AUTHORITY_V23=PASS")
    print("DEVICE_NEUTRAL_CONNECTION_FACTS=PASS")
    print("CISCO_COMPOSITE_ENDPOINT=PASS")


if __name__ == "__main__":
    main()
