"""Hot VLESS revocation via localhost Xray HandlerService, without global restart.

The remote script is generated here so controller and queue handling retain
their original SSH credential model. No arbitrary file or tag input is used.
"""
from __future__ import annotations

import re

_EMAIL = re.compile(r"mv-[1-9][0-9]*@twinpanel")


_REMOTE = r'''
import fcntl,json,os,re,stat,subprocess,tempfile
from pathlib import Path

EMAIL=__EMAIL__
CONFIG=Path("/usr/local/etc/xray/config.json")
LOCK=Path("/run/twinpanel-xray-hot-user.lock")
XRAY="/usr/local/bin/xray"
API="--server=127.0.0.1:10085"
if not re.fullmatch(r"mv-[1-9][0-9]*@twinpanel",EMAIL):
    raise RuntimeError("HOT_REVOKE_EMAIL_INVALID")

def run(args,timeout=18):
    return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          text=True,timeout=timeout,check=False)

def restore_user(tag,port,client):
    obj={"inbounds":[{"tag":tag,"port":int(port),"protocol":"vless",
                      "settings":{"decryption":"none","clients":[client]}}]}
    path=None
    try:
        with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",
                prefix="tp-xray-hot-revoke-rollback-",suffix=".json",delete=False) as f:
            path=Path(f.name);os.chmod(path,0o600)
            json.dump(obj,f)
        response=run([XRAY,"api","adu",API,str(path)])
        if response.returncode or "Added 1 user(s) in total." not in response.stdout:
            raise RuntimeError("HOT_REVOKE_ROLLBACK_API_FAILED")
    finally:
        if path is not None:
            path.unlink(missing_ok=True)

def remove_live_user(tag):
    response=run([XRAY,"api","rmu",API,"-tag="+tag,EMAIL])
    if response.returncode:
        raise RuntimeError("HOT_REVOKE_API_FAILED")
    if "Removed 1 user(s) in total." in response.stdout:
        return True
    if "Removed 0 user(s) in total." in response.stdout:
        return False
    raise RuntimeError("HOT_REVOKE_API_UNVERIFIED")

def sync():
    if CONFIG.is_symlink() or not CONFIG.is_file():
        raise RuntimeError("HOT_REVOKE_CONFIG_MISSING")
    original=CONFIG.read_bytes()
    metadata=CONFIG.stat()
    doc=json.loads(original)
    affected=[]
    for inbound in doc.get("inbounds",[]):
        if not isinstance(inbound,dict) or inbound.get("protocol")!="vless":
            continue
        tag=str(inbound.get("tag") or "")
        port=int(inbound.get("port") or 0)
        clients=(inbound.get("settings") or {}).get("clients")
        if not tag or not 1<=port<=65535 or not isinstance(clients,list):
            raise RuntimeError("HOT_REVOKE_VLESS_INBOUND_INVALID")
        matching=[c for c in clients if isinstance(c,dict) and c.get("email")==EMAIL]
        if len(matching)>1:
            raise RuntimeError("HOT_REVOKE_DUPLICATE_EMAIL")
        if not matching:
            continue
        inbound["settings"]["clients"]=[c for c in clients if c is not matching[0]]
        affected.append((tag,port,matching[0]))
    if not affected:
        print(json.dumps({"ok":True,"changed":False,"live_restart":False,"reason":"already_absent"}))
        return

    stage=None
    try:
        with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",
                dir=CONFIG.parent,prefix="tp-xray-hot-revoke-",suffix=".json",
                delete=False) as f:
            stage=Path(f.name)
            json.dump(doc,f,ensure_ascii=False,indent=2)
            f.write("\n")
            f.flush();os.fsync(f.fileno())
        os.chown(stage,metadata.st_uid,metadata.st_gid)
        os.chmod(stage,stat.S_IMODE(metadata.st_mode))
        check=run([XRAY,"run","-test","-config",str(stage)],timeout=25)
        if check.returncode:
            raise RuntimeError("HOT_REVOKE_STAGED_CONFIG_INVALID")
        active=run(["systemctl","is-active","--quiet","xray"],timeout=5)
        if active.returncode:
            raise RuntimeError("HOT_REVOKE_XRAY_NOT_ACTIVE")

        removed=[]
        try:
            for tag,port,client in affected:
                if remove_live_user(tag):
                    removed.append((tag,port,client))
            # Other controller paths also take this lock, but external edits
            # are detected even if they use a different lock.
            if CONFIG.read_bytes()!=original:
                raise RuntimeError("HOT_REVOKE_CONCURRENT_CONFIG_CHANGE")
            os.replace(stage,CONFIG)
            stage=None
        except Exception:
            errors=[]
            for tag,port,client in reversed(removed):
                try:
                    restore_user(tag,port,client)
                except Exception:
                    errors.append(tag)
            if errors:
                raise RuntimeError("HOT_REVOKE_ROLLBACK_INCOMPLETE")
            raise
        print(json.dumps({"ok":True,"changed":True,
                          "inbounds":len(affected),"live_restart":False},
                         separators=(",",":")))
    finally:
        if stage is not None:
            stage.unlink(missing_ok=True)

LOCK.parent.mkdir(parents=True,exist_ok=True)
with LOCK.open("a+") as file:
    fcntl.flock(file.fileno(),fcntl.LOCK_EX)
    sync()
'''


def hot_revoke_script(subscription_id: int) -> str:
    sid = int(subscription_id)
    if sid <= 0:
        raise ValueError("HOT_REVOKE_SUBSCRIPTION_INVALID")
    email = f"mv-{sid}@twinpanel"
    if not _EMAIL.fullmatch(email):
        raise ValueError("HOT_REVOKE_EMAIL_INVALID")
    script = _REMOTE.replace("__EMAIL__", repr(email))
    compile(script, "<xray-hot-revoke>", "exec")
    return script
