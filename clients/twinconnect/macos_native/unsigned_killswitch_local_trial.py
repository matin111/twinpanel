#!/usr/bin/env python3
"""Bounded local-console PF block trial, NOT production VPN integration.

Never run from SSH or an enrolled remote VPS. No global PF flush/reload.
The trial accepts no endpoint or rule supplied by an unprivileged caller.
A detached recovery worker is armed BEFORE applying the dedicated anchor.
"""
from __future__ import annotations
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time

from unsigned_killswitch_policy import ANCHOR, PFCTL, render_policy, validate_kernel_syntax

ROOT = Path("/Library/PrivilegedHelperTools/TwinConnectKillSwitch")
STATE = Path("/private/var/run/twinconnect-killswitch-trial")
LEASE = STATE / "lease.json"
LOCK = STATE / "lock"
SECONDS = 30


def run(*args, timeout=5):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                          check=False, env={"PATH":"/usr/bin:/bin:/usr/sbin:/sbin",
                                            "LC_ALL":"C"})


def trusted(path, directory=False):
    info = path.lstat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    return expected(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022


def require_root_runtime():
    if sys.platform != "darwin" or os.geteuid() != 0:
        raise ValueError("KS_ROOT_MACOS_REQUIRED")
    if Path(__file__).resolve() != ROOT / Path(__file__).name:
        raise ValueError("KS_ROOT_INSTALL_REQUIRED")
    for p in (ROOT, ROOT.parent, ROOT.parent.parent, Path("/Library"), Path("/")):
        if not trusted(p, True):
            raise ValueError("KS_ROOT_RUNTIME_UNTRUSTED")
    for name in (Path(__file__).name, "unsigned_killswitch_policy.py"):
        if not trusted(ROOT / name):
            raise ValueError("KS_ROOT_RUNTIME_UNTRUSTED")
    STATE.mkdir(mode=0o700, exist_ok=True)
    if not trusted(STATE, True) or STATE.stat().st_mode & 0o077:
        raise ValueError("KS_STATE_UNTRUSTED")


def require_physical_console():
    # No reliance on a caller's shell environment alone. A registered
    # Termalin connector, SSH listener session, or headless console refuses.
    if any(os.environ.get(k) for k in ("SSH_CONNECTION","SSH_CLIENT","SSH_TTY",
                                       "TWINCONNECT_REMOTE_VPS")):
        raise ValueError("KS_REMOTE_SESSION_REFUSED")
    if Path("/usr/local/bin/termalin-agent").exists():
        raise ValueError("KS_REMOTE_CONNECTOR_PRESENT")
    if not sys.stdin.isatty() or not sys.stdout.isatty() or os.stat("/dev/console").st_uid <= 0:
        raise ValueError("KS_PHYSICAL_CONSOLE_REQUIRED")
    # The operator must actually have an independent local recovery path.
    print("This test blocks ALL non-loopback traffic for at most 30 seconds.")
    print("Use only a physical Mac with local administrator access. Do not use on a VPS.")
    if input("Type LOCAL-PF-30-SECOND-TRIAL: ") != "LOCAL-PF-30-SECOND-TRIAL":
        raise ValueError("KS_TRIAL_NOT_APPROVED")


def checked(*args):
    result = run(*args)
    if result.returncode:
        raise ValueError("KS_PF_COMMAND_FAILED")
    return result.stdout + "\n" + result.stderr


def lock():
    fd = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    if not stat.S_ISREG(os.fstat(fd).st_mode) or os.fstat(fd).st_uid != 0:
        os.close(fd)
        raise ValueError("KS_LOCK_UNTRUSTED")
    fcntl.flock(fd, fcntl.LOCK_EX)
    return os.fdopen(fd,"w")


def save(data):
    tmp = STATE / "lease.next"
    fd = os.open(tmp, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"w") as f:
        json.dump(data,f); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,LEASE)


def load():
    if not LEASE.exists():
        return None
    if not trusted(LEASE) or LEASE.stat().st_mode & 0o077:
        raise ValueError("KS_LEASE_UNTRUSTED")
    data=json.loads(LEASE.read_text())
    if not isinstance(data,dict):
        raise ValueError("KS_LEASE_INVALID")
    return data


