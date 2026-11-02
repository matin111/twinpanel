from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from jose import JWTError, jwt

PRODUCT_NAME = "TwinPanel"
DEFAULT_RELEASE_CHANNEL = "stable"
DEFAULT_MANIFEST_URL = (
    "https://raw.githubusercontent.com/"
    "matin111/tp27-core/main/twinpanel/releases/stable.json"
)
DEFAULT_GITHUB_URL = "https://github.com/matin111/tp27-core"

LICENSE_ROOT = Path("/var/lib/twinpanel-license")
LICENSE_STATE_FILE = LICENSE_ROOT / "state.json"
UPDATE_REQUEST_FILE = LICENSE_ROOT / "update-request.json"
UPDATE_STATE_FILE = LICENSE_ROOT / "update-state.json"
INSTALLATION_ID_FILE = Path("/etc/twinpanel/installation-id")
DEFAULT_PUBLIC_KEY_FILE = Path("/etc/twinpanel/license-public.pem")

ACTIVE_LICENSE_STATES = {
    "trial_active",
    "trial_expiring",
    "licensed",
    "license_expiring",
}
AUTHORITATIVE_BLOCKED_STATES = {"suspended", "revoked"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat()


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def license_enforced() -> bool:
    return _truthy(os.getenv("TWINPANEL_LICENSE_ENFORCE", "0"))


def offline_grace_seconds() -> int:
    try:
        return max(
            0,
            int(os.getenv("TWINPANEL_LICENSE_OFFLINE_GRACE_SECONDS", "172800")),
        )
    except Exception:
        return 172800


def _license_timeout() -> httpx.Timeout:
    try:
        total = max(2.0, float(os.getenv("TWINPANEL_LICENSE_TIMEOUT_SECONDS", "12")))
    except Exception:
        total = 12.0
    try:
        connect = max(1.0, float(os.getenv("TWINPANEL_LICENSE_CONNECT_TIMEOUT_SECONDS", "6")))
    except Exception:
        connect = 6.0
    return httpx.Timeout(total, connect=min(connect, total))


def _ensure_root() -> None:
    LICENSE_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(LICENSE_ROOT, 0o700)
    except OSError:
        pass


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    _ensure_root()
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            return value
    except Exception:
        pass
    return {}


def ensure_installation_id() -> str:
    try:
        value = INSTALLATION_ID_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value
    except Exception:
        pass

    INSTALLATION_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
    value = str(uuid.uuid4())
    tmp = Path(str(INSTALLATION_ID_FILE) + ".tmp")
    tmp.write_text(value + "\n", encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(INSTALLATION_ID_FILE)
    return value


def machine_fingerprint() -> str:
    values: list[str] = []
    for path in (
        Path("/etc/machine-id"),
        Path("/sys/class/dmi/id/product_uuid"),
        Path("/sys/class/dmi/id/board_serial"),
    ):
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore").strip()
            if raw and raw.lower() not in {"none", "unknown", "not specified"}:
                values.append(raw)
        except Exception:
            pass

    values.append(os.uname().machine)
    material = "|".join(values) or ensure_installation_id()
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def current_version() -> str:
    candidates = [
        Path(os.getenv("TWINPANEL_VERSION_FILE", "/opt/twinpanel/current/VERSION")),
        Path(__file__).resolve().parents[2] / "VERSION",
    ]
    for path in candidates:
        try:
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
        except Exception:
            pass
    return "0.0.0"


def _version_key(value: str) -> tuple[int, int, int, int, int]:
    raw = str(value or "").strip().lower().lstrip("v")
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:[-.]?([a-z]+)[.-]?(\d*)?)?", raw)
    if not match:
        return (0, 0, 0, -1, 0)

    major, minor, patch = [int(match.group(i) or 0) for i in (1, 2, 3)]
    label = match.group(4) or ""
    number = int(match.group(5) or 0)
    rank = {
        "": 4,
        "stable": 4,
        "release": 4,
        "rc": 3,
        "beta": 2,
        "preview": 1,
        "alpha": 1,
        "dev": 0,
    }.get(label, 0)
    return (major, minor, patch, rank, number)


def is_newer_version(candidate: str, installed: str) -> bool:
    return _version_key(candidate) > _version_key(installed)


def _license_api_url() -> str:
    return str(os.getenv("TWINPANEL_LICENSE_API_URL", "")).strip().rstrip("/")


def _license_ir_api_url() -> str:
    return str(os.getenv("TWINPANEL_LICENSE_IR_API_URL", "")).strip().rstrip("/")


def _license_endpoints() -> list[tuple[str, str]]:
    endpoints: list[tuple[str, str]] = []
    seen: set[str] = set()
    for source, base in (
        ("global", _license_api_url()),
        ("iran", _license_ir_api_url()),
    ):
        if base and base not in seen:
            endpoints.append((source, base))
            seen.add(base)
    return endpoints


def _public_key_path() -> Path:
    raw = str(
        os.getenv(
            "TWINPANEL_LICENSE_PUBLIC_KEY_FILE",
            str(DEFAULT_PUBLIC_KEY_FILE),
        )
    ).strip()
    return Path(raw or str(DEFAULT_PUBLIC_KEY_FILE))


def _vendor_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    endpoints = _license_endpoints()
    if not endpoints:
        raise RuntimeError("LICENSE_API_NOT_CONFIGURED")

    last_connectivity_error: Exception | None = None
    for source, base in endpoints:
        try:
            response = httpx.post(
                f"{base}{path}",
                json=payload,
                timeout=_license_timeout(),
                follow_redirects=True,
            )
            # A 4xx response is authoritative. Never bypass invalid/revoked/key
            # policy by asking another endpoint after the vendor rejected it.
            if 400 <= response.status_code < 500:
                response.raise_for_status()
            if response.status_code >= 500:
                last_connectivity_error = httpx.HTTPStatusError(
                    f"license endpoint {source} returned {response.status_code}",
                    request=response.request,
                    response=response,
                )
                continue
            response.raise_for_status()
            value = response.json()
            if not isinstance(value, dict):
                raise RuntimeError("INVALID_LICENSE_API_RESPONSE")
            value = dict(value)
            value["_validation_source"] = source
            return value
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            last_connectivity_error = exc
            continue

    if last_connectivity_error is not None:
        raise last_connectivity_error
    raise RuntimeError("LICENSE_SERVER_UNREACHABLE")


def _verify_entitlement(token: str) -> dict[str, Any]:
    token = str(token or "").strip()
    if not token:
        raise RuntimeError("SIGNED_ENTITLEMENT_MISSING")

    key_path = _public_key_path()
    if not key_path.is_file():
        if license_enforced():
            raise RuntimeError("LICENSE_PUBLIC_KEY_MISSING")
        return {}

    key = key_path.read_text(encoding="utf-8")
    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience="twinpanel",
            issuer="twinpanel-license",
            options={"verify_at_hash": False},
        )
    except JWTError as exc:
        raise RuntimeError("INVALID_SIGNED_ENTITLEMENT") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("INVALID_SIGNED_ENTITLEMENT")

    expected_installation = ensure_installation_id()
    token_installation = str(payload.get("installation_id") or "").strip()
    if token_installation and token_installation != expected_installation:
        raise RuntimeError("ENTITLEMENT_INSTALLATION_MISMATCH")

    return payload


