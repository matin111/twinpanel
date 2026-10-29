from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V34 = ROOT / "backend/app/routers/public_connection_forward_v34.py"
V26 = ROOT / "backend/app/routers/public_connection_canonical_mobile_v26.py"
V13 = ROOT / "backend/app/routers/public_connection_modern_delivery_v13.py"
MULTI = ROOT / "backend/app/routers/public_connection_all_multilink_v34.py"
DOWNLOAD = ROOT / "backend/app/routers/public_connection_app_download_v34.py"
MOUNT = ROOT / "backend/app/routers/public_connection_forward_mount_v34.py"

EXPECTED_MULTI = (
    "openvpn",
    "wireguard",
    "v2ray",
    "hysteria2",
    "tuic",
    "anytls",
    "naive",
    "shadowtls",
    "snell",
    "mieru",
    "trusttunnel",
    "amneziawg",
    "sudoku",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assigned_tuple(source: str, variable: str) -> tuple[str, ...]:
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == variable:
                value = ast.literal_eval(node.value)
                return tuple(str(item) for item in value)
    raise AssertionError(f"{variable} assignment missing")


def main() -> None:
    v34 = V34.read_text(encoding="utf-8")
    v26 = V26.read_text(encoding="utf-8")
    v13 = V13.read_text(encoding="utf-8")
    multi = MULTI.read_text(encoding="utf-8")
    download = DOWNLOAD.read_text(encoding="utf-8")
    mount = MOUNT.read_text(encoding="utf-8")

    require("TWINPANEL_PUBLIC_CONNECT_FORWARD_V34" in v34, "V34 marker missing")
    require("return refine_public_connection_forward_v34(source)" in v26, "V34 is not final authority")
    require("public_connection_forward_mount_v34" in v26, "V34 routes are not mounted")
    require("public_connection_protocol_subscriptions_mount_v30" in v26, "legacy V30 endpoint compatibility lost")

    # Never restore the accumulated V27-V32 presentation stack.
    for old in (
        "refine_public_connection_mobile_ui_v27(source)",
        "refine_public_connection_mobile_v28(source)",
        "refine_public_connection_presentation_v29(source)",
        "refine_public_connection_protocol_subscriptions_v30(source)",
        "refine_public_connection_unified_actions_v31(source)",
        "refine_public_connection_platform_guard_v32(source)",
    ):
        require(old not in v26, f"retired presentation refiner returned: {old}")

    # Canonical inventory remains all 15 protocols.
    require('CLASSIC_PROTOCOLS = ("cisco", "openvpn", "wireguard", "l2tp", "v2ray")' in v13,
            "classic protocol inventory changed")
    for protocol in (
        "hysteria2", "tuic", "anytls", "naive", "shadowtls",
        "snell", "mieru", "trusttunnel", "amneziawg", "sudoku",
    ):
        require(f'"{protocol}"' in v13, f"missing modern protocol {protocol}")

    # Exactly 13 protocols get the all-server route. Cisco and L2TP stay manual.
    backend_multi = assigned_tuple(multi, "MULTI_PROTOCOLS")
    require(backend_multi == EXPECTED_MULTI, f"wrong backend multi inventory: {backend_multi!r}")
    require("'cisco'" not in backend_multi and "'l2tp'" not in backend_multi,
            "manual protocols must not get multi delivery")
    for protocol in EXPECTED_MULTI:
        require(f"'{protocol}'" in v34, f"V34 UI missing multi protocol {protocol}")

    require('"/{token}/multi/{protocol}"' in multi, "all-server endpoint missing")
    require('"/{token}/multi/{protocol}/meta"' in multi, "all-server metadata endpoint missing")
    require('NATIVE_BUNDLE_PROTOCOLS = {"openvpn", "wireguard", "amneziawg"}' in multi,
            "native file protocols must stay native bundles")
    require('return "uri"' in multi, "URI feed path missing")
    require('return "singbox"' in multi, "sing-box feed path missing")
    require('return "bundle"' in multi, "bundle path missing")

    # V34 beginner semantics.
    require("کپی لینک همه سرورها" in v34, "multi-link copy action missing")
    require("کپی لینک اتصال" in v34, "single-server link copy action missing")
    require("دانلود کانفیگ" in v34, "file-based single-server action missing")
    require("دانلود مستقیم " in v34, "direct app-download label missing")
    require("کپی کانفیگ" not in v34, "beginner UI must not expose copy-config")
    require("while(row.children.length>2)" in v34, "per-server maximum-two-actions gate missing")

    # One app download card at protocol level, never repeated per server.
    require("v34-client-card" in v34, "device app card missing")
    require("v34-server-actions" in v34, "canonical server action row missing")
    require("panel.querySelectorAll('.v34-multi-card,.v34-client-card').forEach" in v34,
            "protocol-level card dedupe missing")
    require("view.querySelectorAll('.v34-server-actions').forEach" in v34,
            "server action dedupe missing")
    require("/v1/connect/app-download/" in v34, "UI does not use direct-download resolver")

    # Direct downloads are internal redirect endpoints, not product landing pages.
    require('"/app-download/{app}/{platform}"' in download, "direct app-download endpoint missing")
    require("browser_download_url" in download, "GitHub release asset resolver missing")
    require("quickstart" not in download.lower(), "Karing landing page must not be used")
    require("How-to-install-Hiddify-app" not in download, "Hiddify documentation page must not be used")
    require("openconnect-gui-1.5.3-win32.exe" in download, "direct Cisco/OpenConnect Windows installer missing")
    require("wireguard-installer.exe" in download, "direct WireGuard Windows installer missing")
    require("OpenVPN-2.7.8-I002-amd64.msi" in download, "direct OpenVPN Windows installer missing")
    require("agrd.io/android_trusttunnel" in download, "verified TrustTunnel Android destination missing")

    # Mount all V34 routes into the already-included public multilink router.
    require("public_connection_all_multilink_v34_router" in mount, "13-protocol router not mounted")
    require("public_connection_app_download_v34_router" in mount, "direct-download router not mounted")

    # Narrow Windows must never become phone presentation.
    require('body.v34-ready[data-tp-platform="android"]' in v34, "Android phone guard missing")
    require('body.v34-ready[data-tp-platform="ios"]' in v34, "iOS phone guard missing")
    require('body.v34-ready[data-tp-platform="windows"] .server-tabs' not in v34,
            "Windows must not receive phone server-stack rules")

    # Legacy chrome stays source-only.
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
