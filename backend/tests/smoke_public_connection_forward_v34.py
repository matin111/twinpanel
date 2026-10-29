from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V34 = ROOT / "backend/app/routers/public_connection_forward_v34.py"
V36 = ROOT / "backend/app/routers/public_connection_mobile_compact_v36.py"
V37 = ROOT / "backend/app/routers/public_connection_final_presentation_v37.py"
V38 = ROOT / "backend/app/routers/public_connection_reference_layout_v38.py"
V39 = ROOT / "backend/app/routers/public_connection_ha_multiserver_v39.py"
V26 = ROOT / "backend/app/routers/public_connection_canonical_mobile_v26.py"
V11 = ROOT / "backend/app/routers/public_connection_device_actions_v11.py"
V13 = ROOT / "backend/app/routers/public_connection_modern_delivery_v13.py"
V15 = ROOT / "backend/app/routers/public_connection_modern_import_v15.py"
V16 = ROOT / "backend/app/routers/public_connection_modern_delivery_v16.py"
V20 = ROOT / "backend/app/routers/public_connection_protocol_actions_v20.py"
V30 = ROOT / "backend/app/routers/public_connection_protocol_subscriptions_v30.py"
V48 = ROOT / "backend/app/xray_public_hub_profiles_v48.py"
MULTI = ROOT / "backend/app/routers/public_connection_all_multilink_v34.py"
MOUNT = ROOT / "backend/app/routers/public_connection_forward_mount_v34.py"

