"""Stage TrustTunnel users with one management SSH and one service restart.

The remote runtime preserves existing accounts, uses credentials already
persisted centrally, and exports real tt:// links through the installed
TrustTunnel CLI. No guessed link format and no per-user SSH/restart.
"""
from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

from .central_mieru_bulk_runtime_v1 import verify_accounts


def remote_source(
    *,
    state="/etc/twinpanel/standalone/accounts/trusttunnel.json",
    credentials="/etc/twinpanel/standalone/trusttunnel/credentials.toml",
    vpn="/etc/twinpanel/standalone/trusttunnel/vpn.toml",
    hosts="/etc/twinpanel/standalone/trusttunnel/hosts.toml",
    executable="/opt/twinpanel/trusttunnel/trusttunnel_endpoint",
    service="twinpanel-trusttunnel.service",
) -> str:
    program = r'''import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

STATE=Path(__STATE__)
CREDS=Path(__CREDS__)
VPN=Path(__VPN__)
HOSTS=Path(__HOSTS__)
BINARY=Path(__EXEC__)
SERVICE=__SERVICE__
payload=json.load(sys.stdin)
incoming=payload.get("accounts")
endpoint=payload.get("endpoint")
if not isinstance(incoming,list) or not 1<=len(incoming)<=3000:
    raise SystemExit("TRUST_BULK_INVALID_COUNT")
if not isinstance(endpoint,str) or not endpoint or len(endpoint)>260:
    raise SystemExit("TRUST_BULK_INVALID_ENDPOINT")
names=set()
for row in incoming:
    name=row.get("username") if isinstance(row,dict) else None
    password=row.get("password") if isinstance(row,dict) else None
    if (not isinstance(name,str) or not name.startswith("tp-sub-")
        or not name[7:].isdigit() or name in names
        or not isinstance(password,str) or not 8<=len(password)<=256):
        raise SystemExit("TRUST_BULK_INVALID_ACCOUNT")
    names.add(name)
if any(p.is_symlink() for p in (STATE,CREDS,VPN,HOSTS,BINARY)):
    raise SystemExit("TRUST_BULK_SYMLINK")
if not CREDS.is_file() or not VPN.is_file() or not HOSTS.is_file() or not BINARY.is_file():
    raise SystemExit("TRUST_BULK_RUNTIME_MISSING")
lock=CREDS.parent/".central-trust-bulk.lock"
with open(lock,"a+") as mutex:
    fcntl.flock(mutex,fcntl.LOCK_EX)
    existing=json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    if not isinstance(existing,dict):
        raise SystemExit("TRUST_BULK_STATE_INVALID")
    for row in incoming:
        name=row["username"]; secret=row["password"]
        old=existing.get(name)
        if old is not None and (not isinstance(old,dict) or old.get("password")!=secret):
            raise SystemExit("TRUST_BULK_IDENTITY_CONFLICT")
        existing[name]={"username":name,"password":secret}
    output=[]
    for row in existing.values():
        if not isinstance(row,dict) or not isinstance(row.get("username"),str) or not isinstance(row.get("password"),str):
            raise SystemExit("TRUST_BULK_EXISTING_ACCOUNT_INVALID")
        output += [
            "[[client]]", "username = "+json.dumps(row["username"]),
            "password = "+json.dumps(row["password"]),
            "max_http2_conns = 4", "max_http3_conns = 4", "",
        ]
    new_state=json.dumps(existing,ensure_ascii=False,separators=(",",":"))+"\\n"
    new_creds="\\n".join(output)+"\\n"
    changed=(not STATE.exists() or STATE.read_text(encoding="utf-8")!=new_state
             or CREDS.read_text(encoding="utf-8")!=new_creds)
    STATE.parent.mkdir(parents=True,exist_ok=True)
    pairs=[]
    for target,content in ((STATE,new_state),(CREDS,new_creds)):
        fd,stage=tempfile.mkstemp(prefix=".trust-stage-",dir=str(target.parent))
        os.fchmod(fd,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            stream.write(content)
            stream.flush(); os.fsync(stream.fileno())
        pairs.append((target,stage))
    originals={}
    try:
        for target,_ in pairs:
            originals[target]=target.read_bytes() if target.exists() else None
        if changed:
            for target,stage in pairs:
                os.replace(stage,target)
            restarted=subprocess.run(
                ["systemctl","restart",SERVICE],stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,timeout=120,check=False)
            status=subprocess.run(["systemctl","is-active","--quiet",SERVICE],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                timeout=20,check=False)
            if restarted.returncode or status.returncode:
                raise RuntimeError("TRUST_BULK_RESTART_FAILED")
        links={}
        for row in incoming:
            name=row["username"]
            exported=subprocess.run(
                [str(BINARY),str(VPN),str(HOSTS),"-c",name,"-a",endpoint,
                 "--format","deeplink"],
                capture_output=True,text=True,timeout=30,check=False)
            link=next((line.strip() for line in exported.stdout.splitlines()
                       if line.strip().startswith("tt://")),"")
            if exported.returncode or not link or len(link)>16384:
                raise RuntimeError("TRUST_BULK_EXPORT_FAILED")
            links[name]=link
    except BaseException:
        if changed:
            for target,data in originals.items():
                if data is None:
                    if target.exists(): target.unlink()
                else:
                    fd,temp=tempfile.mkstemp(prefix=".trust-restore-",dir=str(target.parent))
                    with os.fdopen(fd,"wb") as stream:
                        stream.write(data)
                    os.chmod(temp,0o600)
                    os.replace(temp,target)
            rollback=subprocess.run(["systemctl","restart",SERVICE],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                timeout=120,check=False)
            if rollback.returncode:
                raise SystemExit("TRUST_BULK_ROLLBACK_FAILED")
        raise
    finally:
        for _,stage in pairs:
            if os.path.exists(stage): os.unlink(stage)
print(json.dumps({"ok":True,"applied":len(incoming),"changed":changed,
                  "links":links},separators=(",",":")))
'''
    replacements = {
        "__STATE__":repr(state),
        "__CREDS__":repr(credentials),
        "__VPN__":repr(vpn),
        "__HOSTS__":repr(hosts),
        "__EXEC__":repr(executable),
        "__SERVICE__":repr(service),
    }
    for key, value in replacements.items():
        program=program.replace(key,value)
    return program


