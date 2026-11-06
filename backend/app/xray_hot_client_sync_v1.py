"""VLESS credential updates via Xray's localhost HandlerService, never a global restart.

The on-node script serializes writes, validates staged JSON, applies only
per-inbound user changes through the existing Xray HandlerService, and persists
the exact resulting clients atomically. Failed API operations rollback only
users touched by this request; they NEVER restart Xray or modify other VPNs.
"""
from __future__ import annotations

import uuid

from . import xray_modern_runtime


_REMOTE = r'''
import fcntl
import json
import os
import socket
import stat
import subprocess
import tempfile
from pathlib import Path

CLIENT_ID = __CLIENT_ID__
EMAIL = __EMAIL__
CONFIG = Path("/usr/local/etc/xray/config.json")
LOCK = Path("/run/twinpanel-xray-hot-user.lock")
XRAY = "/usr/local/bin/xray"
API = "--server=127.0.0.1:10085"


def _run(args, *, timeout=12):
    result = subprocess.run(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, check=False, timeout=timeout,
    )
    return result


def _api_add(tag, port, client):
    data = {"inbounds": [{
        "tag": tag,
        "port": int(port),
        "protocol": "vless",
        "settings": {"decryption": "none", "clients": [client]},
    }]}
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8",
            prefix="tp-xray-adu-", suffix=".json", delete=False,
        ) as stream:
            tmp = Path(stream.name)
            os.chmod(tmp, 0o600)
            json.dump(data, stream)
        result = _run([XRAY, "api", "adu", API, str(tmp)])
        if result.returncode != 0 or "Added 1 user(s) in total." not in result.stdout:
            raise RuntimeError("Xray live user add failed for inbound " + tag)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def _api_remove(tag, email):
    result = _run([XRAY, "api", "rmu", API, "-tag=" + tag, email])
    if result.returncode != 0 or "Removed 1 user(s) in total." not in result.stdout:
        raise RuntimeError("Xray live user remove failed for inbound " + tag)


def _api_confirm(tag, email, client_id):
    result = _run([
        XRAY, "api", "inbounduser", API,
        "-tag=" + tag, "-email=" + email,
    ])
    if result.returncode != 0 or client_id not in result.stdout:
        raise RuntimeError("Xray live user verification failed for inbound " + tag)


def _sync():
    original = CONFIG.read_bytes()
    doc = json.loads(original)
    metadata = CONFIG.stat()
    updated = []
    found = 0
    for inbound in doc.get("inbounds", []):
        if not isinstance(inbound, dict) or inbound.get("protocol") != "vless":
            continue
        found += 1
        tag = str(inbound.get("tag") or "")
        port = int(inbound.get("port") or 0)
        clients = inbound.get("settings", {}).get("clients")
        if not tag or not 1 <= port <= 65535 or not isinstance(clients, list):
            raise RuntimeError("invalid VLESS inbound during hot sync")
        if any(not isinstance(c, dict) for c in clients):
            raise RuntimeError("invalid VLESS client record during hot sync")
        matches = [c for c in clients if str(c.get("email") or "") == EMAIL]
        if len(matches) > 1:
            raise RuntimeError("duplicate VLESS account email in " + tag)
        previous = dict(matches[0]) if matches else None
        if (previous is not None
            and str(previous.get("id") or "") == CLIENT_ID
            and int(previous.get("level") or 0) == 0):
            continue
        clients[:] = [c for c in clients if str(c.get("email") or "") != EMAIL]
        client = {"id": CLIENT_ID, "email": EMAIL, "level": 0}
        clients.append(client)
        updated.append((tag, port, previous, client))

    if found < 3:
        raise RuntimeError("modern Xray VLESS inbounds incomplete")
    if not updated:
        print(json.dumps({
            "changed": False, "hot_applied": False,
            "updated_inbounds": found,
        }, separators=(",", ":")))
        return

    # Validate before touching either the running service or its config file.
    stage = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=CONFIG.parent,
            prefix="tp-xray-hot-", suffix=".json", delete=False,
        ) as stream:
            stage = Path(stream.name)
            json.dump(doc, stream, ensure_ascii=False, indent=2)
            stream.write("\\n")
        os.chown(stage, metadata.st_uid, metadata.st_gid)
        os.chmod(stage, stat.S_IMODE(metadata.st_mode))
        validate = _run([XRAY, "run", "-test", "-config", str(stage)], timeout=22)
        if validate.returncode != 0:
            raise RuntimeError("Xray staged config test failed")

        active = _run(["systemctl", "is-active", "--quiet", "xray"], timeout=5)
        if active.returncode != 0:
            raise RuntimeError("Xray inactive: refusing hot user provisioning")

        # An API error fails CLOSED. Do not sacrifice existing connections by
        # restarting Xray to rescue one new subscription.
        applied = []
        try:
            for tag, port, previous, client in updated:
                event = {"tag": tag, "port": port, "previous": previous,
                         "removed": False, "added": False}
                applied.append(event)
                if previous is not None:
                    _api_remove(tag, EMAIL)
                    event["removed"] = True
                _api_add(tag, port, client)
                event["added"] = True
                _api_confirm(tag, EMAIL, CLIENT_ID)

            if CONFIG.read_bytes() != original:
                raise RuntimeError("concurrent Xray config edit: refusing overwrite")
            os.replace(stage, CONFIG)
            stage = None
        except Exception:
            rollback_errors = []
            for event in reversed(applied):
                try:
                    if event["added"]:
                        _api_remove(event["tag"], EMAIL)
                    if event["removed"] and event["previous"] is not None:
                        _api_add(event["tag"], event["port"], event["previous"])
                except Exception:
                    rollback_errors.append(event["tag"])
            if rollback_errors:
                raise RuntimeError("VLESS hot sync failed and live rollback incomplete: " +
                                   ",".join(rollback_errors))
            raise

        # Existing caller treats changed=True as an instruction to RESTART
        # Xray. hot_applied is a hard guard against that legacy behavior.
        print(json.dumps({
            "changed": True, "hot_applied": True,
            "updated_inbounds": found, "hot_updated": len(updated),
        }, separators=(",", ":")))
    finally:
        if stage is not None:
            stage.unlink(missing_ok=True)


with LOCK.open("a+") as file:
    fcntl.flock(file.fileno(), fcntl.LOCK_EX)
    _sync()
'''


def hot_client_sync_script(client_id: str, email: str) -> str:
    """Render a node-local hot-update script with safely quoted values."""
    uuid.UUID(str(client_id))
    if not email or len(email) > 320 or "\n" in email or "\r" in email:
        raise ValueError("Invalid Xray client email")
    return (_REMOTE.replace("__CLIENT_ID__", repr(str(client_id)))
                   .replace("__EMAIL__", repr(email)))


_applied = False


def apply_xray_hot_client_sync_v1() -> None:
    global _applied
    if _applied:
        return
    xray_modern_runtime._client_sync_script = hot_client_sync_script
    _applied = True
    print("TWINPANEL_XRAY_HOT_CLIENT_SYNC_V1_ACTIVE api=localhost:10085 "
          "global_restart=forbidden persistent_config=atomic", flush=True)
