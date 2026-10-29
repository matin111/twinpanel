from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V34 = ROOT / "backend/app/routers/public_connection_forward_v34.py"
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
    match = re.search(
        rf"const\s+{re.escape(variable)}\s*=\s*new Set\(\[(.*?)\]\);",
        source,
        re.S,
    )
    if not match:
        raise AssertionError(f"JS Set {variable} missing")
    return tuple(re.findall(r"'([^']+)'", match.group(1)))


def main() -> None:
    v34 = V34.read_text(encoding="utf-8")
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
    require("return refine_public_connection_forward_v34(source)" in v26, "V34 is not final authority")
    require("public_connection_protocol_subscriptions_mount_v30" in v26, "V30 endpoint mount lost")

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

    # V11 owns platform detection. V34 only consumes its data attribute.
    require("body.dataset.tpPlatform=platform" in v11, "V11 platform data attribute missing")
    require("navigator.userAgentData" not in v34, "V34 duplicated V11 UA detection")
    require("navigator.userAgent||" not in v34, "V34 duplicated V11 UA detection")
    require("dataset?.tpPlatform" in v34, "V34 does not consume V11 platform data")
    require('body.v34-ready[data-tp-platform="android"]' in v34, "Android phone guard missing")
    require('body.v34-ready[data-tp-platform="ios"]' in v34, "iOS phone guard missing")
    require('body.v34-ready[data-tp-platform="windows"] .server-tabs' not in v34,
            "narrow Windows must keep desktop semantics")

    # V13 is the sole client mapping authority; V34 must not invent a second map.
    require("CLIENTS as V13_CLIENTS" in v34, "V34 does not import V13 CLIENTS")
    require("window.__TP_V34_CLIENTS__" in v34, "V13 client catalog is not passed to presentation")
    require("const CLIENTS={" not in v34, "hard-coded V34 client map returned")
    require("دانلود '+client.name" in v34, "one protocol-level client download missing")

    # V30 is the only subscription authority and only its proven cohort is shown.
    require(assigned_tuple(v30, "SUPPORTED_PROTOCOLS") == PROVEN_SUBSCRIPTIONS,
            "V30 proven subscription cohort changed")
    require(js_set(v34, "SUBSCRIPTIONS") == PROVEN_SUBSCRIPTIONS,
            "V34 subscription cohort must match V30 exactly")
    require("+'/sub/'+" in v34, "V34 does not use the V30 subscription endpoint")
    require("+'/multi/'+" not in v34, "V34 presentation must not use synthetic all-protocol multi links")
    require("کپی لینک اشتراک" in v34, "subscription copy label missing")
    require("افزودن همه به " in v34, "subscription app import label missing")

    # Existing V34 multi backend may remain mounted for backward compatibility,
    # but it is no longer a customer-facing subscription authority.
    require('"/{token}/multi/{protocol}"' in multi, "legacy V34 multi route unexpectedly removed")
    require("public_connection_all_multilink_v34_router" in mount, "legacy V34 multi route mount lost")

    # Canonical data/action sources remain intact and are consumed, not regenerated.
    require("standard_share_uri" in v15, "V15 standard share URI source missing")
    require("_resolve_delivery_content" in v16, "V16 lossless config source missing")
    require("refine_public_connection_protocol_actions_v20" in v20, "V20 classic action source missing")
    require("TWINPANEL_XRAY_PUBLIC_HUB_PROFILES_V48" in v48, "V48 Xray action source missing")
    for forbidden in ("db.add(", "db.commit(", "ProtocolCredential(", "credential_generation"):
        require(forbidden not in v34, f"presentation must not mutate credentials: {forbidden}")

    # Beginner-facing action semantics and dedupe.
    require("کپی کانفیگ" not in v34, "beginner UI must not expose copy-config")
    require("کپی لینک اتصال" in v34, "single-server link copy action missing")
    require("دانلود کانفیگ" in v34, "file config download action missing")
    require("mobile-send-btn" in v34, "legacy Windows/mobile-send hide missing")
    require("while(row.children.length>2)" in v34, "per-server maximum-two-actions gate missing")
    require("view.querySelectorAll('.v34-server-actions').forEach" in v34,
            "server action idempotence missing")
    require("cleanupPanel(panel)" in v34, "panel idempotence cleanup missing")
    require("MutationObserver" not in v34, "V34 must not use MutationObserver")
    require("setTimeout(apply" not in v34, "V34 must not stack delayed presentation passes")

    # Mobile uses a vertical server list and collapses only when the list is long.
    require("views.length>3" in v34, "mobile long-list collapse threshold missing")
    require("v34-mobile-servers" in v34, "mobile server details container missing")
    require("سرورهای تکی" in v34, "single-server section label missing")

    # Legacy containers stay data sources but not final presentation.
    for selector in (
        ".v13-client-only",
        ".v13-modern-action",
        ".server-view>.action-row",
        ".mobile-send-btn",
        ".multi-link-card",
    ):
        require(selector in v34, f"legacy source hide missing for {selector}")

    print("PUBLIC_CONNECT_FORWARD_V34_SMOKE=PASS")


if __name__ == "__main__":
    main()
