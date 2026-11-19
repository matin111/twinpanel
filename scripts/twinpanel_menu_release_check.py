#!/usr/bin/env python3
"""Fast, read-only release check for the TwinPanel terminal menu.

This module deliberately does not import ``app``: importing that package
initializes VPN runtime patches and makes an interactive menu take seconds.
The actual update operation still uses app.system_release and its safeguards.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

OFFICIAL_RAW_MANIFEST = (
    "https://raw.githubusercontent.com/matin111/twinpanel/main/releases/stable.json"
)
LEGACY_RAW_MANIFEST = (
    "https://raw.githubusercontent.com/matin111/tp27-core/main/twinpanel/releases/stable.json"
)
DEFAULT_VERSION_FILE = "/opt/twinpanel/current/VERSION"
MAX_MANIFEST_BYTES = 131_072
HTTP_TIMEOUT_SECONDS = 2.0


def version_key(value: str) -> tuple[int, int, int, int, int]:
    """Mirror app.system_release._version_key without importing the app."""
    match = re.match(
        r"^(\d+)\.(\d+)\.(\d+)(?:[-.]?([a-z]+)[.-]?(\d*)?)?",
        str(value or "").strip().lower().lstrip("v"),
    )
    if not match:
        return (0, 0, 0, -1, 0)
    major, minor, patch = (int(match.group(i) or 0) for i in (1, 2, 3))
    label = match.group(4) or ""
    rank = {
        "": 4, "stable": 4, "release": 4, "rc": 3,
        "beta": 2, "preview": 1, "alpha": 1, "dev": 0,
    }.get(label, 0)
    return (major, minor, patch, rank, int(match.group(5) or 0))


def preferred_urls(configured: str) -> list[str]:
    """Prefer the canonical TwinPanel feed; honor vendor custom feeds."""
    if configured in ("", OFFICIAL_RAW_MANIFEST, LEGACY_RAW_MANIFEST):
        fallback = LEGACY_RAW_MANIFEST if configured == LEGACY_RAW_MANIFEST else None
        return [OFFICIAL_RAW_MANIFEST] + ([fallback] if fallback else [])
    return [configured]


def fetch_manifest(url: str, opener=urllib.request.urlopen) -> dict:
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("invalid release feed address")
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "TwinPanel-CLI/1"},
    )
    with opener(req, timeout=HTTP_TIMEOUT_SECONDS) as response:
        raw = response.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("release feed is too large")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict) or not str(data.get("version") or "").strip():
        raise ValueError("invalid release manifest")
    if data.get("published") is False or data.get("installable") is False:
        raise ValueError("release is not published")
    return data


def check_release(current: str, configured: str, opener=urllib.request.urlopen) -> tuple[str | None, str]:
    for url in preferred_urls(configured.strip()):
        try:
            data = fetch_manifest(url, opener=opener)
            latest = str(data["version"]).strip()
            return latest, ("AVAILABLE" if version_key(latest) > version_key(current) else "up to date")
        except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
            continue
    return None, "check unavailable"


def main() -> int:
    file = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_VERSION_FILE)
    try:
        current = file.read_text(encoding="utf-8").strip() or "unknown"
    except OSError:
        current = "unknown"
    configured = os.getenv("TWINPANEL_RELEASE_MANIFEST_URL", "")
    latest, result = check_release(current, configured)
    print("  Current :", current)
    print("  Latest  :", latest if latest else "unavailable")
    print("  Update  :", result)
    if latest is None:
        print("  Error   : release feed unreachable; try Refresh update check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
