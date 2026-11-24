#!/usr/bin/env python3
"""Bounded WireGuard Kill Switch session for a provider-console test Mac.

Explicit local administrator authorization is required for each enable.
Independent launchd recovery expires the session; this is NOT persistent
production protection. No new sudoers permissions or arbitrary commands.
"""
from __future__ import annotations
import fcntl
import json
import os
from pathlib import Path
import plistlib
import re
import secrets
import stat
import subprocess
import sys
import time

DEPENDENCY=Path("/Library/PrivilegedHelperTools/TwinConnectKillSwitchStatus")
if os.geteuid()==0:
    for dependency in (DEPENDENCY, DEPENDENCY/"unsigned_killswitch_attestation.py",
                       DEPENDENCY/"unsigned_killswitch_policy.py"):
        info=dependency.lstat()
        if info.st_uid!=0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
            raise RuntimeError("ATTESTATION_RUNTIME_UNTRUSTED")
sys.path.insert(0,str(DEPENDENCY))
from unsigned_killswitch_attestation import collect, route_interface, process_command, WG_BIN

ROOT=Path("/Library/PrivilegedHelperTools/TwinConnectKillSwitchControl")
SCRIPT=ROOT/"unsigned_killswitch_console_control.py"
STATE=Path("/private/var/run/twinconnect-killswitch-control")
LABEL="com.twinconnect.killswitch-session-recovery"
PLIST=ROOT/"session-recovery.plist"
PF="/sbin/pfctl"
ANCHOR="com.apple/twinconnect-killswitch"
RULES="pass quick on lo0 all no state\nblock drop quick all\n"
MAIN=("scrub-anchor \"com.apple/*\" all fragment reassemble",'anchor "com.apple/*" all')
APPLE=('anchor "200.AirDrop/*" all','anchor "250.ApplicationFirewall/*" all')
RECOVERY_SECONDS=120


def run(*args, input=None, timeout=4):
    return subprocess.run(args,input=input,text=True,capture_output=True,
                          timeout=timeout,check=False,
                          env={"PATH":"/usr/bin:/bin:/usr/sbin:/sbin","LC_ALL":"C"})


def checked(*args,input=None,timeout=4):
    result=run(*args,input=input,timeout=timeout)
    if result.returncode:
        raise RuntimeError("COMMAND_FAILED")
    return result.stdout


def lines(s):
    return tuple(line.strip() for line in s.splitlines() if line.strip())


def trusted(path, directory=False, private=False):
    info=path.lstat()
    kind=stat.S_ISDIR if directory else stat.S_ISREG
    if not kind(info.st_mode) or info.st_uid!=0 or info.st_mode & (0o077 if private else 0o022):
        raise RuntimeError("UNTRUSTED_RUNTIME")


def setup():
    if sys.platform!="darwin" or os.geteuid()!=0 or Path(__file__).resolve()!=SCRIPT:
        raise RuntimeError("ROOT_INSTALLED_MAC_RUNTIME_REQUIRED")
    for p in (Path("/"),Path("/Library"),ROOT.parent,ROOT):
        trusted(p,True)
    trusted(SCRIPT)
    STATE.mkdir(mode=0o700,exist_ok=True)
    trusted(STATE,True,True)


def write_json(name,value):
    tmp=STATE/(name+"."+secrets.token_hex(8))
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"w") as f:
            json.dump(value,f,separators=(",",":")); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,STATE/name)
    finally:
        tmp.unlink(missing_ok=True)


def read_json(name):
    p=STATE/name
    try:
        trusted(p,private=True)
        if p.stat().st_size>4096: raise RuntimeError("STATE_TOO_LARGE")
        return json.loads(p.read_text())
    except FileNotFoundError:
        return None


def lock():
    fd=os.open(STATE/"lock",os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX)
    return os.fdopen(fd,"w")


def pf_enabled():
    out=checked(PF,"-s","info")
    m=re.search(r"(?m)^Status:\s+(Enabled|Disabled)\b",out)
    if not m: raise RuntimeError("PF_STATUS_UNKNOWN")
    return m.group(1)=="Enabled"


