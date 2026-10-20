from __future__ import annotations

import base64
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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

# TWINPANEL_RELEASE_MANIFEST_FAST_CACHE_V2
#
# Real controller paths can reach GitHub more slowly than a desktop browser.
# The public updater already tolerates that reality with a 20 second manifest
# timeout. The release checker used to allow only 4 seconds per provider, so a
# controller which needed ~10 seconds to reach GitHub could successfully install
# a release while the admin navigation kept serving an old cached manifest.
#
# Normal /release/status reads therefore use stale-while-revalidate: once a
# successful manifest exists, an expired entry is returned immediately while a
# single background refresh gets a larger bounded network budget. Explicit
# /release/check and /update can call refresh_release_manifest_cache() when they
# need a fresh provider result before returning.
MANIFEST_CACHE_TTL_SECONDS = 45.0
CANONICAL_PROVIDER_TIMEOUT_SECONDS = 14.0
CANONICAL_CONNECT_TIMEOUT_SECONDS = 4.0
LEGACY_PROVIDER_TIMEOUT_SECONDS = 8.0
LEGACY_CONNECT_TIMEOUT_SECONDS = 3.0

_manifest_cache: dict[str, Any] | None = None
_manifest_cache_at = 0.0
_manifest_refreshing = False
_manifest_lock = threading.RLock()
_manifest_refresh_lock = threading.Lock()


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


def _explicit_source() -> str:
    return str(os.getenv("TWINPANEL_RELEASE_MANIFEST_URL", "")).strip()


def _canonical_sources() -> list[str]:
    explicit = _explicit_source()
    explicit_is_legacy = explicit.rstrip("/") == LEGACY_MANIFEST_URL.rstrip("/")

    values: list[str] = []
    if explicit and not explicit_is_legacy:
        values.append(explicit)
    values.extend([PRIMARY_MANIFEST_URL, GITHUB_API_MANIFEST_URL])

    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output


def _legacy_sources() -> list[str]:
    explicit = _explicit_source()
    values = [LEGACY_MANIFEST_URL]
    if explicit.rstrip("/") == LEGACY_MANIFEST_URL.rstrip("/"):
        values.append(explicit)

    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output


def _cache_value(value: dict[str, Any]) -> dict[str, Any]:
    global _manifest_cache, _manifest_cache_at
    with _manifest_lock:
        _manifest_cache = dict(value)
        _manifest_cache_at = time.monotonic()
    return dict(value)


def _cached_manifest() -> dict[str, Any] | None:
    with _manifest_lock:
        if not _manifest_cache:
            return None
        age = time.monotonic() - _manifest_cache_at
        if age > MANIFEST_CACHE_TTL_SECONDS:
            return None
        cached = dict(_manifest_cache)
    cached["manifest_cached"] = True
    cached["manifest_stale"] = False
    cached["manifest_refreshing"] = False
    return cached


def _stale_manifest(*, refreshing: bool) -> dict[str, Any] | None:
    with _manifest_lock:
        if not _manifest_cache:
            return None
        stale = dict(_manifest_cache)
    stale["manifest_cached"] = True
    stale["manifest_stale"] = True
    stale["manifest_refreshing"] = refreshing
    return stale


def invalidate_release_manifest_cache() -> None:
    """Expire the current cache without discarding the last known-good value."""
    global _manifest_cache_at
    with _manifest_lock:
        _manifest_cache_at = 0.0


def _headers() -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json, application/json",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "User-Agent": "TwinPanel-Release-Checker/80",
    }


def _fetch_source(
    source: str,
    *,
    timeout_seconds: float,
    connect_timeout_seconds: float,
) -> dict[str, Any]:
    response = httpx.get(
        _cache_busted(source),
        headers=_headers(),
        timeout=httpx.Timeout(
            timeout_seconds,
            connect=connect_timeout_seconds,
        ),
        follow_redirects=True,
    )
    response.raise_for_status()
    manifest = _decode_payload(response.json())
    manifest["manifest_source"] = source
    manifest["manifest_cached"] = False
    manifest["manifest_stale"] = False
    manifest["manifest_refreshing"] = False
    manifest.pop("error", None)
    return manifest


