#!/usr/bin/env python3
"""WireGuard-family Kill Switch for the current macOS boot, until manual reset.

Local administrator approval and provider-console recovery are required.
The watchdog stays alive independently of the app and closes on restart.
No automatic timeout releases an owned firewall. This is not boot-time
protection, and does not claim support for other engines.
"""
from __future__ import annotations
import fcntl
import hashlib
import ipaddress
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
from unsigned_killswitch_attestation import collect, route_interface, process_command, WG_BIN, AWG_BIN, wg_uapi, root_private_json, openvpn_session_evidence
from unsigned_killswitch_policy import Transport, render_policy

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
RECOVERY_SECONDS=0
RECONNECT_SECONDS=60
ARMING_TIMEOUT=30
SESSION_MODE='until_reset'
WG_PROTOCOLS={'wireguard':WG_BIN,'amneziawg':AWG_BIN}
SUPPORTED_PROTOCOLS=frozenset(WG_PROTOCOLS)|{'openvpn'}


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
    if evidence is None or evidence.protocol not in SUPPORTED_PROTOCOLS:
        raise RuntimeError("CONNECT_SUPPORTED_VPN_FIRST")
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
           "persistent":False,"mode":SESSION_MODE}
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
        pending=lease.get("pending_canonical",[])
        if current and current not in (tuple(expected),tuple(pending),lines(RULES)):
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


WG_STATE=Path("/private/var/run/twinconnect-wireguard-route-guard/state.json")
WG_META=WG_STATE.with_name("tunnel-dns.json")


def reconnect_identity(evidence):
    try:
        if evidence.protocol=="openvpn":
            current,worker,digest=openvpn_session_evidence()
            state=root_private_json(Path("/private/var/run/twinconnect-full-route-guard/state.json"))
            peer=evidence.transports[0]
            baseline=state.get("baseline_ip")
            if (current!=evidence or state.get("worker_pid")!=worker or
                    not isinstance(baseline,str) or not ipaddress.IPv4Address(baseline).is_global):
                return None
            return {"protocol":"openvpn","digest":digest,"ip":peer.ip,"port":peer.port,
                    "transport":peer.proto,"uplink":evidence.uplink,"gateway":state["gateway"],
                    "baseline_ip":baseline}
        state=root_private_json(WG_STATE)
        meta=root_private_json(WG_META)
        digest=meta.get("profile_digest")
        baseline=state.get("baseline_ip")
        transport=evidence.transports[0]
        if (evidence.protocol not in SUPPORTED_PROTOCOLS or len(evidence.transports)!=1 or
                state.get("protocol_code","wireguard")!=evidence.protocol or
                state.get("worker_pid")!=evidence.pid or
                state.get("full_interface")!=evidence.interface or
                state.get("interface")!=evidence.uplink or
                state.get("endpoint")!=transport.ip or
                meta.get("interface")!=evidence.interface or
                meta.get("endpoint")!=transport.ip+":"+str(transport.port) or
                not isinstance(digest,str) or not re.fullmatch(r"[0-9a-f]{64}",digest) or
                not isinstance(baseline,str) or not ipaddress.IPv4Address(baseline).is_global):
            return None
        return {"protocol":evidence.protocol,"digest":digest,"ip":transport.ip,"port":transport.port,"transport":"udp",
                "uplink":evidence.uplink,"gateway":state["gateway"],"baseline_ip":baseline}
    except (OSError,ValueError,KeyError,TypeError):
        return None


def bootstrap_rules(identity, tunnel=None):
    transport=Transport(identity["ip"],identity["port"],identity.get("transport","udp"))
    uplink=identity["uplink"]
    if not re.fullmatch(r"en[0-9]{1,3}",uplink) or ipaddress.ip_address(transport.ip).version!=4:
        raise ValueError("KS_BOOTSTRAP_TRANSPORT_INVALID")
    if tunnel is not None:
        return render_policy(tunnel,uplink,(transport,))
    # Only the exact previously attested root WireGuard UDP transport;
    # no app data, DNS, control-plane HTTPS or generic direct bypass.
    rules=render_policy("utun9999",uplink,(transport,))
    return rules.replace("pass quick on utun9999 all no state\n","")


