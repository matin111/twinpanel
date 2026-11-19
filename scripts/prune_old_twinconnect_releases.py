#!/usr/bin/env python3
"""Keep only the latest manually published TwinConnect releases.

Preserved releases are explicitly pinned by tag and verified by author and
asset name before any deletion. Deletes GitHub Release objects only; Git tags
and repository source history are retained.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

KEEP = {
    "twinconnect-android-v1.0.0": {
        "author": "matin111",
        "asset": "app-arm64-v8a-release.apk",
    },
    "twinconnect-windows-v0.1.0-beta.1": {
        "author": "matin111",
        "asset": "TwinConnect-Windows-x64-Setup.exe",
    },
}
PREFIX = "twinconnect"


def api(method: str, path: str, data: dict | None = None):
    token = os.environ["GH_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Content-Type": "application/json"} if body else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def main() -> None:
    if os.getenv("CONFIRM_TWINCONNECT_CLEANUP") != "keep-two-manual":
        raise SystemExit("explicit TwinConnect cleanup confirmation missing")

    releases = []
    for page in range(1, 11):
        batch = api("GET", f"releases?per_page=100&page={page}")
        if not isinstance(batch, list):
            raise SystemExit("unexpected GitHub releases response")
        releases.extend(batch)
        if len(batch) < 100:
            break
    else:
        raise SystemExit("release pagination guard stopped cleanup")

    twin = [
        r for r in releases
        if str(r.get("tag_name") or "").lower().startswith(PREFIX)
        or "twinconnect" in str(r.get("name") or "").lower()
    ]
    by_tag = {r.get("tag_name"): r for r in twin}

    # Verify both pinned manual releases before deleting anything.
    for tag, expected in KEEP.items():
        release = by_tag.get(tag)
        if not release:
            raise SystemExit(f"required manual release missing: {tag}")
        if (release.get("author") or {}).get("login") != expected["author"]:
            raise SystemExit(f"unexpected author for protected release: {tag}")
        if not any(a.get("name") == expected["asset"] and
                   int(a.get("size") or 0) > 1_000_000
                   for a in release.get("assets") or []):
            raise SystemExit(f"expected installer missing from protected release: {tag}")

    # Every matching release except the two exact pinned releases is obsolete.
    obsolete = [r for r in twin if r.get("tag_name") not in KEEP]
    inventory = [
        {
            "id": r["id"],
            "tag": r.get("tag_name"),
            "name": r.get("name"),
            "author": (r.get("author") or {}).get("login"),
            "url": r.get("html_url"),
        }
        for r in obsolete
    ]
    with open("removed-twinconnect-release-inventory.json", "w", encoding="utf-8") as f:
        json.dump(inventory, f, ensure_ascii=False, indent=2)

    print(f"Verified {len(KEEP)} latest manual releases; "
          f"will remove {len(obsolete)} other TwinConnect releases.")
    for i, release in enumerate(obsolete, 1):
        try:
            api("DELETE", f"releases/{release['id']}")
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
        if i % 10 == 0 or i == len(obsolete):
            print(f"Removed {i}/{len(obsolete)} obsolete TwinConnect releases")
        time.sleep(0.08)

    print("CLEANUP_COMPLETE: both pinned manual releases and all Git tags retained.")


if __name__ == "__main__":
    main()