def _fetch_canonical_race() -> tuple[dict[str, Any] | None, list[str]]:
    """Race canonical providers so a slow/filtered endpoint cannot serialize delay."""
    sources = _canonical_sources()
    if not sources:
        return None, []

    errors: list[str] = []
    executor = ThreadPoolExecutor(
        max_workers=max(1, len(sources)),
        thread_name_prefix="twinpanel-release-provider",
    )
    futures = {
        executor.submit(
            _fetch_source,
            source,
            timeout_seconds=CANONICAL_PROVIDER_TIMEOUT_SECONDS,
            connect_timeout_seconds=CANONICAL_CONNECT_TIMEOUT_SECONDS,
        ): source
        for source in sources
    }

    try:
        for future in as_completed(futures):
            source = futures[future]
            try:
                manifest = future.result()
            except Exception as exc:
                errors.append(f"{type(exc).__name__}@{source}")
                continue

            for pending in futures:
                if pending is not future:
                    pending.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            return manifest, errors
    finally:
        # If every provider failed, all futures have already completed. If a
        # successful provider returned early, shutdown above deliberately does
        # not wait for another in-flight request to hit its bounded timeout.
        if all(future.done() for future in futures):
            executor.shutdown(wait=True, cancel_futures=True)

    return None, errors


def _refresh_manifest_network() -> dict[str, Any]:
    manifest, errors = _fetch_canonical_race()
    if manifest is not None:
        return _cache_value(manifest)

    for source in _legacy_sources():
        try:
            manifest = _fetch_source(
                source,
                timeout_seconds=LEGACY_PROVIDER_TIMEOUT_SECONDS,
                connect_timeout_seconds=LEGACY_CONNECT_TIMEOUT_SECONDS,
            )
            manifest["manifest_legacy_source"] = True
            return _cache_value(manifest)
        except Exception as exc:
            errors.append(f"{type(exc).__name__}@{source}")

    stale = _stale_manifest(refreshing=False)
    if stale is not None:
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
        "manifest_stale": True,
        "manifest_refreshing": False,
    }


def refresh_release_manifest_cache() -> dict[str, Any]:
    """Synchronously fetch a fresh manifest using the slow-path network budget."""
    with _manifest_refresh_lock:
        return _refresh_manifest_network()


def _start_background_refresh() -> None:
    global _manifest_refreshing

    with _manifest_lock:
        if _manifest_refreshing:
            return
        _manifest_refreshing = True

    def runner() -> None:
        global _manifest_refreshing
        try:
            refresh_release_manifest_cache()
        finally:
            with _manifest_lock:
                _manifest_refreshing = False

    threading.Thread(
        target=runner,
        name="twinpanel-release-refresh",
        daemon=True,
    ).start()


def release_manifest_v25() -> dict[str, Any]:
    cached = _cached_manifest()
    if cached is not None:
        return cached

    # Keep normal nav/status polling instant. Once the cache expires, return the
    # last known-good release immediately and refresh it in one background job.
    stale = _stale_manifest(refreshing=True)
    if stale is not None:
        _start_background_refresh()
        return stale

    # First process start has no cache yet. Do not make every admin page wait on
    # a restricted GitHub route; seed asynchronously and let the next 15 second
    # status poll consume the fresh value. Explicit /release/check remains the
    # synchronous path when the admin requests an immediate provider check.
    _start_background_refresh()

    from . import system_release as base

    return {
        "channel": os.getenv(
            "TWINPANEL_RELEASE_CHANNEL",
            base.DEFAULT_RELEASE_CHANNEL,
        ),
        "version": base.current_version(),
        "manifest_source": None,
        "manifest_cached": False,
        "manifest_stale": True,
        "manifest_refreshing": True,
    }