def session_deadline(lease):
    ready=read_json("ready.json")
    if (not ready or ready.get("nonce")!=lease.get("nonce") or
            ready.get("mode")!=SESSION_MODE or ready.get("deadline")!=0 or
            lease.get("mode")!=SESSION_MODE):
        raise RuntimeError("KS_SESSION_NOT_AUTHORIZED")
    job=checked("/bin/launchctl","print","system/"+LABEL)
    if "state = running" not in job or lease["nonce"] not in job:
        raise RuntimeError("KS_RECOVERY_NOT_RUNNING")
    # No automatic unlock. Only a reconnect attempt has a time limit.
    return 0


def replace_owned_policy(lease,rules,**changes):
    if lease.get("phase")!="owned" or not pf_enabled():
        raise RuntimeError("KS_LEASE_NOT_ACTIVE")
    current=anchor_rules()
    if current not in (tuple(lease["canonical"]),tuple(lease.get("pending_canonical",[]))):
        raise RuntimeError("KS_POLICY_DRIFT")
    canonical=lines(checked(PF,"-n","-v","-a",ANCHOR,"-f","-",input=rules))
    if not canonical or canonical[-1]!="block drop quick all":
        raise RuntimeError("KS_POLICY_INVALID")
    lease["pending_canonical"]=list(canonical)
    write_json("lease.json",lease)
    checked(PF,"-a",ANCHOR,"-f","-",input=rules)
    if anchor_rules()!=canonical:
        raise RuntimeError("KS_POLICY_READBACK_FAILED")
    lease.update(changes)
    lease["canonical"]=list(canonical)
    lease.pop("pending_canonical",None)
    write_json("lease.json",lease)


def close_lease(lease):
    replace_owned_policy(lease,RULES,locked=True,reconnect_stage=None,
                         reconnect_until=0)
    publish("locked","KS_TUNNEL_LOST_LOCKED",session_deadline(lease))


def before_wg_disconnect(pid,interface):
    """Close the firewall BEFORE the guard removes any VPN route."""
    with lock():
        lease=read_json("lease.json")
        if lease is None:
            return
        if (lease.get("phase")!="owned" or
                lease.get("pid")!=pid or lease.get("interface")!=interface):
            raise RuntimeError("KS_DISCONNECT_LEASE_MISMATCH")
        if not lease.get("locked") or lease.get("reconnect_stage"):
            close_lease(lease)
        elif anchor_rules()!=lines(RULES) or not pf_enabled():
            raise RuntimeError("KS_CLOSED_POLICY_UNVERIFIED")


def begin_reconnect(raw,protocol):
    with lock():
        lease=read_json("lease.json")
        if lease is None:
            return None
        if protocol not in SUPPORTED_PROTOCOLS or not lease.get("locked") or lease.get("reconnect_stage"):
            raise RuntimeError("WG_KS_RECONNECT_NOT_ALLOWED")
        identity=lease.get("reconnect_identity")
        if not isinstance(identity,dict) or identity.get("protocol")!=protocol or not isinstance(raw,str) or (
                hashlib.sha256(raw.encode("utf-8")).hexdigest()!=identity.get("digest")):
            raise RuntimeError("WG_KS_ORIGINAL_PROFILE_REQUIRED")
        deadline=session_deadline(lease)
        if anchor_rules()!=lines(RULES):
            raise RuntimeError("WG_KS_LOCK_NOT_VERIFIED")
        until=time.time()+RECONNECT_SECONDS
        replace_owned_policy(lease,bootstrap_rules(identity),locked=True,
                             reconnect_stage="handshake",reconnect_until=until)
        publish("locked","KS_RECONNECTING",deadline)
        return identity.copy()


