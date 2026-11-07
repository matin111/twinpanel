"""One-session AmneziaWG peer projection for a hidden new Exit.

Never touches an already-published node. Preserves existing standalone
AmneziaWG keys and address assignments, stages public peers together,
and restarts the existing managed service only once after atomic replacement.
All private keys stay encrypted in the controller.
"""
from __future__ import annotations

import asyncio
import base64
import json
from typing import Any


def validate_peers(peers):
    if not isinstance(peers,list) or not 1<=len(peers)<=3000:
        raise ValueError("AWG_INVALID_BATCH_SIZE")
    ids=set(); keys=set(); addresses=set()
    for peer in peers:
        if not isinstance(peer,dict):
            raise ValueError("AWG_INVALID_PEER")
        username=peer.get("username")
        public=peer.get("public_key")
        address=peer.get("address")
        if not isinstance(username,str) or not username.startswith("tp-sub-") or not username[7:].isdigit() or username in ids:
            raise ValueError("AWG_INVALID_IDENTITY")
        try:
            raw=base64.b64decode(public,validate=True)
        except Exception as exc:
            raise ValueError("AWG_INVALID_PUBLIC_KEY") from exc
        if len(raw)!=32 or public in keys or address in addresses:
            raise ValueError("AWG_DUPLICATE_OR_INVALID_PEER")
        from ipaddress import ip_interface, ip_network
        try:
            address_obj=ip_interface(address)
        except (TypeError,ValueError) as exc:
            raise ValueError("AWG_INVALID_ADDRESS") from exc
        if address_obj.network.prefixlen!=32 or address_obj.ip not in ip_network("10.254.0.0/16") or str(address_obj.ip)=="10.254.0.1":
            raise ValueError("AWG_INVALID_ADDRESS")
        ids.add(username); keys.add(public); addresses.add(address)


