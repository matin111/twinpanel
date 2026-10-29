from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "backend/app/routers/public_connection_ha_multiserver_v39.py"
MOUNT = ROOT / "backend/app/routers/public_connection_canonical_mobile_v26.py"

source = SRC.read_text(encoding="utf-8")
mount = MOUNT.read_text(encoding="utf-8")

assert "TWINPANEL_PUBLIC_CONNECT_HA_MULTISERVER_V39" in source
assert "refine_public_connection_ha_multiserver_v39" in mount
assert "return refine_public_connection_ha_multiserver_v39(source)" in mount

# Exact requested structure: protocol -> High Availability Config -> Multi Server,
# followed by the existing individual server rows.
for marker in (
    "High Availability Config",
    "Multi Server",
    "v39-ha-card",
    "v39-ha-row",
    "server-view",
):
    assert marker in source, marker

for protocol in (
    "openvpn", "wireguard", "v2ray", "hysteria2", "tuic", "anytls",
    "naive", "shadowtls", "snell", "mieru", "trusttunnel", "amneziawg", "sudoku",
):
    assert f"'{protocol}'" in source, protocol

# V39 consumes the existing official V34 multi endpoint directly and does not
# depend on another async metadata request before showing the Multi Server row.
assert "'/multi/'+encodeURIComponent(protocol)" in source
assert "fetch(" not in source
assert "multiMeta" not in source
assert "subscriptionCount" not in source

# Existing V38 card is retired only at presentation level; backend delivery stays intact.
assert ".v38-all-card" in source
assert ".v37-multi-card" in source
assert "querySelectorAll('.v37-multi-card,.v38-all-card')" in source

# Native bundles and import-capable protocols keep useful multi actions.
assert "دانلود همه" in source
assert "افزودن همه" in source
assert "کپی لینک" in source
assert "کپی مولتی‌لینک" in source

# Mobile stays compact: protocol accordion is authoritative and the standalone
# app card is hidden only inside the opened compact protocol.
assert ".protocol-panel.v36-open{display:block!important}" in source
assert ".protocol-panel{display:none!important}" in source
assert ".protocol-panel.v36-open .v34-client-card{display:none!important}" in source

# V39 is final and runs strictly after V38.
assert mount.index("refine_public_connection_reference_layout_v38(source)") < mount.index(
    "refine_public_connection_ha_multiserver_v39(source)"
)

# Presentation-only scope guard.
for forbidden in (
    "db.add(", "db.commit(", "ProtocolCredential(", "credential_generation",
    "iptables", "nft", "vxlan", "tp27", "provision", "quota", "accounting",
):
    assert forbidden not in source.lower(), forbidden
assert "MutationObserver" not in source
assert "setInterval" not in source

print("V39 HA/Multi Server presentation smoke passed")
