"""Single Sudoku daemon per Exit with a hash-based user whitelist.

The official Sudoku server supports a 'users' whitelist keyed by the client's
handshake hash. Per-user systemd services are neither needed nor permitted in
this new node onboarding path. The shared master is kept on the node (0600);
client split keys are returned only via authenticated SSH and encrypted by
the controller before any runtime apply.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
from typing import Any

SHARED_PORT = 18553
SHARED_SERVICE = "twinpanel-sudoku-shared"
MAX_USERS = 3000
SHARED_BINARY = "/usr/local/bin/twinpanel-sudoku-shared"


def user_hash(key: str) -> str:
    if not isinstance(key, str) or len(key) not in (64, 128) or not re.fullmatch(r"[0-9a-fA-F]+",key):
        raise ValueError("SUDOKU_SHARED_INVALID_CLIENT_KEY")
    return hashlib.sha256(bytes.fromhex(key)).digest()[:8].hex()


def users_manifest(accounts: list[dict]) -> list[dict]:
    if not isinstance(accounts,list) or not 1 <= len(accounts) <= MAX_USERS:
        raise ValueError("SUDOKU_SHARED_INVALID_USERS")
    seen_ids=set()
    seen_hashes=set()
    manifest=[]
    for row in accounts:
        sid=row.get("subscription_id")
        key=row.get("client_key")
        if type(sid) is not int or sid<=0 or sid in seen_ids:
            raise ValueError("SUDOKU_SHARED_DUPLICATE_ID")
        digest=user_hash(key)
        if digest in seen_hashes:
            raise ValueError("SUDOKU_SHARED_DUPLICATE_USER_HASH")
        seen_ids.add(sid)
        seen_hashes.add(digest)
        manifest.append({"alias":f"tp-sub-{sid}","key":digest})
    return sorted(manifest,key=lambda x:int(x["alias"].split("-")[-1]))


def remote_source() -> str:
    # Stdin is JSON; no client key or master key ever appears in command-line
    # arguments to SSH or systemctl. A local "-more" subprocess uses the master
    # private key only inside this locked-down remote execution session.
    return r'''import concurrent.futures,json,os,re,hashlib,socket,subprocess,sys,tempfile,time,secrets,urllib.request
from pathlib import Path
BASE=Path("/etc/twinpanel/standalone/sudoku/shared")
BINARY=Path("/usr/local/bin/twinpanel-sudoku-shared")
PORT=18553
SERVICE="twinpanel-sudoku-shared.service"
UNIT=Path("/etc/systemd/system")/SERVICE
CONF=BASE/"server.config.json"
MASTER=BASE/"master.json"
CONTROLLER="127.0.0.1:19095"
req=json.load(sys.stdin)
action=req.get("action")
if action not in ("prepare","apply","probe","deactivate"):
    raise RuntimeError("SUDOKU_SHARED_ACTION_NOT_ALLOWED")
if not BINARY.is_file() or BINARY.is_symlink():
    raise RuntimeError("SUDOKU_SHARED_BINARY_NOT_INSTALLED")
if BASE.is_symlink() or MASTER.is_symlink() or CONF.is_symlink() or UNIT.is_symlink():
    raise RuntimeError("SUDOKU_SHARED_UNSAFE_PATH")

# A zero-entitlement whitelist must never run as a blank/unrestricted
# Sudoku server. Stop only the owned shared daemon and retain encrypted
# identities/config for a future reactivation or rollback. No legacy units,
# data or other protocol services are modified here.
if action=="deactivate":
    if UNIT.exists():
        existing=UNIT.read_text()
        if str(BINARY) not in existing or str(CONF) not in existing:
            raise RuntimeError("SUDOKU_SHARED_UNIT_OWNERSHIP_CONFLICT")
        # A plain stop is not durable: systemd would restart the stale
        # nonempty whitelist after a node reboot. Disable the owned unit as
        # well. A future positive-identity apply always enables it again.
        stopped=subprocess.run(["systemctl","disable","--now",SERVICE],
                               check=False,timeout=35,
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if stopped.returncode:
            raise RuntimeError("SUDOKU_SHARED_DEACTIVATE_FAILED")
        active=subprocess.run(["systemctl","is-active","--quiet",SERVICE],
                              check=False,timeout=10,
                              stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        enabled=subprocess.run(["systemctl","is-enabled","--quiet",SERVICE],
                               check=False,timeout=10,
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if active.returncode==0 or enabled.returncode==0:
            raise RuntimeError("SUDOKU_SHARED_DEACTIVATE_NOT_CONFIRMED")
    print(json.dumps({"ok":True,"changed":bool(UNIT.exists()),
                      "users":0,"port":PORT,"deactivated":True}))
    raise SystemExit(0)

def read_master():
    if not MASTER.is_file():raise RuntimeError("SUDOKU_SHARED_MASTER_NOT_INITIALIZED")
    st=MASTER.stat()
    if st.st_mode & 0o077:raise RuntimeError("SUDOKU_SHARED_MASTER_PERMISSIONS")
    doc=json.loads(MASTER.read_text())
    if not re.fullmatch("[0-9a-f]{64}",doc.get("private","")):
        raise RuntimeError("SUDOKU_SHARED_MASTER_PRIVATE_INVALID")
    if not re.fullmatch("[0-9a-f]{64}",doc.get("public","")):
        raise RuntimeError("SUDOKU_SHARED_MASTER_PUBLIC_INVALID")
    return doc

def run_keygen(*args):
    result=subprocess.run([str(BINARY),"-keygen",*args],
        capture_output=True,text=True,check=False,timeout=35)
    if result.returncode:raise RuntimeError("SUDOKU_SHARED_KEYGEN_FAILED")
    return result.stdout

def field(raw,label):
    m=re.search(re.escape(label)+r":\s*([0-9a-fA-F]+)\s*$",raw,re.M)
    if not m:raise RuntimeError("SUDOKU_SHARED_KEYGEN_RESULT_INVALID")
    return m.group(1).lower()

if action=="probe":
    print(json.dumps({"ok":True,"binary":True,"master_ready":MASTER.is_file(),
                      "config_ready":CONF.is_file(),"port":PORT}))
elif action=="prepare":
    ids=req.get("ids")
    if not isinstance(ids,list) or len(ids)>3000 or any(
        type(i)!=int or i<=0 for i in ids) or len(set(ids))!=len(ids):
        raise RuntimeError("SUDOKU_SHARED_INVALID_IDENTITIES")
    BASE.mkdir(parents=True,exist_ok=True,mode=0o700)
    if not MASTER.exists():
        raw=run_keygen()
        master={"private":field(raw,"Master Private Key"),
                "public":field(raw,"Master Public Key")}
        path=BASE/"master.json.tmp"
        with path.open("x") as f:
            json.dump(master,f)
        os.chmod(path,0o600)
        os.replace(path,MASTER)
    master=read_master()
    def derive(sid):
        raw=run_keygen("-more",master["private"])
        key=field(raw,"Split Private Key")
        if len(key) not in (64,128):
            raise RuntimeError("SUDOKU_SHARED_SPLIT_KEY_INVALID")
        return {"subscription_id":sid,"client_key":key}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        generated=list(pool.map(derive,ids))
    print(json.dumps({"ok":True,"port":PORT,"master_public":master["public"],
                      "keys":generated},separators=(",",":")))
else:
    master=read_master()
    users=req.get("users")
    if not isinstance(users,list) or not 1<=len(users)<=3000:
        raise RuntimeError("SUDOKU_SHARED_EMPTY_WHITELIST")
    seen=set()
    clean=[]
    for row in users:
        key=row.get("key","")
        alias=row.get("alias","")
        if not re.fullmatch("[0-9a-f]{16}",key) or key in seen:
            raise RuntimeError("SUDOKU_SHARED_INVALID_HASH")
        if not re.fullmatch("tp-sub-[1-9][0-9]*",alias):
            raise RuntimeError("SUDOKU_SHARED_INVALID_ALIAS")
        seen.add(key)
        clean.append({"alias":alias,"key":key})
    clean.sort(key=lambda r:int(r["alias"].split("-")[-1]))
    if not CONF.exists():
        with socket.socket() as sock:
            try:sock.bind(("0.0.0.0",PORT))
            except OSError:raise RuntimeError("SUDOKU_SHARED_PORT_IN_USE")
    previous_config=json.loads(CONF.read_text()) if CONF.exists() else {}
    token=previous_config.get("secret") or secrets.token_hex(24)
    if not re.fullmatch("[0-9a-f]{48}",token):
        raise RuntimeError("SUDOKU_SHARED_CONTROLLER_SECRET_CONFLICT")
    cfg={"mode":"server","transport":"tcp","local_port":PORT,
         "fallback_address":"127.0.0.1:80",
         "key":master["public"],"aead":"chacha20-poly1305",
         "suspicious_action":"fallback",
         "padding_min":5,"padding_max":15,"ascii":"prefer_entropy",
         "enable_pure_downlink":True,"multiplex":"off",
         "httpmask":{"disable":False,"mode":"auto"},
         "external_controller":CONTROLLER,"secret":token,
         "users":clean}
    # No fallback to unrestricted server mode when a whitelist is empty.
    previous=CONF.read_bytes() if CONF.exists() else None
    new=json.dumps(cfg,sort_keys=True,separators=(",",":")).encode()+b"\n"
    if previous==new and subprocess.run(
        ["systemctl","is-active","--quiet",SERVICE],check=False).returncode==0:
        print(json.dumps({"ok":True,"changed":False,"users":len(clean),"port":PORT}))
        sys.exit(0)
    if UNIT.exists():
        existing=UNIT.read_text()
        if str(BINARY) not in existing or str(CONF) not in existing:
            raise RuntimeError("SUDOKU_SHARED_UNIT_OWNERSHIP_CONFLICT")
    if not UNIT.exists():
        body=("[Unit]\nDescription=TwinPanel shared Sudoku server\n"
              "After=network-online.target\nWants=network-online.target\n"
              "[Service]\nType=simple\nUser=root\n"
              "ExecStart="+str(BINARY)+" -c "+str(CONF)+"\n"
              "Restart=on-failure\nRestartSec=3\n"
              "LimitNOFILE=1048576\n[Install]\nWantedBy=multi-user.target\n")
        UNIT.write_text(body)
        os.chmod(UNIT,0o644)
    temp=BASE/"server.config.new"
    try:
        with temp.open("wb") as f:f.write(new)
        os.chmod(temp,0o600)
        os.replace(temp,CONF)
        reload=subprocess.run(["systemctl","daemon-reload"],check=False,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=25)
        if reload.returncode:raise RuntimeError("SUDOKU_SHARED_RELOAD_UNITS_FAILED")
        enable=subprocess.run(["systemctl","enable",SERVICE],check=False,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=25)
        if enable.returncode:raise RuntimeError("SUDOKU_SHARED_ENABLE_FAILED")
        service=subprocess.run(["systemctl","restart",SERVICE],check=False,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=35)
        if service.returncode:raise RuntimeError("SUDOKU_SHARED_SERVICE_FAILED")
        ready=False
        for i in range(50):
            with socket.socket() as sock:
                sock.settimeout(0.2)
                ready=(sock.connect_ex(("127.0.0.1",PORT))==0)
            if ready:break
            time.sleep(0.15)
        if not ready:raise RuntimeError("SUDOKU_SHARED_LISTENER_NOT_READY")
        # Query the core's LIVE, localhost-only controller endpoint to
        # distinguish "service listening" from "all users loaded".
        verified=False
        for attempt in range(20):
            try:
                request=urllib.request.Request(
                    "http://"+CONTROLLER+"/users",
                    headers={"Authorization":"Bearer "+token},
                )
                with urllib.request.urlopen(request,timeout=1.0) as response:
                    snapshot=json.load(response)
                live_users=snapshot.get("users") if isinstance(snapshot,dict) else None
                live_names={
                    row.get("name") for row in live_users
                    if isinstance(row,dict) and isinstance(row.get("name"),str)
                } if isinstance(live_users,list) else set()
                desired_names={row["alias"] for row in clean}
                # Count equality is NOT an identity ACK: two different user
                # lists may have the same length. Only the exact live runtime
                # whitelist proves that expired keys were actually removed.
                verified=(
                    type(snapshot.get("count")) is int
                    and snapshot["count"]==len(clean)
                    and isinstance(live_users,list)
                    and len(live_users)==len(desired_names)
                    and live_names==desired_names
                )
                if verified:break
            except Exception:pass
            time.sleep(0.2)
        if not verified:
            raise RuntimeError("SUDOKU_SHARED_RUNTIME_USER_COUNT_MISMATCH")
        print(json.dumps({"ok":True,"changed":True,"users":len(clean),"port":PORT}))
    except BaseException:
        if previous is None:
            if CONF.exists():CONF.unlink()
            subprocess.run(["systemctl","disable","--now",SERVICE],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=35)
            if UNIT.exists():UNIT.unlink()
            subprocess.run(["systemctl","daemon-reload"],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=25)
        else:
            CONF.write_bytes(previous)
            os.chmod(CONF,0o600)
            subprocess.run(["systemctl","restart",SERVICE],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=35)
        raise
'''


async def _remote(conn: Any, request: dict, *, timeout: int = 300) -> dict:
    encoded=base64.b64encode(remote_source().encode()).decode("ascii")
    process=await asyncio.wait_for(conn.create_process(
        "python3 -c \"$(printf '%s' '"+encoded+"' | base64 -d)\"",
    ),timeout=25)
    process.stdin.write(json.dumps(request,separators=(",",":")))
    process.stdin.write_eof()
    result=await asyncio.wait_for(process.wait(),timeout=timeout)
    if result.exit_status:
        raise RuntimeError("SUDOKU_SHARED_REMOTE_"+str(request.get("action")).upper()+"_FAILED")
    try:
        output=json.loads((result.stdout or "").strip().splitlines()[-1])
    except (IndexError,ValueError,TypeError) as exc:
        raise RuntimeError("SUDOKU_SHARED_REMOTE_ACK_INVALID") from exc
    if output.get("ok") is not True:
        raise RuntimeError("SUDOKU_SHARED_REMOTE_ACK_REJECTED")
    return output


async def prepare(conn: Any, ids: list[int]) -> dict:
    if any(type(i)!=int or i<=0 for i in ids) or len(ids)>MAX_USERS or len(set(ids))!=len(ids):
        raise ValueError("SUDOKU_SHARED_INVALID_IDENTITIES")
    result=await _remote(conn,{"action":"prepare","ids":ids},timeout=850)
    if result.get("port")!=SHARED_PORT or not re.fullmatch(r"[0-9a-f]{64}",str(result.get("master_public") or "")):
        raise RuntimeError("SUDOKU_SHARED_MASTER_INVALID")
    keys=result.get("keys")
    if not isinstance(keys,list) or [r.get("subscription_id") for r in keys]!=ids:
        raise RuntimeError("SUDOKU_SHARED_KEYGEN_COUNT_MISMATCH")
    for row in keys:
        user_hash(row.get("client_key"))
    return result


async def apply(conn: Any, accounts: list[dict]) -> dict:
    manifest=users_manifest(accounts)
    result=await _remote(conn,{"action":"apply","users":manifest},timeout=160)
    if result.get("users")!=len(manifest) or result.get("port")!=SHARED_PORT:
        raise RuntimeError("SUDOKU_SHARED_APPLY_MISMATCH")
    return result


async def deactivate(conn: Any) -> dict:
    """Stop the *owned* shared daemon if no subscribers remain.

    A subsequent normal apply can reactivate the existing unit atomically.
    """
    result = await _remote(conn, {"action": "deactivate"})
    if not result.get("deactivated") or result.get("users") != 0:
        raise RuntimeError("SUDOKU_SHARED_DEACTIVATE_ACK_INVALID")
    return result
