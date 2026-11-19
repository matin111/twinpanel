#!/usr/bin/env python3
"""One-time guarded cleanup of obsolete TwinPanel RC GitHub Releases.

Deletes ONLY old panel RC releases. Git tags remain for source history.
Never touches TwinConnect app releases or current stable release.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

NEW_TAG = "v1.1.0"
OLD_PATTERN = re.compile(r"^v1\.1\.0-rc\.\d+$")
ASSET = "twinpanel-1.1.0-linux-x86_64.tar.gz"


def api(method: str, path: str, data: dict | None = None):
    token = os.environ["GH_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    body = json.dumps(data).encode("utf-8") if data is not None else None
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/{path}",
        data=body, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Content-Type": "application/json"} if body else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def planned_old_releases(releases: list[dict]) -> list[dict]:
    return sorted(
        (release for release in releases
         if OLD_PATTERN.fullmatch(str(release.get("tag_name") or ""))),
        key=lambda item: str(item["tag_name"]),
    )


def main() -> None:
    if os.getenv("CONFIRM_RELEASE_CLEANUP") != "v1.1.0-only":
        raise SystemExit("explicit cleanup confirmation missing")
    manifest_file = api("GET", "contents/releases/stable.json?ref=main")
    manifest = json.loads(base64.b64decode(
        str(manifest_file.get("content") or "").replace("\n", "")
    ).decode("utf-8"))
    if (manifest.get("version") != "1.1.0"
            or manifest.get("published") is not True
            or manifest.get("installable") is not True
            or f"/{NEW_TAG}/{ASSET}" not in str(
                (manifest.get("artifact") or {}).get("url") or "")):
        raise SystemExit("stable manifest does not point to v1.1.0; no deletion")
    stable = api("GET", f"releases/tags/{NEW_TAG}")
    if not any(
        asset.get("name") == ASSET and int(asset.get("size") or 0) > 1_000_000
        for asset in stable.get("assets") or []
    ):
        raise SystemExit("v1.1.0 package not present; no deletion")
    releases = []
    for page in range(1, 21):
        batch = api("GET", f"releases?per_page=100&page={page}")
        if not isinstance(batch, list):
            raise SystemExit("unexpected GitHub releases response")
        releases.extend(batch)
        if len(batch) < 100:
            break
    else:
        raise SystemExit("too many releases; pagination guard stopped cleanup")
    old = planned_old_releases(releases)
    if not old:
        print("No obsolete TwinPanel RC releases found.")
    if any(release.get("tag_name") == NEW_TAG for release in old):
        raise SystemExit("stable release unexpectedly selected")
    print(f"Guarded cleanup: {len(old)} old TwinPanel RC releases; "
          f"{len(releases)-len(old)} protected other releases.")
    with open("old-twinpanel-release-inventory.json", "w", encoding="utf-8") as file:
        json.dump([
            {"id": release["id"], "tag": release["tag_name"],
             "url": release.get("html_url")}
            for release in old
        ], file, indent=2)
    api("PATCH", f"releases/{stable['id']}",
        {"name": "TwinPanel v1.1.0 — شروع"})
    for index, release in enumerate(old, 1):
        try:
            api("DELETE", f"releases/{release['id']}")
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
        if index % 25 == 0 or index == len(old):
            print(f"Removed {index}/{len(old)} old releases")
        time.sleep(0.08)
    print("CLEANUP_COMPLETE: stable v1.1.0 and all TwinConnect releases retained.")


if __name__ == "__main__":
    main()
