from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V11 = ROOT / "backend/app/routers/public_connection_device_actions_v11.py"
V20 = ROOT / "backend/app/routers/public_connection_protocol_actions_v20.py"
V21 = ROOT / "backend/app/routers/public_connection_protocol_uri_details_v21.py"
V22 = ROOT / "backend/app/routers/public_connection_protocol_action_authority_v22.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    v11 = V11.read_text(encoding="utf-8")
    v20 = V20.read_text(encoding="utf-8")
    v21 = V21.read_text(encoding="utf-8")
    v22 = V22.read_text(encoding="utf-8")

    require("public_connection_protocol_actions_v20" in v11, "V20 import missing")
    require("refine_public_connection_protocol_actions_v20(source)" in v11, "V20 chain missing")
    require("public_connection_protocol_uri_details_v21" in v11, "V21 import missing")
    require("refine_public_connection_protocol_uri_details_v21(source)" in v11, "V21 chain missing")
    require("public_connection_protocol_action_authority_v22" in v11, "V22 import missing")
    require("refine_public_connection_protocol_action_authority_v22(source)" in v11, "V22 chain missing")

    # Never expose fake public server rows or internal pending provisioning cards.
    require("document.querySelectorAll('.v18-not-ready').forEach(row=>row.remove())" in v20, "fake server cleanup missing")
    require("protocol-choice.v13-pending" in v20 and "tp-v20-hidden-pending" in v20, "pending protocol cleanup missing")
    require("realRows.length+' سرور'" in v20, "real server count missing")

    # Manual protocols must stay manual; do not invent downloadable config files.
    require("key==='cisco'||key==='l2tp'" in v20, "Cisco/L2TP manual policy missing")
    require("کپی اطلاعات" in v20, "manual connection copy missing")
    require("stripInvalidClassicDownloads" in v20, "invalid classic config cleanup missing")

    # V22 is the final mobile authority after V17/V18 rebuilds.
    require("TWINPANEL_PUBLIC_CONNECT_PROTOCOL_ACTION_AUTHORITY_V22" in v22, "V22 marker missing")
    require("MutationObserver" in v22 and "reconnectObserver" in v22, "V22 rebuild observer missing")
    require("actions.replaceChildren()" in v22, "V22 action dedupe missing")
    require("row.appendChild(detail)" in v22, "V22 detail DOM attachment missing")
    require("key==='cisco'||key==='l2tp'" in v22, "V22 manual protocol authority missing")
    require("if(!server||!user||!password)return[]" in v22, "manual credential validity guard missing")
    require("if(key==='l2tp'&&!secret)return[]" in v22, "L2TP IPsec secret guard missing")
    require("v22-manual-invalid" in v22, "invalid manual server suppression missing")
    require("کپی اطلاعات" in v22 and "جزئیات" in v22, "manual actions missing")
    require("کپی کانفیگ" in v22, "config protocols copy action missing")
    require("دانلود کانفیگ" in v22, "file protocol download action missing")
    require("v22-endpoint" in v22 and "endpointFrom(rows)" in v22, "real endpoint display missing")

    # File/link based protocol families keep their canonical delivery actions.
    require("['openvpn','wireguard','amneziawg']" in v20, "file-based protocol policy missing")
    require("key==='xray'" in v20, "Xray URI policy missing")
    for protocol in (
        "hysteria2", "tuic", "anytls", "naive", "shadowtls",
        "snell", "mieru", "trusttunnel", "sudoku",
    ):
        require(protocol in v20, f"modern protocol policy missing: {protocol}")
        require(protocol in v22, f"V22 modern protocol policy missing: {protocol}")

    # JSON/config detail schemas handled directly by V20.
    require("line('Username',out?.username)" in v20, "Naive username detail missing")
    require("line('User Key',out?.userkey)" in v20, "Snell user key detail missing")
    require("line('Handshake / SNI',tlsSni(out))" in v20, "ShadowTLS SNI detail missing")
    require("profile?.user?.name" in v20 and "profile?.user?.password" in v20, "Mieru identity detail missing")
    require("Server Public Key" in v20, "AmneziaWG endpoint detail missing")

    # Standard URI/deeplink schemas are parsed from their canonical payloads in V21.
    require("new URL(String(raw||''))" in v21, "standard URI parser missing")
    require("key==='hysteria2'" in v21 and "Password" in v21, "Hysteria2 URI details missing")
    require("key==='tuic'" in v21 and "UUID" in v21, "TUIC URI details missing")
    require("key==='anytls'" in v21 and "SNI" in v21, "AnyTLS URI details missing")
    require("startsWith('sudoku://')" in v21, "Sudoku deeplink parser missing")
    require("TextDecoder" in v21 and "AEAD" in v21, "Sudoku decoded details missing")

    # Direct-IP HTTP pages still need usable clipboard actions.
    require("document.execCommand('copy')" in v20, "clipboard fallback missing")
    require("document.execCommand('copy')" in v22, "V22 clipboard fallback missing")

    # Readability regression: reject the old 6.5/7px mobile scale.
    require(".v17-title b{font-size:15px" in v20, "mobile title readability missing")
    require(".v17-action{min-height:38px" in v20, "mobile action readability missing")
    require(".v17-details{padding:10px;font-size:12px" in v20, "mobile details readability missing")
    require(".fact strong{font-size:14px" in v20, "desktop fact readability missing")
    require(".v17-action{font-size:12px;min-height:40px" in v22, "V22 mobile action readability missing")

    require("TWINPANEL_PUBLIC_CONNECT_PROTOCOL_ACTIONS_V20" in v20, "V20 marker missing")
    require("TWINPANEL_PUBLIC_CONNECT_PROTOCOL_URI_DETAILS_V21" in v21, "V21 marker missing")

    print("PUBLIC_CONNECT_PROTOCOL_ACTIONS_V20=PASS")
    print("PUBLIC_CONNECT_PROTOCOL_URI_DETAILS_V21=PASS")
    print("PUBLIC_CONNECT_PROTOCOL_ACTION_AUTHORITY_V22=PASS")


if __name__ == "__main__":
    main()
