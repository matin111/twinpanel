from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "backend/app/routers/public_connection_ha_card_v38.py"
MOUNT = ROOT / "backend/app/routers/public_connection_canonical_mobile_v26.py"

source = SRC.read_text(encoding="utf-8")
mount = MOUNT.read_text(encoding="utf-8")

assert "TWINPANEL_PUBLIC_CONNECT_HA_CARD_V38" in source
assert "refine_public_connection_ha_card_v38" in mount
assert "return refine_public_connection_ha_card_v38(source)" in mount

# Reference structure: HA header + protocol badge + Multi Server row.
for marker in (
    "High Availability Config",
    "Multi Server",
    "v38-ha-badge",
    "v38-ha-row",
    "سرورهای تکی",
):
    assert marker in source, marker

# All supported multi protocols remain present, including native bundles.
for protocol in (
    "openvpn", "wireguard", "v2ray", "hysteria2", "tuic", "anytls",
    "naive", "shadowtls", "snell", "mieru", "trusttunnel", "amneziawg", "sudoku",
):
    assert f"'{protocol}'" in source, protocol

# Uses the existing official V34 multi endpoint; no new delivery/dataplane implementation.
assert "'/multi/'+encodeURIComponent(protocol)" in source
assert "fetch(" not in source
assert "multiMeta" not in source
assert "ProtocolCredential" not in source
for forbidden in ("iptables", "nft", "vxlan", "tp27", "provision", "quota", "accounting"):
    assert forbidden not in source.lower(), forbidden

# Phone presentation stays platform-aware, not viewport-only semantics.
assert 'data-tp-platform="android"' in source
assert 'data-tp-platform="ios"' in source
assert 'data-tp-platform="windows"' not in source

# V38 must be composed after V37 so it can retire the failed V37 visual card deterministically.
assert mount.index("refine_public_connection_final_presentation_v37(source)") < mount.index("refine_public_connection_ha_card_v38(source)")

print("V38 HA/Multi Server presentation smoke passed")
