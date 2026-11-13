"""One audited destination per protocol, OS and client.

GitHub links point to VERSION-PINNED release assets (not releases pages);
iOS/macOS store links point to the specific official app. A plain 200 HTML
response from the panel is NEVER treated as an APK or installer.

Only explicitly tested URL destinations appear here. Existing server routes,
subscription keys and client configuration formats are unchanged.
"""
from __future__ import annotations

from typing import Any

PLATFORMS = ("android", "ios", "windows", "macos")

# OS maps: (human name, HTTPS installable file or exact store listing).
APPS: dict[str, dict[str, tuple[str, str]]] = {
    "openconnect": {
        "android": ("OpenConnect", "https://f-droid.org/repo/net.openconnect_vpn.android_1120.apk"),
        "ios": ("Cisco Secure Client", "https://apps.apple.com/us/app/cisco-secure-client/id1135064690"),
        "windows": ("OpenConnect GUI", "https://github.com/openconnect/openconnect-gui/releases/download/v1.5.3/openconnect-gui-1.5.3-win32.exe"),
        # No current audited macOS installer; provide the actual package install route.
        "macos": ("OpenConnect (Homebrew)", "https://formulae.brew.sh/formula/openconnect"),
    },
    "openvpn": {
        "android": ("OpenVPN for Android", "https://f-droid.org/repo/de.blinkt.openvpn_225.apk"),
        "ios": ("OpenVPN Connect", "https://apps.apple.com/us/app/openvpn-connect/id590379981"),
        "windows": ("OpenVPN Community", "https://build.openvpn.net/downloads/releases/OpenVPN-2.7.8-I002-amd64.msi"),
        "macos": ("Tunnelblick (OpenVPN)", "https://github.com/Tunnelblick/Tunnelblick/releases/download/v10.0.3/Tunnelblick_10.0.3_build_6610.dmg"),
    },
    "wireguard": {
        "android": ("WireGuard", "https://download.wireguard.com/android-client/com.wireguard.android-1.0.20260315.apk"),
        "ios": ("WireGuard", "https://apps.apple.com/us/app/wireguard/id1441195209"),
        "windows": ("WireGuard", "https://download.wireguard.com/windows-client/wireguard-installer.exe"),
        "macos": ("WireGuard", "https://apps.apple.com/us/app/wireguard/id1451685025"),
    },
    "v2rayng": {
        "android": ("v2rayNG", "https://github.com/2dust/v2rayNG/releases/download/2.3.15/v2rayNG_2.3.15_arm64-v8a.apk"),
    },
    "v2box": {
        "ios": ("V2Box", "https://apps.apple.com/us/app/v2box-v2ray-client/id6446814690"),
    },
    "v2rayn": {
        "windows": ("v2rayN", "https://github.com/2dust/v2rayN/releases/download/7.25.6/v2rayN-windows-64-desktop.zip"),
        "macos": ("v2rayN", "https://github.com/2dust/v2rayN/releases/download/7.25.6/v2rayN-macos-arm64.dmg"),
    },
    "karing": {
        "android": ("Karing", "https://github.com/KaringX/karing/releases/download/v1.2.26.2929/karing_1.2.26.2929_android_arm64-v8a.apk"),
        "ios": ("Karing", "https://apps.apple.com/us/app/karing/id6472431552"),
        "windows": ("Karing", "https://github.com/KaringX/karing/releases/download/v1.2.26.2929/karing_1.2.26.2929_windows_x64.exe"),
        "macos": ("Karing", "https://github.com/KaringX/karing/releases/download/v1.2.26.2929/karing_1.2.26.2929_macos_universal.dmg"),
    },
    "singbox": {
        "android": ("sing-box", "https://github.com/SagerNet/sing-box/releases/download/v1.14.4/SFA-1.14.4-arm64-v8a.apk"),
        "ios": ("sing-box MT", "https://apps.apple.com/us/app/sing-box-mt/id6785326793"),
        "windows": ("sing-box", "https://github.com/SagerNet/sing-box/releases/download/v1.14.4/SFW-1.14.4-x64.exe"),
        "macos": ("sing-box", "https://github.com/SagerNet/sing-box/releases/download/v1.14.4/SFM-1.14.4-Universal.pkg"),
    },
    "amneziawg": {
        "android": ("AmneziaWG", "https://github.com/amnezia-vpn/amneziawg-android/releases/download/v3.1.20260814/AmneziaWG-3.1.202060814.apk"),
        "ios": ("AmneziaWG", "https://apps.apple.com/us/app/amneziawg/id6478942365"),
        "windows": ("AmneziaWG", "https://github.com/amnezia-vpn/amneziawg-windows-client/releases/download/3.1.0/amneziawg-amd64-3.1.0.msi"),
        "macos": ("AmneziaWG", "https://apps.apple.com/us/app/amneziawg/id6478942365"),
    },
    "trusttunnel": {
        "android": ("TrustTunnel", "https://play.google.com/store/apps/details?id=com.adguard.trusttunnel"),
        "ios": ("TrustTunnel", "https://apps.apple.com/us/app/trusttunnel/id6755807890"),
        # Official Windows CLI ZIP. Do not label it as a GUI installer.
        "windows": ("TrustTunnel CLI", "https://github.com/TrustTunnel/TrustTunnelClient/releases/download/v1.1.12/trusttunnel_client-v1.1.12-windows-x86_64.zip"),
        "macos": ("TrustTunnel", "https://apps.apple.com/us/app/trusttunnel/id6755807890"),
    },
    "sudoku": {
        "android": ("Sudodroid", "https://github.com/SUDOKU-ASCII/sudoku-android/releases/download/v0.3.4/sudodroid-v0.3.4-universal.apk"),
        "ios": ("Anywhere Proxy", "https://apps.apple.com/us/app/anywhere-proxy/id6758235178"),
        "windows": ("Sudoku Desktop", "https://github.com/SUDOKU-ASCII/sudoku-desktop/releases/download/v0.2.5/sudoku4x4_v0.2.5_windows-amd64.exe"),
        "macos": ("Sudoku Desktop", "https://github.com/SUDOKU-ASCII/sudoku-desktop/releases/download/v0.2.5/sudoku4x4_v0.2.5_darwin-arm64.dmg"),
    },
    "hiddify": {
        "android": ("Hiddify", "https://github.com/hiddify/hiddify-app/releases/download/v5.5.5/Hiddify-Android-arm64.apk"),
        "ios": ("Hiddify", "https://apps.apple.com/us/app/hiddify-proxy-vpn/id6596777532"),
    },
}