def _state_from_vendor(payload: dict[str, Any]) -> dict[str, Any]:
    token = str(payload.get("signed_entitlement") or "").strip()
    verified = _verify_entitlement(token) if token else {}

    status = str(
        payload.get("status")
        or verified.get("status")
        or "unknown"
    ).strip()
    source = str(payload.get("_validation_source") or "global").strip()
    synced_at = _iso_now()

    result: dict[str, Any] = {
        "status": status,
        "installation_id": ensure_installation_id(),
        "signed_entitlement": token,
        "validated_at": synced_at,
        "last_successful_sync_at": synced_at,
        "validation": "online",
        "validation_source": source,
        "offline_mode": False,
        "edition": payload.get("edition") or verified.get("edition") or "standard",
        "release_channel": (
            payload.get("release_channel")
            or verified.get("release_channel")
            or DEFAULT_RELEASE_CHANNEL
        ),
        "expires_at": payload.get("expires_at") or verified.get("expires_at"),
        "trial_started_at": payload.get("trial_started_at") or verified.get("trial_started_at"),
        "trial_expires_at": payload.get("trial_expires_at") or verified.get("trial_expires_at"),
        "seconds_remaining": payload.get("seconds_remaining"),
        "features": payload.get("features") or verified.get("features") or [],
    }

    _atomic_json_write(LICENSE_STATE_FILE, result)
    return result


