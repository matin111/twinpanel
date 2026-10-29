from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V26 = ROOT / "backend/app/routers/public_connection_canonical_mobile_v26.py"
V38 = ROOT / "backend/app/routers/public_connection_reference_layout_v38.py"
V39 = ROOT / "backend/app/routers/public_connection_ha_multiserver_v39.py"

EXPECTED_MULTI = {
    "openvpn", "wireguard", "v2ray", "hysteria2", "tuic", "anytls", "naive",
    "shadowtls", "snell", "mieru", "trusttunnel", "amneziawg", "sudoku",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def js_set(source: str, variable: str) -> set[str]:
    match = re.search(rf"const\s+{re.escape(variable)}\s*=\s*new Set\(\[(.*?)\]\);", source, re.S)
    require(match is not None, f"JS set {variable} missing")
    return set(re.findall(r"'([^']+)'", match.group(1)))


def main() -> None:
    v26 = V26.read_text(encoding="utf-8")
    v38 = V38.read_text(encoding="utf-8")
    v39 = V39.read_text(encoding="utf-8")

    require("TWINPANEL_PUBLIC_CONNECT_REFERENCE_LAYOUT_V38" in v38, "V38 marker missing")
    require("TWINPANEL_PUBLIC_CONNECT_HA_MULTISERVER_V39" in v39, "V39 marker missing")
    require("refine_public_connection_reference_layout_v38" in v26, "V38 not mounted by V26")
    require("refine_public_connection_ha_multiserver_v39" in v26, "V39 not mounted by V26")

    v38_call = v26.index("source = refine_public_connection_reference_layout_v38(source)")
    v39_return = v26.index("return refine_public_connection_ha_multiserver_v39(source)")
    require(v38_call < v39_return, "V39 must refine V38 rather than replace it")

    require(js_set(v38, "MULTI") == EXPECTED_MULTI, "V38 multilink protocol set drifted")
    require("+'/multi/'+" in v38, "V38 multi route compatibility lost")
    require(".v38-all-card" in v38, "V38 reference card marker missing")
    require(".v38-all-card" in v39, "V39 must explicitly retire the V38 card")

    for forbidden in (
        "db.add(", "db.commit(", "ProtocolCredential(", "Quota", "iptables", "nft", "vxlan", "tp27",
        "provision", "credential_generation", "routing", "firewall",
    ):
        require(forbidden not in v38, f"V38 escaped presentation-only scope: {forbidden}")
    require("MutationObserver" not in v38, "V38 must not install a DOM observer")
    require("setInterval" not in v38, "V38 must not poll")

    print("PUBLIC_CONNECT_REFERENCE_V38_COMPATIBILITY_SMOKE=PASS")


if __name__ == "__main__":
    main()
