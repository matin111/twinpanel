from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V11 = ROOT / "backend/app/routers/public_connection_device_actions_v11.py"
V20 = ROOT / "backend/app/routers/public_connection_protocol_actions_v20.py"
V21 = ROOT / "backend/app/routers/public_connection_protocol_uri_details_v21.py"
V22 = ROOT / "backend/app/routers/public_connection_protocol_action_authority_v22.py"
V23 = ROOT / "backend/app/routers/public_connection_device_presentation_v23.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    v11 = V11.read_text(encoding="utf-8")
    v20 = V20.read_text(encoding="utf-8")
    v21 = V21.read_text(encoding="utf-8")
    v22 = V22.read_text(encoding="utf-8")
    v23 = V23.read_text(encoding="utf-8")

    # V20/V21/V22 remain as legacy rollback artifacts, but V23 is the sole active adapter.
    require("public_connection_device_presentation_v23" in v11, "V23 import missing")
    require("refine_public_connection_device_presentation_v23(source)" in v11, "V23 chain missing")
    for retired in (
        "public_connection_protocol_actions_v20",
        "refine_public_connection_protocol_actions_v20",
        "public_connection_protocol_uri_details_v21",
        "refine_public_connection_protocol_uri_details_v21",
        "public_connection_protocol_action_authority_v22",
        "refine_public_connection_protocol_action_authority_v22",
    ):
        require(retired not in v11, f"retired mobile reconstruction re-entered V11: {retired}")

    # Preserve important legacy safety contracts for rollback/history.
    require("document.querySelectorAll('.v18-not-ready').forEach(row=>row.remove())" in v20, "legacy fake-server cleanup missing")
    require("key==='cisco'||key==='l2tp'" in v20, "legacy Cisco/L2TP manual policy missing")
    require("کپی اطلاعات" in v20, "legacy manual connection copy missing")
    require("stripInvalidClassicDownloads" in v20, "legacy invalid classic config cleanup missing")

    require("TWINPANEL_PUBLIC_CONNECT_PROTOCOL_ACTION_AUTHORITY_V22" in v22, "V22 marker missing")
    require("key==='cisco'||key==='l2tp'" in v22, "V22 manual protocol authority missing")
    require("if(!server||!user||!password)return[]" in v22, "manual credential validity guard missing")
    require("if(key==='l2tp'&&!secret)return[]" in v22, "L2TP IPsec secret guard missing")

    require("['openvpn','wireguard','amneziawg']" in v20, "legacy file-based protocol policy missing")
    require("key==='xray'" in v20, "legacy Xray URI policy missing")
    require("new URL(String(raw||''))" in v21, "legacy standard URI parser missing")
    require("startsWith('sudoku://')" in v21, "legacy Sudoku parser missing")

    # V23 may style/filter app recommendations, but it may not rebuild protocol actions/data.
    require(".protocol-panel" in v23 and ".server-view" in v23, "V23 canonical server authority missing")
    require("data-v13-platform" in v23 and "data-tp-platform" in v23, "device app presentation filter missing")
    require("fetch(" not in v23, "V23 must not fetch a second dataset")
    require("JSON.parse" not in v23, "V23 must not parse/rebuild configs")
    require("createElement('button')" not in v23 and 'createElement("button")' not in v23, "V23 must not rebuild protocol actions")
    require("createElement('a')" not in v23 and 'createElement("a")' not in v23, "V23 must not rebuild protocol links")

    # Readability now belongs to the presentation layer and must not use the old tiny scale.
    require("font-size:12px!important" in v23, "V23 readable action/fact size missing")
    require("font-size:13px" in v23, "V23 readable server text missing")
    require("font-size:16px!important" in v23, "V23 readable protocol title missing")

    print("PUBLIC_CONNECT_PROTOCOL_ACTIONS_V20_V21_V22_LEGACY=PASS")
    print("PUBLIC_DEVICE_PRESENTATION_V23_CANONICAL_ACTIONS=PASS")


if __name__ == "__main__":
    main()