def load_license_state() -> dict[str, Any]:
    state = _read_json(LICENSE_STATE_FILE)
    if not state:
        return {
            "status": "unconfigured" if _license_endpoints() else "license_api_missing",
            "installation_id": ensure_installation_id(),
            "validation": "none",
            "validation_source": "none",
            "offline_mode": False,
        }
    return state


def _parse_iso(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _seconds_until_expiry(state: dict[str, Any]) -> int | None:
    for key in ("expires_at", "trial_expires_at"):
        value = _parse_iso(state.get(key))
        if value:
            return int((value - _utc_now()).total_seconds())
    raw = state.get("seconds_remaining")
    try:
        return int(raw) if raw is not None else None
    except Exception:
        return None


def _verified_offline_state(cached: dict[str, Any], exc: Exception) -> dict[str, Any]:
    state = dict(cached)
    token = str(state.get("signed_entitlement") or "").strip()
    try:
        verified = _verify_entitlement(token)
    except Exception as verify_exc:
        state["validation"] = "server_unreachable"
        state["validation_source"] = "none"
        state["offline_mode"] = True
        state["validation_error"] = type(verify_exc).__name__
        state["offline_grace_seconds_remaining"] = 0
        state["seconds_remaining"] = _seconds_until_expiry(state)
        return state

    signed_status = str(verified.get("status") or state.get("status") or "unknown").strip()
    if signed_status in AUTHORITATIVE_BLOCKED_STATES:
        state["status"] = signed_status
        state["validation"] = "offline_cache"
        state["validation_source"] = "offline_cache"
        state["offline_mode"] = True
        state["offline_grace_seconds_remaining"] = 0
        state["seconds_remaining"] = _seconds_until_expiry(state)
        return state

    validated_at = _parse_iso(state.get("validated_at"))
    age = int((_utc_now() - validated_at).total_seconds()) if validated_at else None
    remaining_grace = (
        max(0, offline_grace_seconds() - age)
        if age is not None
        else 0
    )
    state["validation"] = "offline_cache" if remaining_grace > 0 else "server_unreachable"
    state["validation_source"] = "offline_cache" if remaining_grace > 0 else "none"
    state["offline_mode"] = True
    state["validation_error"] = type(exc).__name__
    state["offline_grace_seconds_remaining"] = remaining_grace
    state["seconds_remaining"] = _seconds_until_expiry(state)
    return state


def license_allows_mutation() -> bool:
    if not license_enforced():
        return True

    state = load_license_state()
    status = str(state.get("status") or "").strip()
    if status not in ACTIVE_LICENSE_STATES:
        return False

    remaining = _seconds_until_expiry(state)
    if remaining is not None and remaining <= 0:
        return False

    validated_at = _parse_iso(state.get("validated_at"))
    if not validated_at:
        return False

    age = int((_utc_now() - validated_at).total_seconds())
    return age <= offline_grace_seconds()


def _validation_payload(state: dict[str, Any] | None = None) -> dict[str, Any]:
    state = state or load_license_state()
    return {
        "installation_id": ensure_installation_id(),
        "machine_fingerprint": machine_fingerprint(),
        "product": PRODUCT_NAME,
        "version": current_version(),
        "signed_entitlement": state.get("signed_entitlement"),
    }


def validate_license() -> dict[str, Any]:
    cached = load_license_state()
    try:
        payload = _vendor_post("/v1/license/validate", _validation_payload(cached))
        return _state_from_vendor(payload)
    except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
        # Only connectivity / 5xx failures reach this offline path. `_vendor_post`
        # raises 4xx immediately, so a vendor rejection can never be bypassed by
        # the Iran mirror or stale cache.
        if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None and exc.response.status_code < 500:
            raise
        return _verified_offline_state(cached, exc)


def start_trial() -> dict[str, Any]:
    payload = _vendor_post(
        "/v1/license/trial",
        {
            "installation_id": ensure_installation_id(),
            "machine_fingerprint": machine_fingerprint(),
            "product": PRODUCT_NAME,
            "version": current_version(),
        },
    )
    return _state_from_vendor(payload)


def activate_license(license_key: str) -> dict[str, Any]:
    key = str(license_key or "").strip()
    if len(key) < 8:
        raise ValueError("LICENSE_KEY_INVALID")

    payload = _vendor_post(
        "/v1/license/activate",
        {
            "license_key": key,
            "installation_id": ensure_installation_id(),
            "machine_fingerprint": machine_fingerprint(),
            "product": PRODUCT_NAME,
            "version": current_version(),
        },
    )
    return _state_from_vendor(payload)


def release_manifest() -> dict[str, Any]:
    url = str(
        os.getenv("TWINPANEL_RELEASE_MANIFEST_URL", DEFAULT_MANIFEST_URL)
    ).strip() or DEFAULT_MANIFEST_URL

    try:
        response = httpx.get(
            url,
            timeout=httpx.Timeout(8.0, connect=5.0),
            follow_redirects=True,
        )
        response.raise_for_status()
        value = response.json()
        if not isinstance(value, dict):
            raise RuntimeError("INVALID_RELEASE_MANIFEST")
        return value
    except Exception as exc:
        return {
            "channel": os.getenv("TWINPANEL_RELEASE_CHANNEL", DEFAULT_RELEASE_CHANNEL),
            "version": current_version(),
            "error": type(exc).__name__,
        }


def load_update_state() -> dict[str, Any]:
    state = _read_json(UPDATE_STATE_FILE)
    return state or {"state": "idle"}


def release_status(refresh_license_state: bool = False) -> dict[str, Any]:
    installed = current_version()
    manifest = release_manifest()
    latest = str(manifest.get("version") or installed).strip()

    # A missing vendor endpoint is a setup state, not a release-check failure.
    # Once an endpoint is configured, validation errors still propagate normally.
    if refresh_license_state and _license_endpoints():
        license_state = validate_license()
    else:
        license_state = load_license_state()
    remaining = _seconds_until_expiry(license_state)
    if remaining is not None:
        license_state = dict(license_state)
        license_state["seconds_remaining"] = remaining

    return {
        "product": PRODUCT_NAME,
        "current_version": installed,
        "latest_version": latest,
        "channel": manifest.get("channel") or DEFAULT_RELEASE_CHANNEL,
        "update_available": is_newer_version(latest, installed),
        "released_at": manifest.get("released_at"),
        "release_notes": manifest.get("notes") or {},
        "github_url": manifest.get("github_url") or DEFAULT_GITHUB_URL,
        "manifest_error": manifest.get("error"),
        "license": {
            **license_state,
            "enforced": license_enforced(),
        },
        "update": load_update_state(),
    }


def request_update() -> dict[str, Any]:
    status = release_status(refresh_license_state=True)
    if not status.get("update_available"):
        return {
            "ok": True,
            "started": False,
            "reason": "already_latest",
            "current_version": status.get("current_version"),
            "latest_version": status.get("latest_version"),
        }

    if license_enforced() and not license_allows_mutation():
        raise RuntimeError("LICENSE_REQUIRED_FOR_UPDATE")

    unit_path = Path("/etc/systemd/system/twinpanel-updater.service")
    if not unit_path.is_file():
        raise RuntimeError("UPDATER_SERVICE_NOT_INSTALLED")

    request = {
        "requested_at": _iso_now(),
        "requested_version": status.get("latest_version"),
        "channel": status.get("channel") or DEFAULT_RELEASE_CHANNEL,
    }
    _atomic_json_write(UPDATE_REQUEST_FILE, request)
    _atomic_json_write(
        UPDATE_STATE_FILE,
        {
            "state": "queued",
            "requested_at": request["requested_at"],
            "target_version": request["requested_version"],
        },
    )

    result = subprocess.run(
        ["systemctl", "start", "--no-block", "twinpanel-updater.service"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        _atomic_json_write(
            UPDATE_STATE_FILE,
            {
                "state": "failed",
                "failed_at": _iso_now(),
                "error": "SYSTEMD_START_FAILED",
            },
        )
        raise RuntimeError("UPDATER_START_FAILED")

    return {
        "ok": True,
        "started": True,
        "target_version": request["requested_version"],
    }


async def license_validation_loop() -> None:
    # Do not make startup depend on either vendor endpoint. The first
    # validation is deliberately delayed; outages fall back to the verified
    # signed cache for the configured bounded grace period.
    import asyncio

    await asyncio.sleep(20)
    while True:
        try:
            if _license_endpoints():
                validate_license()
        except Exception:
            pass
        await asyncio.sleep(900)
