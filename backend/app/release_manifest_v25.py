from __future__ import annotations

import base64
import json
import os
import threading
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

# TWINPANEL_RELEASE_MANIFEST_FAST_CACHE_V1
#
# /release/status is read by the admin navigation and update center. It must be
# a cheap local read after the first successful provider lookup; otherwise each
# navigation poll can wait on a filtered/stale upstream URL. Explicit
# /release/check invalidates this cache before resolving a fresh manifest.
MANIFEST_CACHE_TTL_SECONDS = 45.0
_manifest_cache: dict[str, Any] | None = None
_manifest_cache_at = 0.0
_manifest_lock = threading.Lock()


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

    # Old installs can still carry the legacy tp27-core URL in install.env.
    # Treat that exact legacy value as a fallback so a filtered/stale legacy
    # host cannot add a 10-12 second delay before the canonical TwinPanel repo.
    explicit_is_legacy = explicit.rstrip("/") == LEGACY_MANIFEST_URL.rstrip("/")

    values: list[str] = []
    if explicit and not explicit_is_legacy:
        values.append(explicit)

    values.extend(
        [
            PRIMARY_MANIFEST_URL,
            GITHUB_API_MANIFEST_URL,
            LEGACY_MANIFEST_URL,
        ]
    )

    if explicit_is_legacy:
        values.append(explicit)

    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output


def _cache_value(value: dict[str, Any]) -> dict[str, Any]:
    global _manifest_cache, _manifest_cache_at
    _manifest_cache = dict(value)
    _manifest_cache_at = time.monotonic()
    return dict(value)


def _cached_manifest() -> dict[str, Any] | None:
    if not _manifest_cache:
        return None
    age = time.monotonic() - _manifest_cache_at
    if age > MANIFEST_CACHE_TTL_SECONDS:
        return None
    cached = dict(_manifest_cache)
    cached["manifest_cached"] = True
    return cached


def invalidate_release_manifest_cache() -> None:
    """Force the next resolver call to perform a fresh provider lookup."""
    global _manifest_cache_at
    with _manifest_lock:
        _manifest_cache_at = 0.0


def release_manifest_v25() -> dict[str, Any]:
    cached = _cached_manifest()
    if cached is not None:
        return cached

    # Single-flight the provider lookup. The footer and nav can request status
    # at nearly the same moment; only one request should touch upstream.
    with _manifest_lock:
        cached = _cached_manifest()
        if cached is not None:
            return cached

        errors: list[str] = []
        headers = {
            "Accept": "application/vnd.github+json, application/json",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "User-Agent": "TwinPanel-Release-Checker/26",
        }

        for source in _sources():
            try:
                response = httpx.get(
                    _cache_busted(source),
                    headers=headers,
                    # A release check is interactive UI. Fail over quickly to
                    # the next provider rather than blocking the admin menu.
                    timeout=httpx.Timeout(4.0, connect=2.5),
                    follow_redirects=True,
                )
                response.raise_for_status()
                manifest = _decode_payload(response.json())
                manifest["manifest_source"] = source
                manifest["manifest_cached"] = False
                manifest.pop("error", None)
                return _cache_value(manifest)
            except Exception as exc:
                errors.append(f"{type(exc).__name__}@{source}")

        # If providers are temporarily unreachable, a previously successful
        # manifest is safer and much more useful than making every admin poll
        # block. Mark it stale so the API can expose that fact to the UI.
        if _manifest_cache:
            stale = dict(_manifest_cache)
            stale["manifest_cached"] = True
            stale["manifest_stale"] = True
            stale["error"] = "MANIFEST_STALE:" + ";".join(errors)
            return stale

        from . import system_release as base

        return {
            "channel": os.getenv(
                "TWINPANEL_RELEASE_CHANNEL",
                base.DEFAULT_RELEASE_CHANNEL,
            ),
            "version": base.current_version(),
            "error": "MANIFEST_UNREACHABLE:" + ";".join(errors),
            "manifest_source": None,
            "manifest_cached": False,
        }