PROVEN_SUBSCRIPTIONS = ("v2ray", "hysteria2", "tuic", "anytls")
MULTI_PROTOCOLS = (
    "openvpn", "wireguard", "v2ray", "hysteria2", "tuic", "anytls", "naive",
    "shadowtls", "snell", "mieru", "trusttunnel", "amneziawg", "sudoku",
)
CANONICAL_PROTOCOLS = (
    "cisco", "openvpn", "wireguard", "l2tp", "v2ray",
    "hysteria2", "tuic", "anytls", "naive", "shadowtls",
    "snell", "mieru", "trusttunnel", "amneziawg", "sudoku",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assigned_tuple(source: str, variable: str) -> tuple[str, ...]:
    tree = ast.parse(source)
    for node in tree.body:
        target = None
        value = None
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                target = node.targets[0].id
                value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target.id
            value = node.value
        if target == variable and value is not None:
            return tuple(str(item) for item in ast.literal_eval(value))
    raise AssertionError(f"{variable} assignment missing")


def js_set(source: str, variable: str) -> tuple[str, ...]:
    match = re.search(rf"const\s+{re.escape(variable)}\s*=\s*new Set\(\[(.*?)\]\);", source, re.S)
    if not match:
        raise AssertionError(f"JS Set {variable} missing")
    return tuple(re.findall(r"'([^']+)'", match.group(1)))


def main() -> None:
    v34 = V34.read_text(encoding="utf-8")
    v36 = V36.read_text(encoding="utf-8")
    v37 = V37.read_text(encoding="utf-8")
    v38 = V38.read_text(encoding="utf-8")
    v39 = V39.read_text(encoding="utf-8")
    v26 = V26.read_text(encoding="utf-8")
    v11 = V11.read_text(encoding="utf-8")
    v13 = V13.read_text(encoding="utf-8")
    v15 = V15.read_text(encoding="utf-8")
    v16 = V16.read_text(encoding="utf-8")
    v20 = V20.read_text(encoding="utf-8")
    v30 = V30.read_text(encoding="utf-8")
    v48 = V48.read_text(encoding="utf-8")
    multi = MULTI.read_text(encoding="utf-8")
    mount = MOUNT.read_text(encoding="utf-8")

    require("TWINPANEL_PUBLIC_CONNECT_FORWARD_V34" in v34, "V34 marker missing")
    require("TWINPANEL_PUBLIC_CONNECT_MOBILE_COMPACT_V36" in v36, "V36 marker missing")
    require("TWINPANEL_PUBLIC_CONNECT_FINAL_PRESENTATION_V37" in v37, "V37 marker missing")
    require("TWINPANEL_PUBLIC_CONNECT_REFERENCE_LAYOUT_V38" in v38, "V38 marker missing")
    require("TWINPANEL_PUBLIC_CONNECT_HA_MULTISERVER_V39" in v39, "V39 marker missing")

    # Composition: keep existing layers, then refine the visible reference card in V39.
    positions = [
        v26.find("source = refine_public_connection_mobile_compact_v36(source)"),
        v26.find("source = refine_public_connection_forward_v34(source)"),
        v26.find("source = refine_public_connection_final_presentation_v37(source)"),
        v26.find("source = refine_public_connection_reference_layout_v38(source)"),
        v26.find("return refine_public_connection_ha_multiserver_v39(source)"),
    ]
    require(all(pos >= 0 for pos in positions) and positions == sorted(positions),
            "V36 -> V34 -> V37 -> V38 -> V39 composition order drifted")
    require(v26.rstrip().endswith("return refine_public_connection_ha_multiserver_v39(source)"),
            "V39 is not the final composer")

    for old in (
        "refine_public_connection_mobile_ui_v27(source)",
        "refine_public_connection_mobile_v28(source)",
        "refine_public_connection_presentation_v29(source)",
        "refine_public_connection_protocol_subscriptions_v30(source)",
        "refine_public_connection_unified_actions_v31(source)",
        "refine_public_connection_platform_guard_v32(source)",
    ):
        require(old not in v26, f"retired presentation refiner returned: {old}")

    classic = assigned_tuple(v13, "CLASSIC_PROTOCOLS")
    modern = assigned_tuple(v13, "MODERN_PROTOCOLS")
    require(classic + modern == CANONICAL_PROTOCOLS, "15-protocol inventory drifted")

    require("body.dataset.tpPlatform=platform" in v11, "V11 platform authority missing")
    require("function isCompact()" in v36 and "window.matchMedia(MOBILE).matches" in v36,
            "V36 viewport accordion authority missing")
    require("const PHONE=" not in v36, "V36 must not restrict compact layout to Android/iOS UA")

    require("CLIENTS as V13_CLIENTS" in v34, "V34 does not consume V13 client mapping")
    require("window.__TP_V34_CLIENTS__" in v34, "V13 client catalog not passed to presentation")
    require("const CLIENTS={" not in v34, "hard-coded V34 client map returned")

    require(assigned_tuple(v30, "SUPPORTED_PROTOCOLS") == PROVEN_SUBSCRIPTIONS,
            "V30 proven subscription cohort changed")
    require(js_set(v34, "SUBSCRIPTIONS") == PROVEN_SUBSCRIPTIONS,
            "V34 proven subscription cohort drifted")

    # Backend authority remains V34; V39 only presents the existing all-protocol endpoint.
    require(assigned_tuple(multi, "MULTI_PROTOCOLS") == MULTI_PROTOCOLS,
            "V34 all-protocol multi backend drifted")
    require('"/{token}/multi/{protocol}"' in multi, "V34 multi route removed")
    require("public_connection_all_multilink_v34_router" in mount, "V34 multi route mount lost")
    require(set(js_set(v39, "MULTI")) == set(MULTI_PROTOCOLS), "V39 multilink cohort drifted")
    require("+'/multi/'+" in v39, "V39 does not consume V34 multi route")
    require("High Availability Config" in v39 and "Multi Server" in v39,
            "V39 requested reference structure missing")
    require("fetch(" not in v39 and "multiMeta" not in v39,
            "V39 must not wait for async meta before rendering Multi Server")

    require("standard_share_uri" in v15, "V15 share URI source missing")
    require("_resolve_delivery_content" in v16, "V16 lossless config source missing")
    require("refine_public_connection_protocol_actions_v20" in v20, "V20 action source missing")
    require("TWINPANEL_XRAY_PUBLIC_HUB_PROFILES_V48" in v48, "V48 Xray source missing")

    for presentation in (v34, v36, v37, v38, v39):
        for forbidden in ("db.add(", "db.commit(", "ProtocolCredential(", "credential_generation"):
            require(forbidden not in presentation, f"presentation mutates credentials: {forbidden}")
        require("MutationObserver" not in presentation, "presentation must not use MutationObserver")

    require("panel.classList.add('active','v36-open')" in v36, "compact open state missing")
    require("const wasOpen=panel.classList.contains('v36-open')" in v36, "toggle-close state missing")
    require("event.stopImmediatePropagation()" in v36, "legacy click isolation missing")
    require(".protocol-panel.v36-open{display:block!important}" in v39,
            "V39 must preserve one-open-protocol accordion")
    require(".protocol-panel{display:none!important}" in v39,
            "V39 compact protocols must start collapsed")

    require("heading==='اتصال هوشمند'" in v37, "Smart Connect cleanup missing")
    require(".v38-all-card" in v39 and ".v37-multi-card" in v39,
            "V39 must retire older competing all-server cards")

    print("PUBLIC_CONNECT_FORWARD_V34_V39_SMOKE=PASS")


if __name__ == "__main__":
    main()