def reconnect_context(stage=None):
    """Read-only proof for the existing root WireGuard route guard."""
    with lock():
        lease=read_json("lease.json")
        if lease is None or lease.get("reconnect_stage") not in ("handshake","route"):
            return None
        if stage is not None and lease["reconnect_stage"]!=stage:
            raise RuntimeError("KS_RECONNECT_STAGE_INVALID")
        session_deadline(lease)
        if (lease.get("phase")!="owned" or not lease.get("locked") or
                time.time()>=lease.get("reconnect_until",0) or
                not pf_enabled() or anchor_rules()!=tuple(lease["canonical"])):
            raise RuntimeError("KS_RECONNECT_UNVERIFIED")
        identity=lease["reconnect_identity"].copy()
        identity.update({"stage":lease["reconnect_stage"],"pid":lease["pid"],
                         "interface":lease["interface"],"route_worker":lease.get("route_worker")})
        return identity


def attach_openvpn_reconnect(worker,iface):
    with lock():
        lease=read_json("lease.json")
        if not lease or lease.get("reconnect_stage")!="handshake":
            raise RuntimeError("KS_RECONNECT_STAGE_INVALID")
        identity=lease["reconnect_identity"]
        session_deadline(lease)
        evidence,actual_worker,digest=openvpn_session_evidence()
        if (identity.get("protocol")!="openvpn" or actual_worker!=worker or
                evidence.interface!=iface or evidence.uplink!=identity["uplink"] or
                evidence.transports!=(Transport(identity["ip"],identity["port"],identity["transport"]),) or
                digest!=identity["digest"] or time.time()>=lease.get("reconnect_until",0)):
            raise RuntimeError("KS_RECONNECT_PEER_UNVERIFIED")
        replace_owned_policy(lease,bootstrap_rules(identity,iface),
                             pid=evidence.pid,interface=iface,reconnect_stage="route",
                             route_worker=worker)
        return evidence.pid


def openvpn_active_recovery(worker,iface):
    with lock():
        lease=read_json("lease.json")
        if (not lease or lease.get("locked") or lease.get("route_worker")!=worker or
                lease.get("interface")!=iface or lease.get("reconnect_identity",{}).get("protocol")!="openvpn"):
            return False
        session_deadline(lease)
        return monitor_lease(lease)=="active"


def before_openvpn_disconnect(worker,iface):
    with lock():
        lease=read_json("lease.json")
        if lease is None:
            return
        identity=lease.get("reconnect_identity",{})
        if identity.get("protocol")!="openvpn":
            raise RuntimeError("KS_DISCONNECT_LEASE_MISMATCH")
        if lease.get("interface")!=iface or lease.get("route_worker")!=worker:
            raise RuntimeError("KS_DISCONNECT_LEASE_MISMATCH")
        if not lease.get("locked") or lease.get("reconnect_stage"):
            close_lease(lease)
        elif anchor_rules()!=lines(RULES) or not pf_enabled():
            raise RuntimeError("KS_CLOSED_POLICY_UNVERIFIED")


def attach_reconnect(pid,iface):
    with lock():
        lease=read_json("lease.json")
        if not lease or lease.get("reconnect_stage")!="handshake":
            raise RuntimeError("KS_RECONNECT_STAGE_INVALID")
        identity=lease["reconnect_identity"]
        session_deadline(lease)
        if (time.time()>=lease.get("reconnect_until",0) or
                identity.get("protocol") not in WG_PROTOCOLS or
                process_command(pid)!=WG_PROTOCOLS[identity["protocol"]]+" -f "+iface or
                wg_uapi(identity["protocol"],iface)!=Transport(identity["ip"],identity["port"],identity.get("transport","udp")) or
                route_interface(identity["ip"])!=identity["uplink"]):
            raise RuntimeError("KS_RECONNECT_PEER_UNVERIFIED")
        replace_owned_policy(lease,bootstrap_rules(identity,iface),
                             pid=pid,interface=iface,reconnect_stage="route")


