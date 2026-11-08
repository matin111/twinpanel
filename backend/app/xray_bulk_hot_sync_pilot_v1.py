"""Opt-in, bounded Xray live-client prewarm. Never restarts or replaces inbounds.

This pilot installs clients into the existing VLESS inbounds in ONE staged
config validation and up to ONE HandlerService AddUsers call per inbound.
It deliberately does not alter subscription rows; the existing idempotent
backfill later publishes each profile in central DB.
"""
from __future__ import annotations

import re
import uuid

_MAX_CLIENTS = 10
_EMAIL = re.compile(r"mv-[1-9][0-9]*@twinpanel\Z")

_REMOTE = r"""
import fcntl
import json
import os
import re
import stat
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CLIENTS = __CLIENTS__
CONF = Path("/usr/local/etc/xray/config.json")
LOCK = Path("/run/twinpanel-xray-hot-user.lock")
XRAY = "/usr/local/bin/xray"
API = "--server=127.0.0.1:10085"

def run(argv, timeout=22):
    return subprocess.run(argv, text=True, capture_output=True,
                          timeout=timeout, check=False)

def api_add(tag, port, clients):
    snippet = {"inbounds": [{
        "tag": tag, "port": int(port), "protocol": "vless",
        "settings": {"decryption": "none", "clients": clients},
    }]}
    path = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf8", prefix="tp-bulk-adu-",
                suffix=".json", delete=False) as f:
            path = Path(f.name)
            os.chmod(path, 0o600)
            json.dump(snippet, f)
        res = run([XRAY, "api", "adu", API, str(path)])
        # A successful subprocess exit alone does not guarantee all clients.
        m = re.search(r"Added (\d+) user\(s\) in total", res.stdout)
        if res.returncode or not m or int(m.group(1)) != len(clients):
            raise RuntimeError("bulk live add incomplete")
    finally:
        if path is not None:
            path.unlink(missing_ok=True)

def api_remove(tag, email):
    res = run([XRAY, "api", "rmu", API, "-tag=" + tag, email])
    if res.returncode:
        raise RuntimeError("rollback API remove failed")

def verify(tag, email, client_id):
    res = run([XRAY, "api", "inbounduser", API,
               "-tag=" + tag, "-email=" + email])
    if res.returncode or client_id not in res.stdout:
        raise RuntimeError("live account verification failed")

def sync():
    if len(CLIENTS) < 1 or len(CLIENTS) > 10:
        raise RuntimeError("invalid pilot size")
    original = CONF.read_bytes()
    meta = CONF.stat()
    doc = json.loads(original)
    changed = []
    checked = 0
    for inbound in doc.get("inbounds", []):
        if not isinstance(inbound, dict) or inbound.get("protocol") != "vless":
            continue
        tag = inbound.get("tag")
        port = inbound.get("port")
        users = inbound.get("settings", {}).get("clients")
        if not tag or not isinstance(users, list) or not isinstance(port, int):
            raise RuntimeError("invalid VLESS inbound")
        if any(not isinstance(c, dict) for c in users):
            raise RuntimeError("invalid existing user")
        checked += 1
        by_email = {}
        by_uuid = {}
        for c in users:
            mail, ident = c.get("email"), c.get("id")
            if mail in by_email or ident in by_uuid:
                raise RuntimeError("duplicate existing VLESS user")
            by_email[mail] = c
            by_uuid[ident] = c
        additions = []
        for client_id, email in CLIENTS:
            current = by_email.get(email)
            if current is not None:
                if current.get("id") != client_id:
                    raise RuntimeError("UUID rotation forbidden")
                if (tag == "vless-tcp-reality-vision"
                        and current.get("flow") != "xtls-rprx-vision"):
                    raise RuntimeError("XRAY_VISION_EXISTING_FLOW_MISMATCH")
                continue
            if client_id in by_uuid:
                raise RuntimeError("duplicate UUID across emails")
            client = {"id": client_id, "email": email, "level": 0}
            if tag == "vless-tcp-reality-vision":
                client["flow"] = "xtls-rprx-vision"
            users.append(client)
            additions.append(client)
        if additions:
            changed.append((tag, port, additions))
    if checked < 3:
        raise RuntimeError("Xray VLESS inbounds incomplete")
    if not changed:
        print(json.dumps({"ok": True, "changed": False,
                          "inbounds": checked, "users_added": 0}))
        return
    stage = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf8",
                dir=CONF.parent, prefix=".tp-bulk-", suffix=".json",
                delete=False) as f:
            stage = Path(f.name)
            json.dump(doc, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.chown(stage, meta.st_uid, meta.st_gid)
        os.chmod(stage, stat.S_IMODE(meta.st_mode))
        res = run([XRAY, "run", "-test", "-config", str(stage)], timeout=22)
        if res.returncode:
            raise RuntimeError("staged Xray config invalid")
        if run(["systemctl", "is-active", "--quiet", "xray"], timeout=5).returncode:
            raise RuntimeError("Xray inactive; refusing update")
        # Track intended clients before invoking the API: partial additions
        # from a failed call must be eligible for user-scoped rollback.
        attempted = []
        try:
            for tag, port, additions in changed:
                attempted.extend((tag, c["email"]) for c in additions)
                api_add(tag, port, additions)
                # Independent read-only HandlerService checks can overlap.
                # Keep full per-user verification, rather than weakening
                # the canary to a sample when a larger batch is selected.
                with ThreadPoolExecutor(max_workers=min(8, len(additions))) as pool:
                    list(pool.map(
                        lambda client: verify(tag, client["email"], client["id"]),
                        additions,
                    ))
            if CONF.read_bytes() != original:
                raise RuntimeError("concurrent config edit; refusing overwrite")
            os.replace(stage, CONF)
            stage = None
        except Exception:
            rollback_failures = 0
            for tag, email in reversed(attempted):
                try:
                    api_remove(tag, email)
                except Exception:
                    rollback_failures += 1
            if rollback_failures:
                raise RuntimeError("bulk rollback incomplete; manual review required")
            raise
        print(json.dumps({"ok": True, "changed": True,
            "hot_applied": True, "inbounds": checked,
            "users_added": sum(len(x[2]) for x in changed)}))
    finally:
        if stage is not None:
            stage.unlink(missing_ok=True)

with LOCK.open("a+") as f:
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    sync()
"""


def bulk_hot_sync_script(entries: list[tuple[str, str]]) -> str:
    """Render a bounded, validated on-node Xray hot-apply script."""
    if not 1 <= len(entries) <= _MAX_CLIENTS:
        raise ValueError("pilot batch must contain 1..10 users")
    normalized: list[tuple[str, str]] = []
    for ident, email in entries:
        canon = str(uuid.UUID(str(ident)))
        mail = str(email)
        if not _EMAIL.fullmatch(mail):
            raise ValueError("email is not a TwinPanel subscription identity")
        normalized.append((canon, mail))
    if (len(set(x[0] for x in normalized)) != len(normalized)
            or len(set(x[1] for x in normalized)) != len(normalized)):
        raise ValueError("pilot batch has duplicate identity")
    return _REMOTE.replace("__CLIENTS__", repr(normalized))