def anchor_rules():
    return lines(checked(PF,"-a",ANCHOR,"-sr"))


def preflight():
    if pf_enabled(): raise RuntimeError("PF_ALREADY_ENABLED")
    if lines(checked(PF,"-sr"))!=MAIN or lines(checked(PF,"-a","com.apple","-sr"))!=APPLE:
        raise RuntimeError("FOREIGN_PF_RULES")
    if lines(checked(PF,"-a","com.apple/*","-sr"))!=('anchor "*" all {','}','anchor "*" all {','}'):
        raise RuntimeError("FOREIGN_PF_ANCHORS")
    if anchor_rules() or lines(checked(PF,"-ss")):
        raise RuntimeError("EXISTING_ANCHOR_OR_STATES")
    if lines(checked(PF,"-s","References"))!=("No pf starter references held",):
        raise RuntimeError("EXISTING_PF_REFERENCES")
    canonical=lines(checked(PF,"-n","-v","-a",ANCHOR,"-f","-",input=RULES))
    if canonical!=lines(RULES): raise RuntimeError("RULE_SYNTAX_READBACK_FAILED")
    evidence=collect()
    if evidence is None or evidence.protocol!="wireguard":
        raise RuntimeError("CONNECT_WIREGUARD_FIRST")
    if route_interface("1.1.1.1")!=evidence.interface:
        raise RuntimeError("WG_ROUTE_UNVERIFIED")
    service=run("/bin/launchctl","print","system/"+LABEL)
    if service.returncode==0:
        raise RuntimeError("PREVIOUS_WATCHDOG_LOADED")
    if read_json("lease.json") is not None:
        raise RuntimeError("PREVIOUS_TRIAL_REQUIRES_RESTORE")


def require_console_approval():
    if any(os.environ.get(k) for k in ("SSH_CONNECTION","SSH_CLIENT","SSH_TTY")):
        raise RuntimeError("SSH_ACTIVATION_REFUSED")
    if os.stat("/dev/console").st_uid <= 0:
        raise RuntimeError("CONSOLE_OWNER_REQUIRED")
    # The provider-console acceptance test must already have completed.
    for directory in ("twinconnect-pf-console-trial","twinconnect-pf-wireguard-trial"):
        path=Path("/private/var/run")/directory/"result.json"
        trusted(path.parent,True,True)
        trusted(path,private=True)
        value=json.loads(path.read_text())
        if value.get("restored") is not True or value.get("source")!="launchd":
            raise RuntimeError("CONSOLE_RECOVERY_TEST_REQUIRED")


