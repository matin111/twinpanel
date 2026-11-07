"""Mieru one-session credential staging for a hidden Exit.

Accepts only a bounded set of already-encrypted-and-persisted central
identities supplied by the caller. No credentials in logs or command args.
A single mita lifecycle operation replaces all per-user restarts.
This is an adapter primitive; it does not publish nodes or write to DB.
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
from typing import Any

MAX_ACCOUNTS = 3000
_USERNAME = re.compile(r"^tp-sub-[1-9][0-9]{0,17}$")


def verify_accounts(rows: list[dict[str, str]]) -> None:
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_ACCOUNTS:
        raise ValueError("MIERU_INVALID_BATCH_SIZE")
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("MIERU_INVALID_ACCOUNT")
        username = row.get("username")
        password = row.get("password")
        if (not isinstance(username, str) or
                not _USERNAME.fullmatch(username) or username in seen or
                not isinstance(password, str) or not 8 <= len(password) <= 256 or
                any(x in password for x in ("\n", "\r", "\0"))):
            raise ValueError("MIERU_INVALID_ACCOUNT")
        seen.add(username)


def remote_source(
    config="/etc/twinpanel/standalone/mieru/server.json",
    state="/etc/twinpanel/standalone/accounts/mieru.json",
) -> str:
    program = r'''import fcntl, json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path

CONFIG=Path(__CONFIG__)
STATE=Path(__STATE__)
incoming=json.load(sys.stdin)
if not isinstance(incoming,list) or not 1<=len(incoming)<=3000:
    raise SystemExit("INVALID_MIERU_BATCH")
names=set()
for row in incoming:
    name=row.get("username")
    secret=row.get("password")
    if (not isinstance(name,str) or not name.startswith("tp-sub-")
        or not name[7:].isdigit() or not isinstance(secret,str)
        or not 8<=len(secret)<=256 or name in names):
        raise SystemExit("INVALID_MIERU_IDENTITY")
    names.add(name)
for path in (CONFIG,STATE):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise SystemExit("MIERU_UNSAFE_PATH")
if not CONFIG.is_file():
    raise SystemExit("MIERU_RUNTIME_NOT_INSTALLED")
lock=CONFIG.parent/".central-mieru-bulk.lock"
with open(lock,"a+") as handle:
    fcntl.flock(handle,fcntl.LOCK_EX)
    config=json.loads(CONFIG.read_text(encoding="utf-8"))
    if not isinstance(config,dict):
        raise SystemExit("MIERU_CONFIG_INVALID")
    if STATE.exists():
        accounts=json.loads(STATE.read_text(encoding="utf-8"))
    else:
        accounts={}
    if not isinstance(accounts,dict):
        raise SystemExit("MIERU_STATE_INVALID")
    for row in incoming:
        username=row["username"]
        current=accounts.get(username)
        if current is not None and current.get("password")!=row["password"]:
            raise SystemExit("MIERU_EXISTING_IDENTITY_CONFLICT")
        accounts[username]={"name":username,"password":row["password"]}
    if not accounts:
        raise SystemExit("MIERU_EMPTY_USER_LIST")
    config["users"]=list(accounts.values())
    STATE.parent.mkdir(parents=True,exist_ok=True)
    state_text=json.dumps(accounts,separators=(",",":"),ensure_ascii=False)+"\\n"
    config_text=json.dumps(config,indent=2,ensure_ascii=False)+"\\n"
    changed=(not STATE.exists() or STATE.read_text(encoding="utf-8")!=state_text
             or CONFIG.read_text(encoding="utf-8")!=config_text)
    if not changed:
        print(json.dumps({"ok":True,"applied":len(incoming),"changed":False}))
        raise SystemExit(0)
    files=[]
    try:
        for dest,value in ((STATE,state_text),(CONFIG,config_text)):
            fd,name=tempfile.mkstemp(prefix=".central-mieru-",dir=str(dest.parent))
            os.fchmod(fd,0o600)
            with os.fdopen(fd,"w",encoding="utf-8") as out:
                out.write(value)
                out.flush()
                os.fsync(out.fileno())
            files.append((dest,name))
        backups=[]
        for dest,_ in files:
            if dest.exists():
                backup=dest.parent/(".pre-central-mieru-"+str(time.time_ns())+".bak")
                shutil.copy2(dest,backup)
                os.chmod(backup,0o600)
                backups.append((dest,backup))
        # Match the existing mita lifecycle once for this entire batch.
        subprocess.run(["mita","stop"],stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL,timeout=40,check=False)
        swapped=False
        try:
            # The existing runtime uses 'mita replace config' for applying
            # the server config. Use the prepared file and a single start.
            staged_config=next(name for dest,name in files if dest==CONFIG)
            result=subprocess.run(["mita","replace","config",staged_config],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=80,check=False)
            if result.returncode:
                raise RuntimeError("MIERU_REPLACE_FAILED")
            for dest,name in files:
                os.replace(name,dest)
            swapped=True
            started=subprocess.run(["mita","start"],stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,timeout=80,check=False)
            status=subprocess.run(["mita","status"],capture_output=True,text=True,
                timeout=20,check=False)
            if started.returncode or status.returncode or "RUNNING" not in (status.stdout+status.stderr).upper():
                raise RuntimeError("MIERU_START_FAILED")
        except BaseException:
            for dest,backup in backups:
                shutil.copy2(backup,dest)
                os.chmod(dest,0o600)
            subprocess.run(["mita","replace","config",str(CONFIG)],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=60,check=False)
            subprocess.run(["mita","start"],stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,timeout=60,check=False)
            raise
    finally:
        for _,name in files:
            if os.path.exists(name): os.unlink(name)
print(json.dumps({"ok":True,"applied":len(incoming),"changed":True}))
'''
    return (program.replace("__CONFIG__", repr(config))
                   .replace("__STATE__", repr(state)))


async def apply_bulk(conn: Any, accounts: list[dict[str, str]]) -> dict[str, Any]:
    verify_accounts(accounts)
    encoded = base64.b64encode(remote_source().encode()).decode("ascii")
    process = await asyncio.wait_for(
        conn.create_process("python3 -c \"$(printf '%s' '" + encoded + "' | base64 -d)\""),
        timeout=25,
    )
    process.stdin.write(json.dumps(accounts))
    process.stdin.write_eof()
    result = await asyncio.wait_for(process.wait(), timeout=300)
    if result.exit_status:
        # Only accept a fixed error-code token from the remote process.
        # Never include stdout/stderr or credentials in logs.
        import re
        diagnostics = str(result.stderr or "")
        tokens = re.findall(r"\\b(?:MIERU_[A-Z0-9_]+|MIERU_[A-Z0-9_]+)\\b", diagnostics)
        code = tokens[-1] if tokens else "REMOTE_UNKNOWN"
        raise RuntimeError("CENTRAL_MIERU_REMOTE_APPLY_FAILED:"+code)
    try:
        value = json.loads((result.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise RuntimeError("CENTRAL_MIERU_REMOTE_RESULT_MISSING") from exc
    if value.get("ok") is not True or value.get("applied") != len(accounts):
        raise RuntimeError("CENTRAL_MIERU_REMOTE_RESULT_UNCONFIRMED")
    return value