def remote_source(
    *,
    state="/etc/twinpanel/standalone/accounts/amneziawg.json",
    config="/etc/amnezia/amneziawg/tpawg0.conf",
    service="twinpanel-amneziawg.service",
) -> str:
    source=r'''import base64,fcntl,ipaddress,json,os,re,shutil,subprocess,sys,tempfile
from pathlib import Path
STATE=Path(__STATE__)
CONFIG=Path(__CONFIG__)
SERVICE=__SERVICE__
incoming=json.load(sys.stdin)
if not isinstance(incoming,list) or not 1<=len(incoming)<=3000:
    raise SystemExit("AWG_BAD_PAYLOAD")
names=set(); keys=set(); addresses=set()
for row in incoming:
    name=row.get("username")
    key=row.get("public_key")
    address=row.get("address")
    if not isinstance(name,str) or not name.startswith("tp-sub-") or not name[7:].isdigit() or name in names:
        raise SystemExit("AWG_BAD_USER")
    try:
        valid_key=base64.b64decode(key,validate=True)
        parsed=ipaddress.ip_interface(address)
    except Exception:
        raise SystemExit("AWG_BAD_PEER")
    if (len(valid_key)!=32 or key in keys or address in addresses
        or parsed.network.prefixlen!=32 or parsed.ip not in ipaddress.ip_network("10.254.0.0/16")
        or str(parsed.ip) in ("10.254.0.0","10.254.0.1")):
        raise SystemExit("AWG_BAD_PEER")
    names.add(name); keys.add(key); addresses.add(address)
for target in (STATE,CONFIG):
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise SystemExit("AWG_UNSAFE_PATH")
if not CONFIG.is_file():
    raise SystemExit("AWG_RUNTIME_NOT_INSTALLED")
lock=CONFIG.parent/".twinpanel-awg-central-bulk.lock"
with open(lock,"a+") as mutex:
    fcntl.flock(mutex,fcntl.LOCK_EX)
    original=CONFIG.read_text(encoding="utf-8")
    if not original.lstrip().startswith("[Interface]"):
        raise SystemExit("AWG_INTERFACE_INVALID")
    accounts=json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    if not isinstance(accounts,dict):
        raise SystemExit("AWG_STATE_INVALID")
    # Prevent rebuilding the peer list if it contains unmanaged peers.
    managed_keys={str(row.get("public_key")) for row in accounts.values()
                  if isinstance(row,dict)}
    disk_keys=set(re.findall(r"(?m)^\s*PublicKey\s*=\s*(\S+)",original))
    if not disk_keys.issubset(managed_keys):
        raise SystemExit("AWG_UNMANAGED_PEERS_PRESENT")
    for row in incoming:
        name=row["username"]
        old=accounts.get(name)
        if old is not None and old!=row:
            raise SystemExit("AWG_EXISTING_IDENTITY_CONFLICT")
        for other_name, other in accounts.items():
            if other_name!=name and isinstance(other,dict) and (
                other.get("address")==row["address"]
                or other.get("public_key")==row["public_key"]):
                raise SystemExit("AWG_EXISTING_PEER_COLLISION")
        accounts[name]=row
    # Reuse the existing standalone account format and header.
    header=original.split("[Peer]",1)[0].rstrip()+"\n"
    header=re.sub(r"(?m)^Address\s*=.*$","Address = 10.254.0.1/16",header)
    parts=[]
    for account in accounts.values():
        if not isinstance(account,dict) or not all(isinstance(account.get(key),str)
            for key in ("username","public_key","address")):
            raise SystemExit("AWG_STATE_CORRUPT")
        parts.extend(["","[Peer]","PublicKey = "+account["public_key"],
                      "AllowedIPs = "+account["address"]])
    updated=header+"\n".join(parts)+"\n"
    state_text=json.dumps(accounts,ensure_ascii=False,separators=(",",":"))+"\n"
    changed=(updated!=original or not STATE.exists()
             or STATE.read_text(encoding="utf-8")!=state_text)
    orig_state=STATE.read_bytes() if STATE.exists() else None
    if changed:
        paths=[]
        try:
            STATE.parent.mkdir(parents=True,exist_ok=True)
            for target,data in ((CONFIG,updated),(STATE,state_text)):
                fd,stage=tempfile.mkstemp(prefix=".awg-central-",dir=str(target.parent))
                os.fchmod(fd,0o600)
                with os.fdopen(fd,"w",encoding="utf-8") as output:
                    output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
                paths.append((target,stage))
            for target,stage in paths: os.replace(stage,target)
            restart=subprocess.run(["systemctl","restart",SERVICE],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                check=False,timeout=150)
            status=subprocess.run(["systemctl","is-active","--quiet",SERVICE],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                check=False,timeout=20)
            if restart.returncode or status.returncode:
                raise RuntimeError("AWG_RESTART_FAILED")
        except BaseException:
            CONFIG.write_text(original,encoding="utf-8")
            os.chmod(CONFIG,0o600)
            if orig_state is None:
                if STATE.exists(): STATE.unlink()
            else:
                STATE.write_bytes(orig_state)
                os.chmod(STATE,0o600)
            recovered=subprocess.run(["systemctl","restart",SERVICE],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                check=False,timeout=150)
            if recovered.returncode:
                raise SystemExit("AWG_ROLLBACK_FAILED")
            raise
        finally:
            for _,stage in paths:
                if os.path.exists(stage): os.unlink(stage)
    private=re.search(r"(?m)^\s*PrivateKey\s*=\s*(\S+)",CONFIG.read_text())
    if not private:
        raise SystemExit("AWG_SERVER_KEY_MISSING")
    result=subprocess.run(["awg","pubkey"],input=private.group(1)+"\n",
                          capture_output=True,text=True,check=False,timeout=15)
    public=result.stdout.strip()
    if result.returncode or not public:
        raise SystemExit("AWG_SERVER_KEY_EXPORT_FAILED")
print(json.dumps({"ok":True,"applied":len(incoming),"changed":changed,
                  "server_public_key":public}))
'''
    for needle,value in {
        "__STATE__":repr(state),"__CONFIG__":repr(config),"__SERVICE__":repr(service),
    }.items():
        source=source.replace(needle,value)
    return source


async def apply_bulk(conn: Any, peers: list[dict]) -> dict:
    validate_peers(peers)
    source=base64.b64encode(remote_source().encode()).decode("ascii")
    process=await asyncio.wait_for(conn.create_process(
        "python3 -c \"$(printf '%s' '"+source+"' | base64 -d)\""),timeout=25)
    process.stdin.write(json.dumps(peers))
    process.stdin.write_eof()
    result=await asyncio.wait_for(process.wait(),timeout=350)
    if result.exit_status:
        raise RuntimeError("AWG_BULK_REMOTE_FAILED")
    try:
        ack=json.loads((result.stdout or "").strip().splitlines()[-1])
    except (ValueError,IndexError) as exc:
        raise RuntimeError("AWG_BULK_RESULT_INVALID") from exc
    if (ack.get("ok") is not True or ack.get("applied")!=len(peers)
            or not isinstance(ack.get("server_public_key"),str)):
        raise RuntimeError("AWG_BULK_RESULT_MISMATCH")
    return ack