def complete_reconnect(pid,iface):
    with lock():
        lease=read_json("lease.json")
        if not lease or lease.get("reconnect_stage")!="route":
            raise RuntimeError("KS_RECONNECT_STAGE_INVALID")
        deadline=session_deadline(lease)
        evidence=collect()
        identity=lease["reconnect_identity"]
        if (time.time()>=lease.get("reconnect_until",0) or evidence is None or
                evidence.protocol!=identity.get("protocol") or evidence.pid!=pid or evidence.interface!=iface or
                evidence.uplink!=identity["uplink"] or
                evidence.transports!=(Transport(identity["ip"],identity["port"],identity.get("transport","udp")),) or
                anchor_rules()!=tuple(lease["canonical"]) or not pf_enabled()):
            raise RuntimeError("KS_RECONNECT_ROUTE_UNVERIFIED")
        lease.update(locked=False,reconnect_stage=None,reconnect_until=0)
        write_json("lease.json",lease)
        publish("active","KS_WG_ACTIVE",deadline)


def abort_reconnect(protocol=None):
    with lock():
        lease=read_json("lease.json")
        if lease and lease.get("reconnect_stage") and (protocol is None or lease.get("reconnect_identity",{}).get("protocol")==protocol):
            close_lease(lease)


def monitor_lease(lease):
    if not pf_enabled():
        raise RuntimeError("PF_DISABLED_UNEXPECTEDLY")
    current=anchor_rules()
    if lease.get("pending_canonical"):
        # Crash in a policy transition: close rather than adopt it.
        close_lease(lease)
        return "locked"
    if lease.get("reconnect_stage"):
        if current!=tuple(lease["canonical"]):
            raise RuntimeError("RECONNECT_POLICY_DRIFT")
        expired=time.time()>=lease.get("reconnect_until",0)
        if not expired and lease.get("reconnect_stage")=="route":
            try:
                identity=lease["reconnect_identity"]
                iface=lease["interface"]
                if identity.get("protocol")=="openvpn":
                    evidence,worker,digest=openvpn_session_evidence()
                    expired=(evidence.pid!=lease["pid"] or worker!=lease.get("route_worker") or
                             evidence.interface!=iface or digest!=identity["digest"] or
                             evidence.transports!=(Transport(identity["ip"],identity["port"],identity["transport"]),))
                else:
                    expired=(identity.get("protocol") not in WG_PROTOCOLS or
                         process_command(lease["pid"])!=WG_PROTOCOLS[identity["protocol"]]+" -f "+iface or
                         wg_uapi(identity["protocol"],iface)!=Transport(identity["ip"],identity["port"],identity.get("transport","udp")))
            except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
                expired=True
        if expired:
            close_lease(lease)
        return "locked"
    if lease.get("locked"):
        if current!=lines(RULES):
            raise RuntimeError("LOCKED_POLICY_DRIFT")
        return "locked"
    if current!=tuple(lease["canonical"]):
        raise RuntimeError("ACTIVE_POLICY_DRIFT")
    pid,iface=lease["pid"],lease["interface"]
    valid=False
    try:
        identity=lease.get("reconnect_identity")
        protocol=identity.get("protocol") if isinstance(identity,dict) else None
        if protocol=="openvpn":
            evidence=collect()
            valid=(evidence is not None and evidence.protocol=="openvpn" and
                   evidence.pid==pid and evidence.interface==iface and
                   evidence.uplink==identity["uplink"] and
                   evidence.transports==(Transport(identity["ip"],identity["port"],identity["transport"]),))
        else:
            valid=(protocol in WG_PROTOCOLS and
               process_command(pid)==WG_PROTOCOLS[protocol]+" -f "+iface and
               route_interface("1.1.1.1")==iface and
               route_interface("129.0.0.1")==iface and
               wg_uapi(protocol,iface)==Transport(identity["ip"],identity["port"],identity.get("transport","udp")) and
               route_interface(identity["ip"])==identity["uplink"])
    except Exception:
        pass
    if valid:
        return "active"
    close_lease(lease)
    return "locked"