def preflight():
    # This restricted trial only runs with PF initially disabled, no states,
    # no custom main filter rules and no existing private anchor rules.
    if "Status: Disabled" not in checked(PFCTL,"-s","info"):
        raise ValueError("KS_EXISTING_PF_REFUSED")
    main = run(PFCTL,"-sr")
    if main.returncode or set(main.stdout.splitlines()) != {
        'scrub-anchor "com.apple/*" all fragment reassemble',
        'anchor "com.apple/*" all'}:
        raise ValueError("KS_MAIN_RULESET_UNREVIEWED")
    for args in ((PFCTL,"-ss"), (PFCTL,"-a",ANCHOR,"-sr")):
        out=run(*args)
        if out.returncode or out.stdout.strip():
            raise ValueError("KS_EXISTING_STATE_OR_ANCHOR")
    if not validate_kernel_syntax(render_policy()):
        raise ValueError("KS_PF_SYNTAX_REJECTED")


def restore_locked():
    data=load()
    if not data:
        return
    # First remove ONLY our own blocking anchor. Never disable or flush
    # the main ruleset. If release fails, preserve the lease for recovery.
    checked(PFCTL,"-a",ANCHOR,"-F","rules")
    token=data.get("token")
    if token:
        if not re.fullmatch(r"[0-9]{1,20}",str(token)):
            raise ValueError("KS_TOKEN_INVALID")
        checked(PFCTL,"-X",str(token))
    LEASE.unlink(missing_ok=True)


def recovery_worker():
    # Detached process with independent deadline; never depend on the app.
    # Locking serializes activation and rollback even if the parent dies.
    deadline=time.monotonic()+SECONDS
    print("KS_RECOVERY_READY",flush=True)
    while time.monotonic()<deadline:
        time.sleep(min(0.5,max(0,deadline-time.monotonic())))
    for _ in range(5):
        try:
            with lock():
                restore_locked()
            return
        except (OSError,ValueError,subprocess.TimeoutExpired):
            time.sleep(1)
    raise ValueError("KS_RECOVERY_RETRY_REQUIRED")


def trial():
    require_physical_console()
    with lock():
        if load() is not None:
            raise ValueError("KS_PREVIOUS_LEASE_REQUIRES_RESTORE")
        preflight()
        # Journal before any kernel changes. The detached worker removes
        # the dedicated anchor even if the controller crashes mid-activation.
        save({"token":None})
        try:
            worker=subprocess.Popen([sys.executable,str(ROOT/Path(__file__).name),"--recover"],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                       stdin=subprocess.DEVNULL,start_new_session=True,text=True)
            import select
            ready,_,_=select.select([worker.stdout],[],[],3)
            if not ready or worker.stdout.readline().strip()!="KS_RECOVERY_READY":
                raise ValueError("KS_RECOVERY_NOT_READY")
            worker.stdout.close()
            # The rules file contains no user input and is root-private.
            path=STATE/"trial.pf"
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            try:
                with os.fdopen(fd,"w") as f:
                    f.write(render_policy())
                checked(PFCTL,"-a",ANCHOR,"-f",str(path))
            finally:
                path.unlink(missing_ok=True)
            # macOS PF reference-counted enable. Capture only our reference.
            reply=checked(PFCTL,"-E")
            match=re.search(r"(?im)^\s*Token\s*:\s*(\d+)\s*$",reply)
            if not match:
                raise ValueError("KS_ENABLE_TOKEN_UNAVAILABLE")
            save({"token":match.group(1)})
            print("KS_TRIAL_RULES_LOADED; LIVE LEAK TEST NOT YET VERIFIED",flush=True)
        except BaseException:
            restore_locked()
            raise
    try:
        time.sleep(SECONDS)
    finally:
        with lock():
            restore_locked()
    print("KS_TRIAL_RESTORED",flush=True)


def main():
    require_root_runtime()
    if sys.argv[1:]==["--trial"]:
        trial()
    elif sys.argv[1:]==["--recover"]:
        recovery_worker()
    elif sys.argv[1:]==["--restore"]:
        with lock():
            restore_locked()
        print("KS_TRIAL_RESTORED")
    else:
        raise ValueError("KS_ACTION_INVALID")


if __name__=="__main__":
    try:
        main()
    except (OSError,ValueError,subprocess.TimeoutExpired):
        print("KS_TRIAL_REFUSED_OR_FAILED",file=sys.stderr)
        raise SystemExit(2)
