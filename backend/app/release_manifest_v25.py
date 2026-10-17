from __future__ import annotations

import base64
import json
import os
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

PRIMARY_MANIFEST_URL = (
    "https://raw.githubusercontent.com/"
    "matin111/twinpanel/main/releases/stable.json"
)
LEGACY_MANIFEST_URL = (
    "https://raw.githubusercontent.com/"
    "matin111/tp27-core/main/twinpanel/releases/stable.json"
)
GITHUB_API_MANIFEST_URL = (
    "https://api.github.com/repos/matin111/twinpanel/"
    "contents/releases/stable.json?ref=main"
)


def _cache_busted(url: str) -> str:
    """Avoid stale branch-backed manifests without changing the provider path."""
    try:
        parts = urlsplit(url)
        query = dict(parse_qsl(parts.query, keep_blank_values=True))
        query["twinpanel_check"] = str(int(time.time() // 15))
        return urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                urlencode(query),
                parts.fragment,
            )
        )
    except Exception:
        return url


def _decode_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError("INVALID_RELEASE_MANIFEST")

    # api.github.com /contents response. This is intentionally a fallback for
    # networks where raw.githubusercontent.com is filtered or intermittently
    # unreachable.
    if value.get("encoding") == "base64" and isinstance(value.get("content"), str):
        raw = str(value["content"]).replace("\n", "")
        try:
            decoded = base64.b64decode(raw).decode("utf-8")
            value = json.loads(decoded)
        except Exception as exc:
            raise RuntimeError("INVALID_GITHUB_CONTENT_MANIFEST") from exc

    if not isinstance(value, dict):
        raise RuntimeError("INVALID_RELEASE_MANIFEST")

    version = str(value.get("version") or "").strip()
    if not version:
        raise RuntimeError("RELEASE_VERSION_MISSING")

    return dict(value)


def _sources() -> list[str]:
    explicit = str(os.getenv("TWINPANEL_RELEASE_MANIFEST_URL", "")).strip()
    values = [
        explicit,
        PRIMARY_MANIFEST_URL,
        LEGACY_MANIFEST_URL,
        GITHUB_API_MANIFEST_URL,
    ]
    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output


def release_manifest_v25() -> dict[str, Any]:
    errors: list[str] = []

    headers = {
        "Accept": "application/vnd.github+json, application/json",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "User-Agent": "TwinPanel-Release-Checker/25",
    }

    for source in _sources():
        try:
            response = httpx.get(
                _cache_busted(source),
                headers=headers,
                timeout=httpx.Timeout(10.0, connect=5.0),
                follow_redirects=True,
            )
            response.raise_for_status()
            manifest = _decode_payload(response.json())
            manifest["manifest_source"] = source
            manifest.pop("error", None)
            return manifest
        except Exception as exc:
            errors.append(f"{type(exc).__name__}@{source}")

    # Keep the existing release_status contract, but make the failure explicit.
    # release_status will expose manifest_error to the UI and will not invent a
    # newer version when all providers are unreachable.
    from . import system_release as base

    return {
        "channel": os.getenv(
            "TWINPANEL_RELEASE_CHANNEL",
            base.DEFAULT_RELEASE_CHANNEL,
        ),
        "version": base.current_version(),
        "error": "MANIFEST_UNREACHABLE:" + ";".join(errors),
        "manifest_source": None,
    }
