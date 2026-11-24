#!/usr/bin/env python3
"""Root-owned read-only Kill Switch status service for unsigned macOS.

This service is intentionally incapable of loading/enabling PF. It exposes
only bounded, non-secret status until local live-leak and recovery tests
authorize the separate enforcement controller. No action socket or sudoers
rule is created. A remote Mac never claims active protection.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import time

from unsigned_killswitch_attestation import collect
from unsigned_killswitch_journal import PROTOCOLS
from unsigned_killswitch_pf_backend import PFCTL, ANCHOR, native_command, lines

RUNTIME = Path("/Library/PrivilegedHelperTools/TwinConnectKillSwitchStatus")
PUBLIC = Path("/private/var/run/twinconnect-killswitch-status")
INTERVAL = 10
FILES = ("unsigned_killswitch_status_service.py","unsigned_killswitch_policy.py",
         "unsigned_killswitch_attestation.py","unsigned_killswitch_controller.py",
         "unsigned_killswitch_journal.py","unsigned_killswitch_pf_backend.py")


def report(command=native_command, evidence=collect, remote=None, now=time.time):
    if remote is None:
        remote=Path("/usr/local/bin/termalin-agent").exists()
    reason="KS_REMOTE_RECOVERY_REQUIRED" if remote else "KS_LIVE_ACCEPTANCE_REQUIRED"
    state={"version":1,"timestamp":int(now()),"state":"off",
           "activation_available":False,"leak_verified":False,
           "pf_enabled":None,"protocol":None,"reason":reason}
    try:
        out=command((PFCTL,"-s","info"))
        if out.returncode!=0:
            raise ValueError("KS_PF_STATUS_UNAVAILABLE")
        m=re.search(r"(?m)^Status:\s+(Enabled|Disabled)\b",out.stdout)
        if not m:
            raise ValueError("KS_PF_STATUS_UNAVAILABLE")
        state["pf_enabled"]=m.group(1)=="Enabled"
        anchor=command((PFCTL,"-a",ANCHOR,"-sr"))
        if anchor.returncode!=0:
            raise ValueError("KS_PF_STATUS_UNAVAILABLE")
        if lines(anchor.stdout):
            state["state"]="unknown"
            state["reason"]="KS_EXISTING_ANCHOR_UNVERIFIED"
    except Exception:
        state["state"]="unknown"
        state["reason"]="KS_PF_STATUS_UNAVAILABLE"
    try:
        observed=evidence()
        if observed is not None and observed.protocol in PROTOCOLS:
            state["protocol"]=observed.protocol
    except Exception:
        pass
    return state


def require_trusted(path, directory=False):
    info=path.lstat()
    if (info.st_uid!=0 or info.st_mode & 0o022 or
            not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))):
        raise ValueError("KS_STATUS_RUNTIME_UNTRUSTED")


def publish(directory, value):
    dirfd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    tmp=None
    try:
        info=os.fstat(dirfd)
        if info.st_uid!=os.geteuid() or info.st_mode & 0o022:
            raise ValueError("KS_STATUS_DIRECTORY_UNTRUSTED")
        import secrets
        tmp="status.next-"+secrets.token_hex(10)
        fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644,dir_fd=dirfd)
        with os.fdopen(fd,"wb") as f:
            f.write(json.dumps(value,separators=(",",":")).encode("ascii")+b"\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp,"status.json",src_dir_fd=dirfd,dst_dir_fd=dirfd)
        os.fsync(dirfd)
    finally:
        if tmp is not None:
            try: os.unlink(tmp,dir_fd=dirfd)
            except FileNotFoundError: pass
        os.close(dirfd)


def main():
    if sys.platform!="darwin" or os.geteuid()!=0:
        raise ValueError("KS_STATUS_ROOT_MACOS_REQUIRED")
    if Path(__file__).resolve()!=RUNTIME/Path(__file__).name:
        raise ValueError("KS_STATUS_ROOT_INSTALL_REQUIRED")
    for path in (RUNTIME,RUNTIME.parent,Path("/Library"),Path("/")):
        require_trusted(path,True)
    for name in FILES:
        require_trusted(RUNTIME/name)
    PUBLIC.mkdir(mode=0o755,exist_ok=True)
    require_trusted(PUBLIC,True)
    if sys.argv[1:]==["--once"]:
        publish(PUBLIC,report())
        return
    if sys.argv[1:]!=["--serve"]:
        raise ValueError("KS_STATUS_ACTION_INVALID")
    stopping=False
    def stop(*_):
        nonlocal stopping
        stopping=True
    signal.signal(signal.SIGTERM,stop)
    signal.signal(signal.SIGINT,stop)
    while not stopping:
        publish(PUBLIC,report())
        for _ in range(INTERVAL*2):
            if stopping: break
            time.sleep(0.5)


if __name__=="__main__":
    main()