def publish(state, reason, deadline=0):
    value={"version":1,"state":state,"reason":reason,"timestamp":int(time.time()),
           "expires_at":int(deadline),"session_limit":RECOVERY_SECONDS,
           "persistent":False}
    target=ROOT/"status.json"
    temp=ROOT/("status.next-"+secrets.token_hex(8))
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
    try:
        with os.fdopen(fd,"w") as stream:
            json.dump(value,stream,separators=(",",":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp,target)
    finally:
        temp.unlink(missing_ok=True)


def restore_locked():
    lease=read_json("lease.json")
    if lease is None:
        if anchor_rules(): raise RuntimeError('UNOWNED_ANCHOR_REFUSED')
        return True
    phase=lease.get("phase")
    if phase not in ("prepared","loading","enabling","owned","anchor_removed"):
        raise RuntimeError("LEASE_UNKNOWN")
    if phase not in ("prepared","anchor_removed"):
        current=anchor_rules()
        expected=lease.get("canonical")
        if not isinstance(expected,list) or len(expected)>20:
            raise RuntimeError("LEASE_RULES_INVALID")
        if current and current not in (tuple(expected),lines(RULES)):
            raise RuntimeError("UNEXPECTED_ANCHOR_RULES")
        if current:
            checked(PF,"-a",ANCHOR,"-F","rules")
        if anchor_rules():
            raise RuntimeError("ANCHOR_RESTORE_FAILED")
    token=lease.get("token")
    if token is not None:
        if not isinstance(token,str) or not re.fullmatch(r"[0-9]{1,20}",token):
            raise RuntimeError("TOKEN_INVALID")
        # If the reference was released before a crash, PF will be disabled.
        # Otherwise release only the exact token returned by our own -E.
        if pf_enabled():
            checked(PF,"-X",token)
    if pf_enabled():
        # The anchor is gone; do not globally disable other PF references.
        lease["phase"]="anchor_removed"
        write_json("lease.json",lease)
        return False
    (STATE/"lease.json").unlink(missing_ok=True)
    return True


def monitor_lease(lease):
    if not pf_enabled():
        raise RuntimeError("PF_DISABLED_UNEXPECTEDLY")
    current=anchor_rules()
    if lease.get("locked"):
        if current!=lines(RULES):
            raise RuntimeError("LOCKED_POLICY_DRIFT")
        return "locked"
    if current!=tuple(lease["canonical"]):
        raise RuntimeError("ACTIVE_POLICY_DRIFT")
    pid,iface=lease["pid"],lease["interface"]
    valid=False
    try:
        valid=(process_command(pid)==WG_BIN+" -f "+iface and
               route_interface("1.1.1.1")==iface and
               route_interface("129.0.0.1")==iface)
    except Exception:
        pass
    if valid:
        return "active"
    # Keep the lock closed after loss; never re-open for a new process.
    checked(PF,"-a",ANCHOR,"-f","-",input=RULES)
    if anchor_rules()!=lines(RULES):
        raise RuntimeError("CLOSED_POLICY_READBACK_FAILED")
    lease["locked"]=True
    write_json("lease.json",lease)
    return "locked"


def watchdog(nonce):
    lease=read_json("lease.json")
    if lease is None or lease.get("nonce")!=nonce:
        return
    prior=read_json("ready.json")
    # launchd retries a crashed watchdog. Never extend the original lease;
    # recover immediately if a running activation lost its watchdog.
    if prior and prior.get("nonce")==nonce:
        deadline=prior["deadline"]
        end=time.monotonic()
    elif lease.get("phase")=="prepared":
        end=time.monotonic()+RECOVERY_SECONDS
        deadline=time.time()+RECOVERY_SECONDS
        write_json("ready.json",{"nonce":nonce,"deadline":int(deadline)})
    else:
        deadline=time.time()
        end=time.monotonic()
    while time.monotonic()<end:
        try:
            with lock():
                lease=read_json("lease.json")
                if lease is None or lease.get("nonce")!=nonce:
                    return
                if lease.get("phase")=="owned":
                    state=monitor_lease(lease)
                    publish(state,"KS_WG_ACTIVE" if state=="active" else "KS_TUNNEL_LOST_LOCKED",deadline)
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
            publish("fault","KS_POLICY_UNVERIFIED",deadline)
            # No early fail-open. The bounded recovery deadline still
            # applies; never claim protection while readback is unknown.
        time.sleep(1)
    for _ in range(4):
        try:
            with lock():
                current=read_json("lease.json")
                if current is None or current.get("nonce")!=nonce:
                    return
                good=restore_locked()
                publish("off" if good else "fault",
                        "KS_SESSION_EXPIRED" if good else "KS_RECOVERY_REQUIRED")
                write_json("result.json",{"nonce":nonce,"restored":good,"source":"launchd"})
            return
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
            time.sleep(0.5)
    publish("fault","KS_RECOVERY_REQUIRED")
    write_json("result.json",{"nonce":nonce,"restored":False,"source":"launchd"})


def start_watchdog(nonce):
    payload={"Label":LABEL,"ProgramArguments":["/usr/bin/python3","-I",str(SCRIPT),"--watchdog",nonce],
             "RunAtLoad":True,"KeepAlive":{"SuccessfulExit":False},"ThrottleInterval":2}
    # This is a transient launchd job, not a boot-time firewall service.
    fd=os.open(PLIST,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as f:
        plistlib.dump(payload,f); f.flush(); os.fsync(f.fileno())
    checked("/usr/bin/plutil","-lint",str(PLIST))
    checked("/bin/launchctl","bootstrap","system",str(PLIST))
    for _ in range(40):
        ready=read_json("ready.json")
        if ready and ready.get("nonce")==nonce:
            status=checked("/bin/launchctl","print","system/"+LABEL)
            if not re.search(r"(?m)^\s*state = running\s*$",status):
                raise RuntimeError("WATCHDOG_NOT_RUNNING")
            return
        time.sleep(0.1)
    raise RuntimeError("WATCHDOG_NOT_READY")


def cleanup_job():
    result=run("/bin/launchctl","bootout","system/"+LABEL)
    if result.returncode==0 or run("/bin/launchctl","print","system/"+LABEL).returncode!=0:
        PLIST.unlink(missing_ok=True)


def enable():
    require_console_approval()
    with lock():
        # A completed prior transient job is harmless; only clean our own
        # job when its lease and private anchor are definitely absent.
        if read_json("lease.json") is None and not anchor_rules():
            cleanup_job()
        preflight()
        evidence=collect()
        if evidence is None or evidence.protocol!="wireguard":
            raise RuntimeError("CONNECT_WIREGUARD_FIRST")
        rules=evidence.rules()
        canonical=lines(checked(PF,"-n","-v","-a",ANCHOR,"-f","-",input=rules))
        if not canonical or canonical[-1]!="block drop quick all":
            raise RuntimeError("WG_RULES_INVALID")
        nonce=secrets.token_hex(16)
        lease={"phase":"prepared","nonce":nonce,"token":None,
               "canonical":list(canonical),"pid":evidence.pid,
               "interface":evidence.interface,"locked":False}
        write_json("lease.json",lease)
        publish("arming","KS_ARMING")
        try:
            start_watchdog(nonce)
            if collect()!=evidence:
                raise RuntimeError("WG_EVIDENCE_CHANGED")
            lease["phase"]="loading"
            write_json("lease.json",lease)
            checked(PF,"-a",ANCHOR,"-f","-",input=rules)
            if anchor_rules()!=canonical:
                raise RuntimeError("ANCHOR_READBACK_FAILED")
            lease["phase"]="enabling"
            write_json("lease.json",lease)
            r=run(PF,"-E")
            m=re.search(r"(?im)^\s*Token\s*:\s*([0-9]{1,20})\s*$",r.stdout+"\n"+r.stderr)
            if m:
                lease["phase"]="owned"
                lease["token"]=m.group(1)
                write_json("lease.json",lease)
            if r.returncode or not m or not pf_enabled():
                raise RuntimeError("PF_ENABLE_UNVERIFIED")
            ready=read_json("ready.json")
            publish("active","KS_WG_ACTIVE",ready["deadline"])
            print("KS_SESSION_ENABLED",flush=True)
        except BaseException:
            try:
                good=restore_locked()
                publish("off" if good else "fault","KS_ENABLE_FAILED")
            except Exception:
                publish("fault","KS_RECOVERY_REQUIRED")
            raise


def main():
    setup()
    args=sys.argv[1:]
    if args==["--check"]:
        if read_json("lease.json") is None and not anchor_rules():
            publish("off","KS_READY_FOR_LOCAL_SESSION")
        print("KS_CONTROL_INSTALLED_NO_NETWORK_CHANGES")
    elif args==["--enable"]:
        enable()
    elif args==["--reset"]:
        with lock():
            restored=restore_locked()
            publish("off" if restored else "fault",
                    "KS_RESET" if restored else "KS_RECOVERY_REQUIRED")
            if restored:
                cleanup_job()
        print("KS_RESET_OK" if restored else "KS_RESET_REVIEW_REQUIRED")
        if not restored: raise RuntimeError("KS_RECOVERY_REQUIRED")
    elif len(args)==2 and args[0]=="--watchdog" and re.fullmatch(r"[0-9a-f]{32}",args[1]):
        watchdog(args[1])
    else:
        raise RuntimeError("ACTION_INVALID")


if __name__=="__main__":
    try:
        main()
    except (ValueError,OSError,RuntimeError,subprocess.SubprocessError) as exc:
        reason=str(exc)
        print("KS_CONTROL_FAILED: "+(reason if re.fullmatch(r"[A-Z_]{3,80}",reason) else "RUNTIME_ERROR"),file=sys.stderr,flush=True)
        sys.exit(2)
