from __future__ import annotations

import json
import re
import time
import urllib.request
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse


router = APIRouter(tags=["public-connect-app-download-v34"])

_MARKER = "TWINPANEL_PUBLIC_CONNECT_APP_DOWNLOAD_V34"
_CACHE_TTL = 3600
_CACHE: dict[tuple[str, str], tuple[float, str]] = {}


@dataclass(frozen=True)
class GitHubAsset:
    repo: str
    pattern: str


_GITHUB: dict[tuple[str, str], GitHubAsset] = {
    ("karing", "windows"): GitHubAsset("KaringX/karing", r"_windows_x64\.exe$"),
    ("karing", "android"): GitHubAsset("KaringX/karing", r"_android_arm64-v8a\.apk$"),
    ("karing", "macos"): GitHubAsset("KaringX/karing", r"_macos_universal\.dmg$"),
    ("karing", "linux"): GitHubAsset("KaringX/karing", r"_linux_amd64\.AppImage$"),

    ("hiddify", "windows"): GitHubAsset("hiddify/hiddify-app", r"Hiddify-Windows-Setup-x64\.exe$"),
    ("hiddify", "android"): GitHubAsset("hiddify/hiddify-app", r"Hiddify-Android-universal\.apk$"),
    ("hiddify", "macos"): GitHubAsset("hiddify/hiddify-app", r"Hiddify-MacOS\.dmg$"),
    ("hiddify", "linux"): GitHubAsset("hiddify/hiddify-app", r"Hiddify-Linux-x64-AppImage\.AppImage$"),

    ("amneziawg", "windows"): GitHubAsset("amnezia-vpn/amneziawg-windows-client", r"amneziawg-amd64-.*\.msi$"),
    ("amneziawg", "android"): GitHubAsset("amnezia-vpn/amneziawg-android", r"AmneziaWG-.*\.apk$"),

    ("sudoku", "windows"): GitHubAsset("SUDOKU-ASCII/sudoku-desktop", r"windows-amd64\.exe$"),
    ("sudoku", "android"): GitHubAsset("SUDOKU-ASCII/sudoku-android", r"sudodroid-.*-universal\.apk$"),
    ("sudoku", "macos"): GitHubAsset("SUDOKU-ASCII/sudoku-desktop", r"darwin-(?:arm64|amd64)\.dmg$"),
}


_STATIC: dict[tuple[str, str], str] = {
    # Apple stores are direct install destinations, not project landing pages.
    ("hiddify", "ios"): "https://apps.apple.com/us/app/hiddify-proxy-vpn/id6596777532?platform=iphone",
    ("karing", "ios"): "https://apps.apple.com/us/app/karing/id6472431552",
    ("karing", "macos-store"): "https://apps.apple.com/us/app/karing/id6472431552",
    ("amneziawg", "ios"): "https://apps.apple.com/app/amneziawg/id6478942365",
    ("amneziawg", "macos"): "https://apps.apple.com/app/amneziawg/id6478942365",
    ("sudoku", "ios"): "https://apps.apple.com/us/app/anywhere-proxy/id6758235178",

    # Native WireGuard installers/store destinations.
    ("wireguard", "windows"): "https://download.wireguard.com/windows-client/wireguard-installer.exe",
    ("wireguard", "android"): "market://details?id=com.wireguard.android",
    ("wireguard", "ios"): "https://apps.apple.com/us/app/wireguard/id1441195209",
    ("wireguard", "macos"): "https://apps.apple.com/us/app/wireguard/id1451685025",

    # Direct OpenVPN install destinations.
    ("openvpn", "windows"): "https://build.openvpn.net/downloads/releases/OpenVPN-2.7.8-I002-amd64.msi",
    ("openvpn", "android"): "market://details?id=net.openvpn.openvpn",
    ("openvpn", "ios"): "https://apps.apple.com/us/app/openvpn-connect-openvpn-app/id590379981",

    # Cisco/OpenConnect is manual credential delivery. Keep a direct installer
    # instead of sending Windows users to a documentation/landing page.
    ("openconnect", "windows"): "https://github.com/openconnect/openconnect-gui/releases/download/v1.5.3/openconnect-gui-1.5.3-win32.exe",
    ("openconnect", "android"): "market://details?id=com.cisco.anyconnect.vpn.android.avf",
    ("openconnect", "ios"): "https://apps.apple.com/us/app/cisco-secure-client/id1135064690",

    # Official TrustTunnel Flutter client destinations for mobile/macOS. The
    # Windows GUI is the same community GUI already selected by TwinPanel.
    ("trusttunnel", "windows"): "https://raw.githubusercontent.com/blazuryk/TrustTunnel-GUI-Client/main/gui_client.exe",
    ("trusttunnel", "android"): "https://agrd.io/android_trusttunnel",
    ("trusttunnel", "ios"): "https://agrd.io/ios_trusttunnel",
    ("trusttunnel", "macos"): "https://agrd.io/macos_trusttunnel",
}


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _github_asset(spec: GitHubAsset) -> str:
    cache_key = (spec.repo, spec.pattern)
    now = time.time()
    cached = _CACHE.get(cache_key)
    if cached and now - cached[0] < _CACHE_TTL:
        return cached[1]

    request = urllib.request.Request(
        f"https://api.github.com/repos/{spec.repo}/releases/latest",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "TwinPanel-Public-Connect/34",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            payload: Any = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=502, detail="دانلود مستقیم برنامه موقتاً در دسترس نیست") from exc

    assets = payload.get("assets") if isinstance(payload, dict) else []
    pattern = re.compile(spec.pattern, re.I)
    for asset in assets if isinstance(assets, list) else []:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        if url and pattern.search(name):
            _CACHE[cache_key] = (now, url)
            return url

    raise HTTPException(status_code=404, detail="فایل مستقیم مناسب این دستگاه پیدا نشد")


@router.get("/app-download/{app}/{platform}", name="public_connect_app_download_v34")
def public_connect_app_download_v34(app: str, platform: str):
    """Redirect to an installable asset/store target; never to a project landing page."""
    app_key = _normalize(app)
    platform_key = _normalize(platform)
    if platform_key in {"iphone", "ipad"}:
        platform_key = "ios"

    direct = _STATIC.get((app_key, platform_key))
    if direct:
        return RedirectResponse(url=direct, status_code=307)

    spec = _GITHUB.get((app_key, platform_key))
    if spec:
        return RedirectResponse(url=_github_asset(spec), status_code=307)

    raise HTTPException(status_code=404, detail="دانلود مستقیم برای این برنامه و دستگاه تعریف نشده است")


__all__ = ["router", "_MARKER"]