async def apply_bulk(conn: Any, accounts: list[dict[str,str]], endpoint: str) -> dict[str,Any]:
    verify_accounts(accounts)
    if not endpoint or len(endpoint)>260:
        raise ValueError("TRUST_BULK_ENDPOINT_INVALID")
    program=base64.b64encode(remote_source().encode()).decode("ascii")
    process=await asyncio.wait_for(
        conn.create_process("python3 -c \"$(printf '%s' '"+program+"' | base64 -d)\""),
        timeout=25,
    )
    process.stdin.write(json.dumps({"accounts":accounts,"endpoint":endpoint}))
    process.stdin.write_eof()
    result=await asyncio.wait_for(process.wait(),timeout=1200)
    if result.exit_status:
        # Only accept a fixed error-code token from the remote process.
        # Never include stdout/stderr or credentials in logs.
        import re
        diagnostics = str(result.stderr or "")
        tokens = re.findall(r"\\b(?:TRUST_[A-Z0-9_]+|TRUST_[A-Z0-9_]+)\\b", diagnostics)
        code = tokens[-1] if tokens else "REMOTE_UNKNOWN"
        raise RuntimeError("TRUST_BULK_REMOTE_FAILED:"+code)
    try:
        ack=json.loads((result.stdout or "").strip().splitlines()[-1])
    except (ValueError,IndexError) as exc:
        raise RuntimeError("TRUST_BULK_ACK_INVALID") from exc
    expected={row["username"] for row in accounts}
    actual=ack.get("links")
    if (ack.get("ok") is not True or ack.get("applied")!=len(accounts)
            or not isinstance(actual,dict) or set(actual)!=expected
            or any(not isinstance(link,str) or not link.startswith("tt://")
                   for link in actual.values())):
        raise RuntimeError("TRUST_BULK_ACK_MISMATCH")
    return ack