# Protocol -> OS-specific client. Do not accidentally route Cisco to Karing,
# AmneziaWG to ordinary WireGuard, or V2Ray Android to a web release page.
PROTOCOL_CLIENT: dict[str, dict[str, str]] = {
    "cisco": {p: "openconnect" for p in PLATFORMS},
    "openvpn": {p: "openvpn" for p in PLATFORMS},
    "wireguard": {p: "wireguard" for p in PLATFORMS},
    "l2tp": {},  # Native OS setup only; never show a fake download.
    "v2ray": {"android": "v2rayng", "ios": "v2box", "windows": "v2rayn", "macos": "v2rayn"},
    "hysteria2": {p: "karing" for p in PLATFORMS},
    "tuic": {p: "karing" for p in PLATFORMS},
    "anytls": {p: "karing" for p in PLATFORMS},
    "naive": {p: "singbox" for p in PLATFORMS},
    "shadowtls": {p: "singbox" for p in PLATFORMS},
    "snell": {p: "singbox" for p in PLATFORMS},
    "mieru": {p: "karing" for p in PLATFORMS},
    "socks5": {p: "karing" for p in PLATFORMS},
    "trusttunnel": {p: "trusttunnel" for p in PLATFORMS},
    "amneziawg": {p: "amneziawg" for p in PLATFORMS},
    "sudoku": {p: "sudoku" for p in PLATFORMS},
}

ALIASES = {
    "openconnect": "openconnect", "anyconnect": "openconnect",
    "cisco": "cisco", "xray": "v2ray", "naiveproxy": "naive",
    "sing-box": "singbox", "singbox": "singbox",
    "v2rayng": "v2rayng", "v2rayn": "v2rayn", "v2box": "v2box",
}

# Additional verified architecture-specific installers for the global Apps tab.
ALTERNATIVE_ASSETS: dict[str, list[tuple[str, str, str]]] = {
    "macos": [
        ("v2rayN · Intel", "https://github.com/2dust/v2rayN/releases/download/7.25.6/v2rayN-macos-64.dmg", "Intel Mac"),
        ("Sudoku Desktop · Intel", "https://github.com/SUDOKU-ASCII/sudoku-desktop/releases/download/v0.2.5/sudoku4x4_v0.2.5_darwin-amd64.dmg", "Intel Mac"),
    ],
}


def normalize(value: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def app_for_protocol(protocol: str, platform: str) -> str | None:
    key = ALIASES.get(str(protocol or "").strip().lower(), str(protocol or "").strip().lower())
    plat = normalize(platform)
    if plat in ("iphone", "ipad"):plat = "ios"
    return PROTOCOL_CLIENT.get(key, {}).get(plat)


def client_for(protocol: str, platform: str) -> tuple[str, str] | None:
    app = app_for_protocol(protocol, platform)
    return APPS.get(app or "", {}).get(normalize(platform))


def client_redirect_path(app: str, platform: str) -> str:
    return f"/v1/connect/app-download/{normalize(app)}/{normalize(platform)}"


def protocol_client_rows() -> dict[str, dict[str, tuple[str, str]]]:
    out: dict[str, dict[str, tuple[str, str]]] = {}
    for protocol, rows in PROTOCOL_CLIENT.items():
        matches = {}
        for platform, app in rows.items():
            data = APPS.get(app, {}).get(platform)
            if data:
                matches[platform] = (data[0], client_redirect_path(app, platform))
        if matches:
            out[protocol] = matches
    return out


def global_downloads() -> dict[str, list[dict[str, str]]]:
    """Only verified install destinations, one card per app on each OS."""
    result: dict[str, list[dict[str, str]]] = {}
    for platform in PLATFORMS:
        rows: list[dict[str, str]] = []
        used: set[str] = set()
        for protocol, mappings in PROTOCOL_CLIENT.items():
            app = mappings.get(platform)
            if not app or app in used:
                continue
            data = APPS.get(app, {}).get(platform)
            if not data:
                continue
            used.add(app)
            note = ("باز کردن صفحه رسمی نصب" if (
                platform == "macos" and app == "openconnect"
            ) else "نصب از فروشگاه رسمی" if (
                data[1].startswith("https://apps.apple.com") or
                data[1].startswith("https://play.google.com")
            ) else "دانلود مستقیم فایل نصب")
            rows.append({
                "name": data[0], "url": client_redirect_path(app, platform),
                "note": note,
            })
        for name, url, note in ALTERNATIVE_ASSETS.get(platform, []):
            rows.append({"name": name, "url": url, "note": note})
        result[platform] = rows
    return result