def watchdog_tick(nonce,restarted=False):
    """One independent service tick; never release an owned firewall."""
    with lock():
        lease=read_json("lease.json")
        if lease is None or lease.get("nonce")!=nonce:
            return False
        if lease.get("mode")!=SESSION_MODE:
            raise RuntimeError("KS_SESSION_MODE_INVALID")
        if lease.get("phase")=="owned":
            if restarted:
                # Never trust an old interface or interrupted handshake after
                # watchdog restart. Reconnect needs a fresh peer handshake.
                close_lease(lease)
                state="locked"
            else:
                state=monitor_lease(lease)
            reason=("KS_WG_ACTIVE" if state=="active" else
                    "KS_RECONNECTING" if lease.get("reconnect_stage") else
                    "KS_TUNNEL_LOST_LOCKED")
            publish(state,reason)
        elif lease.get("phase")=="prepared":
            # No kernel change happened yet. This is the only timed cleanup
            # of a preparation abandoned by its local authorization process.
            started=lease.get("created_at",0)
            if time.time()-started>ARMING_TIMEOUT and not anchor_rules() and not pf_enabled():
                if not restore_locked():
                    raise RuntimeError("KS_RECOVERY_REQUIRED")
                publish("off","KS_ARMING_ABANDONED")
                return False
        else:
            # Unknown acquisition progress, token gap or partial reset:
            # never silently clear rules or disable a foreign PF reference.
            publish("fault","KS_RECOVERY_REQUIRED")
        return True


def watchdog(nonce):
    lease=read_json("lease.json")
    if lease is None or lease.get("nonce")!=nonce:
        return
    if lease.get("mode")!=SESSION_MODE:
        raise RuntimeError("KS_SESSION_MODE_INVALID")
    prior=read_json("ready.json")
    restarted=bool(prior and prior.get("nonce")==nonce)
    if not restarted:
        if lease.get("phase")!="prepared":
            raise RuntimeError("KS_WATCHDOG_START_UNVERIFIED")
        write_json("ready.json",{"nonce":nonce,"deadline":0,"mode":SESSION_MODE})
    while True:
        try:
            if not watchdog_tick(nonce,restarted):
                return
            restarted=False
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
            publish("fault","KS_POLICY_UNVERIFIED")
            # Continue monitoring and keep owned rules; manual recovery is
            # available locally. Never restore the direct network on timeout.
        time.sleep(1)


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
        if ready and ready.get("nonce")==nonce and ready.get("mode")==SESSION_MODE and ready.get("deadline")==0:
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
        if evidence is None or evidence.protocol not in SUPPORTED_PROTOCOLS:
            raise RuntimeError("CONNECT_SUPPORTED_VPN_FIRST")
        rules=evidence.rules()
        canonical=lines(checked(PF,"-n","-v","-a",ANCHOR,"-f","-",input=rules))
        if not canonical or canonical[-1]!="block drop quick all":
            raise RuntimeError("WG_RULES_INVALID")
        nonce=secrets.token_hex(16)
        identity=reconnect_identity(evidence)
        if identity is None:
            raise RuntimeError("WG_RECONNECT_PROFILE_REQUIRED")
        lease={"phase":"prepared","nonce":nonce,"token":None,
               "mode":SESSION_MODE,"created_at":time.time(),
               "canonical":list(canonical),"pid":evidence.pid,
               "interface":evidence.interface,"locked":False,
               "reconnect_identity":identity}
        if evidence.protocol=="openvpn":
            _,worker,_=openvpn_session_evidence()
            lease["route_worker"]=worker
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
            if session_deadline(lease)!=0:
                raise RuntimeError("KS_SESSION_NOT_AUTHORIZED")
            publish("active","KS_WG_ACTIVE")
            print("KS_ENABLED_UNTIL_RESET",flush=True)
        except BaseException:
            try:
                current=read_json("lease.json")
                if current and current.get("phase")=="owned":
                    close_lease(current)
                    publish("locked","KS_ENABLE_INTERRUPTED_LOCKED")
                elif current and current.get("phase")=="prepared" and not pf_enabled() and not anchor_rules():
                    good=restore_locked()
                    publish("off" if good else "fault","KS_ENABLE_FAILED")
                else:
                    publish("fault","KS_RECOVERY_REQUIRED")
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
