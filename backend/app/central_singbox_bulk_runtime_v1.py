"""Staged, O(N) sing-box identity merge on ONE hidden Exit.

Only the caller chooses valid central entitlements. A single SSH stdin
transfer creates the credential snapshot, validates it and restarts the
node's sing-box ONCE. Existing live nodes never use this staging adapter.
"""
from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

from .modern_protocol_runtime import CONFIG_PATH, SERVICE_NAME, STATE_PATH
from .modern_protocol_runtime_v2 import (
    SHADOWTLS_INNER_METHOD, SHADOWTLS_INNER_TAG, SINGBOX_PROTOCOLS, TAGS,
)
from .singbox_subscription_accounts import (
    SingBoxAccountSecret, _user_record,
)


def remote_script(
    *,
    config_path: str = CONFIG_PATH,
    state_path: str = STATE_PATH,
    service_name: str = SERVICE_NAME,
    binary_path: str = "/usr/local/bin/twinpanel-sing-box",
    lock_path: str = "/run/twinpanel-singbox-batch.lock",
) -> str:
    src = r'''import copy
import fcntl
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CONFIG = Path(__CONFIG__)
STATE = Path(__STATE__)
SERVICE = __SERVICE__
BINARY = __BINARY__
LOCK = __LOCK__
TAGS = __TAGS__
SHADOWTLS_INNER_TAG = __INNER_TAG__
SHADOWTLS_INNER_METHOD = __INNER_METHOD__
SENTINEL = "__twinpanel_revoked__"

payload = json.load(sys.stdin)
updates = payload.get("updates")
if not isinstance(updates,list) or not 0 < len(updates) <= 30000:
    raise SystemExit("INVALID_SINGBOX_BATCH")
by_proto = {}
for row in updates:
    p = row.get("protocol")
    username = row.get("username")
    record = row.get("record")
    if p not in TAGS or not isinstance(username,str) or not username:
        raise SystemExit("INVALID_SINGBOX_PROTOCOL_OR_USERNAME")
    if not isinstance(record,dict):
        raise SystemExit("INVALID_SINGBOX_IDENTITY")
    key = "username" if p in ("naive","socks5") else "name"
    if record.get(key) != username:
        raise SystemExit("MISMATCHED_SINGBOX_IDENTITY")
    group = by_proto.setdefault(p, {})
    if username in group:
        raise SystemExit("DUPLICATE_SINGBOX_IDENTITY")
    group[username] = record

LOCK_PARENT = Path(LOCK).parent
LOCK_PARENT.mkdir(parents=True,exist_ok=True)
with open(LOCK,"a+") as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    if CONFIG.is_symlink() or not CONFIG.is_file():
        raise SystemExit("SINGBOX_CONFIG_NOT_A_REGULAR_FILE")
    old_config_text = CONFIG.read_text(encoding="utf-8")
    doc = json.loads(old_config_text)
    if not isinstance(doc,dict) or not isinstance(doc.get("inbounds"),list):
        raise SystemExit("INVALID_SINGBOX_CONFIG")
    original = copy.deepcopy(doc)
    state_original = STATE.read_text(encoding="utf-8") if STATE.exists() else None
    state = json.loads(state_original) if state_original else {}
    if not isinstance(state,dict):
        raise SystemExit("INVALID_SINGBOX_STATE")
    inbound_map = {
        (row.get("tag"),row.get("type")):row
        for row in doc["inbounds"] if isinstance(row,dict)
    }
    for protocol, records in by_proto.items():
        kind = "socks" if protocol == "socks5" else protocol
        inbound = inbound_map.get((TAGS[protocol],kind))
        if not isinstance(inbound,dict):
            raise SystemExit("MANAGED_SINGBOX_INBOUND_NOT_FOUND")
        key = "username" if protocol in ("naive","socks5") else "name"
        previous = inbound.get("users")
        previous = previous if isinstance(previous,list) else []
        current = {
            u.get(key):u for u in previous
            if isinstance(u,dict) and isinstance(u.get(key),str)
        }
        unchanged = (
            len(current) == len(previous)
            and not any(str(k).startswith(SENTINEL) for k in current)
            and all(current.get(k)==v for k,v in records.items())
        )
        if not unchanged:
            keep = [
                u for u in previous
                if not isinstance(u,dict) or (
                    u.get(key) not in records and
                    not str(u.get(key) or "").startswith(SENTINEL)
                )
            ]
            inbound["users"] = keep + list(records.values())
        if protocol == "shadowtls":
            section = dict(state.get("shadowtls") or {})
            section.setdefault("inner_password", secrets.token_urlsafe(32))
            state["shadowtls"] = section
            inbound["detour"] = SHADOWTLS_INNER_TAG
            inner = {
                "type":"shadowsocks", "tag":SHADOWTLS_INNER_TAG,
                "listen":"127.0.0.1","method":SHADOWTLS_INNER_METHOD,
                "password":section["inner_password"],
            }
            existing = next((
                item for item in doc["inbounds"]
                if isinstance(item,dict) and item.get("tag")==SHADOWTLS_INNER_TAG
            ),None)
            if existing is None:
                doc["inbounds"].append(inner)
            else:
                existing.clear()
                existing.update(inner)

    changed = doc != original or (
        state_original is None and "shadowtls" in by_proto
    )
    if not changed:
        print(json.dumps({"ok":True,"accounts":len(updates),"changed":False,"restarted":False}))
        raise SystemExit(0)

    backup_dir = CONFIG.parent / ".twinpanel-central-singbox-backups"
    backup_dir.mkdir(mode=0o700,exist_ok=True)
    os.chmod(backup_dir,0o700)
    backup = backup_dir / ("pre-bulk-"+str(time.time_ns())+".json")
    shutil.copy2(CONFIG,backup)
    os.chmod(backup,0o600)
    fd,tmp=tempfile.mkstemp(prefix=".central-singbox-",dir=str(CONFIG.parent))
    state_tmp=None
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as out:
            json.dump(doc,out,ensure_ascii=False,indent=2)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        validated=subprocess.run([BINARY,"check","-c",tmp],timeout=180,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
        if validated.returncode:
            raise SystemExit("SINGBOX_BATCH_CONFIG_INVALID")
        if "shadowtls" in by_proto:
            STATE.parent.mkdir(parents=True,exist_ok=True)
            sfd,state_tmp=tempfile.mkstemp(prefix=".central-shadowtls-",dir=str(STATE.parent))
            os.fchmod(sfd,0o600)
            with os.fdopen(sfd,"w",encoding="utf-8") as out:
                json.dump(state,out,ensure_ascii=False,indent=2)
                out.write("\n")
                out.flush()
                os.fsync(out.fileno())
        os.replace(tmp,CONFIG)
        if state_tmp:
            os.replace(state_tmp,STATE)
        started=subprocess.run(["systemctl","restart",SERVICE+".service"],timeout=70,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
        healthy=subprocess.run(["systemctl","is-active","--quiet",SERVICE+".service"],
            timeout=15,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
        if started.returncode or healthy.returncode:
            # Roll back both config and inner secret; do not disclose either.
            shutil.copy2(backup,CONFIG)
            os.chmod(CONFIG,0o600)
            if state_original is not None:
                STATE.write_text(state_original,encoding="utf-8")
                os.chmod(STATE,0o600)
            subprocess.run(["systemctl","restart",SERVICE+".service"],timeout=70,
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
            raise SystemExit("SINGBOX_BATCH_RESTART_FAILED_ROLLED_BACK")
    finally:
        for path in (tmp,state_tmp):
            if path and os.path.exists(path):
                os.unlink(path)

print(json.dumps({"ok":True,"accounts":len(updates),"changed":True,"restarted":True}))
'''
    replacements = {
        "__CONFIG__": repr(config_path),
        "__STATE__": repr(state_path),
        "__SERVICE__": repr(service_name),
        "__BINARY__": repr(binary_path),
        "__LOCK__": repr(lock_path),
        "__TAGS__": repr({str(k): str(v) for k, v in TAGS.items()}),
        "__INNER_TAG__": repr(SHADOWTLS_INNER_TAG),
        "__INNER_METHOD__": repr(SHADOWTLS_INNER_METHOD),
    }
    for marker, value in replacements.items():
        src = src.replace(marker, value)
    return src


async def apply_bulk(
    conn: Any,
    secrets: list[SingBoxAccountSecret],
) -> dict[str, Any]:
    if not 1 <= len(secrets) <= 30000:
        raise ValueError("central sing-box batch must contain 1..30000 identities")
    updates = []
    duplicates = set()
    for secret in secrets:
        if secret.protocol not in SINGBOX_PROTOCOLS or not secret.username:
            raise ValueError("invalid staged sing-box identity")
        key = (secret.protocol, secret.username)
        if key in duplicates:
            raise ValueError("duplicate staged sing-box identity")
        duplicates.add(key)
        updates.append({
            "protocol":secret.protocol, "username":secret.username,
            "record":_user_record(secret),
        })
    source = base64.b64encode(remote_script().encode("utf-8")).decode("ascii")
    process = await asyncio.wait_for(
        conn.create_process("python3 -c \"$(printf '%s' '"+source+"' | base64 -d)\""),
        timeout=30,
    )
    process.stdin.write(json.dumps({"updates":updates},ensure_ascii=False))
    process.stdin.write_eof()
    outcome = await asyncio.wait_for(process.wait(), timeout=550)
    if outcome.exit_status:
        raise RuntimeError("CENTRAL_SINGBOX_REMOTE_STAGE_FAILED")
    try:
        result = json.loads((outcome.stdout or "").strip().splitlines()[-1])
    except (ValueError,IndexError):
        raise RuntimeError("CENTRAL_SINGBOX_CONFIRMATION_MISSING")
    if not result.get("ok") or int(result.get("accounts") or 0) != len(secrets):
        raise RuntimeError("CENTRAL_SINGBOX_CONFIRMATION_MISMATCH")
    return result
