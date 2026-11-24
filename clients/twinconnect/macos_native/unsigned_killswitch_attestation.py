"""Read-only privileged transport evidence for the native PF policy.

Never trust UI state, generic utun interfaces, or app-supplied addresses.
This module produces private evidence only inside a trusted root runtime.
The command-line report exposes protocol/readiness, not keys or endpoints.
"""
from __future__ import annotations
from dataclasses import dataclass
import ipaddress
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import stat
import subprocess
import sys
import time

from unsigned_killswitch_policy import Transport, render_policy, validate_kernel_syntax

WG_ROOT = Path("/private/var/run/twinconnect-wireguard-route-guard")
CISCO_ROOT = Path("/private/var/run/twinconnect-cisco-route-guard")
OPENVPN_ROOT = Path("/private/var/run/twinconnect-full-route-guard")
L2TP_ROOT = Path("/private/var/run/twinconnect-l2tp-route-guard")
WG_BIN = "/Library/PrivilegedHelperTools/TwinConnectWireGuard/wireguard-go"
AWG_BIN = "/Library/PrivilegedHelperTools/TwinConnectWireGuard/amneziawg-go"
CISCO_BIN = "/Library/PrivilegedHelperTools/TwinConnectCisco/openconnect-runtime/bin/openconnect"
TUN_ROOT = Path("/Library/PrivilegedHelperTools/TwinConnectTUN")
TUN_PROTOCOLS=frozenset(('v2ray','hysteria2','tuic','anytls','socks5','snell','naive','shadowtls','mieru','trusttunnel','sudoku'))

@dataclass(frozen=True)
class Evidence:
    protocol: str
    interface: str
    uplink: str
    transports: tuple[Transport, ...]
    pid: int

    def rules(self):
        return render_policy(self.interface, self.uplink, self.transports)


def run(*args, timeout=4):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                          check=False, env={"PATH":"/usr/bin:/bin:/usr/sbin:/sbin",
                                            "LC_ALL":"C"})


def root_private_bytes(path: Path):
    # Open without following links, check the descriptor, and read bounded
    # bytes. An untrusted pathname must not become a root-read primitive.
    info = path.parent.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise ValueError("KS_GUARD_DIRECTORY_UNTRUSTED")
    with os.fdopen(os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK),"rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077 or info.st_nlink != 1 or info.st_size > 262144:
            raise ValueError("KS_GUARD_STATE_UNTRUSTED")
        raw=stream.read(262145)
    if len(raw)>262144:
        raise ValueError("KS_GUARD_STATE_TOO_LARGE")
    return raw


def root_private_json(path: Path):
    data=json.loads(root_private_bytes(path))
    if not isinstance(data,dict):
        raise ValueError("KS_GUARD_STATE_INVALID")
    return data


def route_interface(destination):
    result=run("/sbin/route","-n","get",destination)
    if result.returncode:
        return None
    match=re.search(r"(?m)^\s*interface:\s+([a-z0-9]+)\s*$",result.stdout)
    return match.group(1) if match else None


def process_command(pid):
    if type(pid) is not int or pid<=1:
        raise ValueError("KS_ENGINE_PID_INVALID")
    result=run("/bin/ps","-p",str(pid),"-o","uid=","-o","command=")
    if result.returncode:
        raise ValueError("KS_ENGINE_NOT_RUNNING")
    match=re.fullmatch(r"\s*0\s+([^\r\n]+)\s*",result.stdout)
    if not match:
        raise ValueError("KS_ENGINE_NOT_ROOT")
    return match.group(1).strip()


def checked_lease(state, protocol):
    if not isinstance(state,dict) or state.get("mode")!="leased":
        raise ValueError("KS_ENGINE_LEASE_NOT_ACTIVE")
    deadline=state.get("deadline")
    if type(deadline) not in (int,float) or not math.isfinite(deadline) or not time.time()<deadline:
        raise ValueError("KS_ENGINE_LEASE_EXPIRED")
    iface=state.get("full_interface")
    uplink=state.get("interface")
    pid=state.get("worker_pid")
    if not isinstance(iface,str) or not re.fullmatch(r"utun[0-9]{1,4}",iface):
        raise ValueError("KS_TUNNEL_INTERFACE_INVALID")
    if not isinstance(uplink,str) or not re.fullmatch(r"en[0-9]{1,3}",uplink):
        raise ValueError("KS_UPLINK_INTERFACE_INVALID")
    if type(pid) is not int or pid<=1:
        raise ValueError("KS_ENGINE_PID_INVALID")
    endpoint=state.get("endpoint")
    if not isinstance(endpoint,str) or not ipaddress.ip_address(endpoint).is_global:
        raise ValueError("KS_ENDPOINT_INVALID")
    if route_interface("1.1.1.1")!=iface or route_interface("129.0.0.1")!=iface:
        raise ValueError("KS_TUNNEL_ROUTE_UNVERIFIED")
    if route_interface(endpoint)!=uplink:
        raise ValueError("KS_TRANSPORT_ROUTE_UNVERIFIED")
    return iface,uplink,pid,endpoint


def wg_uapi(protocol, iface):
    directory="amneziawg" if protocol=="amneziawg" else "wireguard"
    path=Path("/var/run")/directory/(iface+".sock")
    info=path.lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=0:
        raise ValueError("KS_WG_SOCKET_UNTRUSTED")
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(2)
        connection.connect(str(path))
        connection.sendall(b"get=1\n\n")
        data=bytearray()
        while b"\n\n" not in data and len(data)<32768:
            part=connection.recv(4096)
            if not part: break
            data.extend(part)
    # UAPI may contain private keys. Never log/return the entire response.
    try:
        text=data.decode("ascii")
    except UnicodeError:
        raise ValueError("KS_WG_UAPI_INVALID") from None
    if len(data)>=32768 or not text.endswith("\n\n") or not re.search(r"(?m)^errno=0$",text):
        raise ValueError("KS_WG_UAPI_INVALID")
    endpoints=re.findall(r"(?m)^endpoint=([0-9.]+):([0-9]{1,5})$",text)
    handshakes=re.findall(r"(?m)^last_handshake_time_sec=([0-9]+)$",text)
    if len(endpoints)!=1 or len(handshakes)!=1 or abs(time.time()-int(handshakes[0]))>180:
        raise ValueError("KS_WG_HANDSHAKE_UNVERIFIED")
    return Transport(endpoints[0][0],int(endpoints[0][1]),"udp")


def wireguard_evidence(state):
    protocol=state.get("protocol_code","wireguard")
    if protocol not in ("wireguard","amneziawg"):
        raise ValueError("KS_WG_PROTOCOL_INVALID")
    iface,uplink,pid,endpoint=checked_lease(state,protocol)
    expected=(AWG_BIN if protocol=="amneziawg" else WG_BIN)+" -f "+iface
    if process_command(pid)!=expected:
        raise ValueError("KS_ENGINE_IDENTITY_UNVERIFIED")
    transport=wg_uapi(protocol,iface)
    if transport.ip!=endpoint:
        raise ValueError("KS_TRANSPORT_ENDPOINT_CHANGED")
    return Evidence(protocol,iface,uplink,(transport,),pid)


OPENVPN_APP=Path("/private/var/run/twinconnect-openvpn-app")
OPENVPN_ENGINES=("/usr/local/opt/openvpn/sbin/openvpn",
                 "/opt/homebrew/opt/openvpn/sbin/openvpn")


def openvpn_session_evidence():
    """Attest the current authenticated child and its exact live socket."""
    session=root_private_json(OPENVPN_APP/"state.json")
    meta=root_private_json(OPENVPN_APP/"profile-meta.json")
    iface=session.get("interface")
    worker=session.get("worker_pid")
    pid=session.get("engine_pid")
    if (session.get("state") not in ("tunnel_established_unrouted",
             "tunnel_egress_verified_unrouted") or
            type(session.get("deadline")) not in (int,float) or
            not time.time()<session["deadline"] or
            type(worker) is not int or worker<=1 or
            type(pid) is not int or pid<=1 or
            not isinstance(iface,str) or not re.fullmatch(r"utun[0-9]{1,4}",iface)):
        raise ValueError("KS_OPENVPN_SESSION_UNVERIFIED")
    workers=observed_tun_processes()
    child=workers.get(pid)
    parent=workers.get(worker)
    helper="/Library/PrivilegedHelperTools/TwinConnectOpenVPN/macos_native/openvpn_app_session.py"
    if (not parent or not parent[1].endswith(" "+helper+" worker") or
            not child or child[0]!=worker or
            not any(child[1].startswith(binary+" --config "+str(OPENVPN_APP/"session.ovpn")+" ")
                    for binary in OPENVPN_ENGINES)):
        raise ValueError("KS_OPENVPN_ENGINE_UNVERIFIED")
    digest=meta.get("digest")
    if meta.get("single_remote") is not True or not isinstance(digest,str) or not re.fullmatch(r"[0-9a-f]{64}",digest):
        raise ValueError("KS_OPENVPN_PROFILE_UNVERIFIED")
    # The root worker records only the exact authenticated remote after
    # OpenVPN's Initialization Sequence Completed. Cross-check live sockets.
    if session.get("transport") not in ("tcp","udp"):
        raise ValueError("KS_OPENVPN_TRANSPORT_NOT_ATTESTED")
    peer=Transport(session.get("endpoint"),session.get("port"),session["transport"])
    if live_peers(pid)!={peer}:
        raise ValueError("KS_OPENVPN_SOCKET_UNVERIFIED")
    uplink=route_interface(peer.ip)
    if not isinstance(uplink,str) or not re.fullmatch(r"en[0-9]{1,3}",uplink):
        raise ValueError("KS_TRANSPORT_ROUTE_UNVERIFIED")
    return Evidence("openvpn",iface,uplink,(peer,),pid),worker,digest


def openvpn_evidence(state):
    if not isinstance(state,dict) or state.get("mode")!="leased":
        raise ValueError("KS_OPENVPN_TRANSPORT_NOT_ATTESTED")
    evidence,worker,_=openvpn_session_evidence()
    deadline=state.get("deadline")
    if (type(deadline) not in (int,float) or not math.isfinite(deadline) or
            not time.time()<deadline or state.get("worker_pid")!=worker or
            state.get("interface")!=evidence.interface or
            state.get("original_interface")!=evidence.uplink or
            state.get("endpoint")!=evidence.transports[0].ip or
            any(route_interface(ip)!=evidence.interface for ip in ("1.0.0.1","129.0.0.1"))):
        raise ValueError("KS_OPENVPN_ROUTE_UNVERIFIED")
    return evidence


def cisco_tcp_transport(pid,endpoint):
    if not process_command(pid).startswith(CISCO_BIN+" "):
        raise ValueError("KS_ENGINE_IDENTITY_UNVERIFIED")
    result=run("/usr/sbin/lsof","-nP","-a","-p",str(pid),"-iTCP","-sTCP:ESTABLISHED")
    if result.returncode:
        raise ValueError("KS_TRANSPORT_UNATTESTED")
    peers=set()
    for line in result.stdout.splitlines():
        match=re.search(r"TCP\s+[0-9.]+:[0-9]+->([0-9.]+):([0-9]+)\s+\(ESTABLISHED\)",line)
        if match:
            peers.add(Transport(match.group(1),int(match.group(2)),"tcp"))
    if len(peers)!=1 or next(iter(peers)).ip!=endpoint:
        raise ValueError("KS_TRANSPORT_UNATTESTED")
    # OpenConnect may also use DTLS. Until that UDP association is
    # independently attested, do not claim a complete live policy.
    udp=run("/usr/sbin/lsof","-nP","-a","-p",str(pid),"-iUDP")
    if udp.returncode not in (0,1) or (udp.returncode==0 and len(udp.stdout.splitlines())>1):
        raise ValueError("KS_CISCO_DTLS_NOT_ATTESTED")
    return next(iter(peers))


def cisco_evidence(state):
    iface,uplink,pid,endpoint=checked_lease(state,"cisco")
    return Evidence("cisco",iface,uplink,(cisco_tcp_transport(pid,endpoint),),pid)


def observed_tun_processes():
    """Private process enumeration, never return raw command strings to UI."""
    out=run("/bin/ps","-axo","uid=,pid=,ppid=,command=")
    if out.returncode:
        raise ValueError("KS_PROCESS_LIST_UNAVAILABLE")
    result={}
    for line in out.stdout.splitlines():
        match=re.fullmatch(r"\s*0\s+(\d+)\s+(\d+)\s+([^\r\n]+)\s*",line)
        if match:
            result[int(match.group(1))]=(int(match.group(2)),match.group(3).strip())
    return result


TUN_INNER=ipaddress.ip_network("172.19.0.0/30")


def live_peers(pid, tun_interface=None):
    peers=set()
    for proto in ("TCP","UDP"):
        result=run("/usr/sbin/lsof","-nP","-a","-p",str(pid),"-i"+proto)
        if result.returncode not in (0,1):
            raise ValueError("KS_TRANSPORT_SOCKET_SCAN_FAILED")
        for line in result.stdout.splitlines():
            match=re.search(r"\b"+proto+r"\s+([0-9.]+):[0-9]+->([0-9.]+):([0-9]+)(?:\s|$)",line)
            if match and (proto!="TCP" or line.endswith("(ESTABLISHED)")):
                source,host,port=match.groups()
                src,dst=ipaddress.ip_address(source),ipaddress.ip_address(host)
                # The reviewed system-stack TUN uses a fixed /30. Only
                # sockets with BOTH ends inside it and both routes on the
                # attested interface are inner flows, never outer exceptions.
                if tun_interface and src in TUN_INNER and dst in TUN_INNER:
                    if route_interface(source)==tun_interface and route_interface(host)==tun_interface:
                        continue
                try:
                    peers.add(Transport(host,int(port),proto.lower()))
                except ValueError:
                    # A loopback listener is not an outer network transport.
                    if not dst.is_loopback:
                        raise
    return peers


def modern_outbound(config):
    rows=config.get("outbounds")
    if not isinstance(rows,list) or len(rows) not in (1,2) or any(not isinstance(o,dict) for o in rows):
        raise ValueError("KS_TUN_OUTBOUND_AMBIGUOUS")
    route=config.get("route")
    if not isinstance(route,dict) or route.get("final")!="proxy":
        raise ValueError("KS_TUN_ROUTE_POLICY_UNVERIFIED")
    if len(rows)==2:
        ss=[o for o in rows if o.get("type")=="shadowsocks" and o.get("tag")=="proxy"]
        st=[o for o in rows if o.get("type")=="shadowtls" and o.get("tag")=="shadowtls-transport"]
        if len(ss)!=1 or len(st)!=1 or ss[0].get("detour")!="shadowtls-transport":
            raise ValueError("KS_TUN_OUTBOUND_AMBIGUOUS")
        return "shadowtls",st[0],"tcp"
    row=rows[0]
    if row.get("tag")!="proxy":
        raise ValueError("KS_TUN_OUTBOUND_AMBIGUOUS")
    kind=row.get("type")
    known={"vless":("v2ray","tcp"),"hysteria2":("hysteria2","udp"),
           "tuic":("tuic","udp"),"anytls":("anytls","tcp"),
           "socks":("socks5","tcp"),"snell":("snell","tcp"),
           "naive":("naive","tcp"),"mieru":("mieru","tcp")}
    if kind not in known or row.get("detour") is not None:
        raise ValueError("KS_TUN_OUTBOUND_UNSUPPORTED")
    protocol,transport=known[kind]
    if kind=="mieru" and row.get("transport")!="TCP":
        raise ValueError("KS_TUN_TRANSPORT_UNSUPPORTED")
    if kind=="socks" and row.get("network") not in ("tcp",None):
        raise ValueError("KS_TUN_TRANSPORT_UNSUPPORTED")
    return protocol,row,transport


def secondary_evidence(processes, daemon_pid, primary_pid, path, iface, require_live=True, inner_iface=None):
    """Identify the real supervised TrustTunnel or Sudoku outer connection.

    This is evidence only, never proof that a PF policy is active.
    """
    candidates=[]
    for pid,(parent,cmd) in processes.items():
        if parent!=daemon_pid:
            continue
        sdk=path.with_suffix(".sudoku.json")
        tt=path.with_suffix(".tt.toml")
        if cmd==str(TUN_ROOT/"sudoku")+" -c "+str(sdk):
            candidates.append(("sudoku",pid,sdk))
        elif cmd==str(TUN_ROOT/"trusttunnel_client")+" --config "+str(tt)+" --loglevel error":
            candidates.append(("trusttunnel",pid,tt))
    if len(candidates)!=1:
        raise ValueError("KS_SECONDARY_TRANSPORT_NOT_ATTESTED")
    protocol,pid,profile=candidates[0]
    if protocol=="sudoku":
        row=root_private_json(profile)
        if (row.get("mode")!="client" or row.get("transport")!="tcp" or
                row.get("local_address")!="127.0.0.1"):
            raise ValueError("KS_SECONDARY_PROFILE_INVALID")
        addresses=[row.get("server_address")]
    else:
        # The root converter emits one JSON-compatible addresses array in
        # the endpoint section, and an explicit HTTP/2 transport. Never
        # parse or log credential/certificate fields.
        raw=root_private_bytes(profile).decode("utf-8")
        if raw.count("[endpoint]")!=1:
            raise ValueError("KS_SECONDARY_PROFILE_INVALID")
        endpoint=raw.split("[endpoint]",1)[1].split("\n[",1)[0]
        rows=re.findall(r"(?m)^addresses = (\[[^\r\n]+\])$",endpoint)
        if (len(rows)!=1 or
                re.findall(r'(?m)^upstream_protocol = "([^"]+)"$',endpoint)!=["http2"] or
                re.findall(r"(?m)^skip_verification = (\w+)$",endpoint)!=["false"]):
            raise ValueError("KS_SECONDARY_PROFILE_INVALID")
        addresses=json.loads(rows[0])
    if not isinstance(addresses,list) or not 1<=len(addresses)<=8:
        raise ValueError("KS_SECONDARY_PROFILE_INVALID")
    allowed=set()
    for value in addresses:
        if not isinstance(value,str) or not re.fullmatch(r"[0-9.]+:[0-9]{1,5}",value):
            raise ValueError("KS_SECONDARY_ENDPOINT_UNPINNED")
        host,port=value.rsplit(":",1)
        allowed.add(Transport(host,int(port),"tcp"))
    observed=live_peers(pid)
    if (require_live and not observed) or not observed.issubset(allowed) or live_peers(primary_pid,inner_iface):
        raise ValueError("KS_SECONDARY_TRANSPORT_NOT_ATTESTED")
    if not require_live:
        if len(allowed)!=1:
            raise ValueError("KS_SECONDARY_ENDPOINT_AMBIGUOUS")
        observed=allowed
    uplinks={route_interface(t.ip) for t in observed}
    if len(uplinks)!=1:
        raise ValueError("KS_TRANSPORT_ROUTE_UNVERIFIED")
    uplink=next(iter(uplinks))
    if not isinstance(uplink,str) or not re.fullmatch(r"en[0-9]{1,3}",uplink):
        raise ValueError("KS_TRANSPORT_ROUTE_UNVERIFIED")
    return Evidence(protocol,iface,uplink,
                    tuple(sorted(observed,key=lambda t:(t.ip,t.port,t.proto))),pid)


def tun_evidence(processes, require_live=True, with_path=False):
    # Use exact root-owned known process paths and a single live daemon
    # child. Never derive identity from a generic SOCKS picker or a filename
    # alone. Unknown endpoint or route evidence must fail closed.
    # Xcode's system python3 launcher resolves to a framework executable.
    # Accept only known interpreter paths, and cross-check the launchd PID.
    interpreter = (r"/(?:usr/bin/python3|Library/Developer/CommandLineTools/usr/bin/python3"
                   r"|Applications/Xcode\.app/Contents/Developer/Library/Frameworks/"
                   r"Python3\.framework/Versions/[0-9.]+/Resources/Python\.app/Contents/MacOS/Python)")
    daemon_pids={pid for pid,(_,cmd) in processes.items()
                 if re.fullmatch(interpreter+" "+
                    re.escape(str(TUN_ROOT/"unsigned_tun_daemon.py")),cmd)}
    service = run("/bin/launchctl","print","system/com.twinconnect.localtun")
    match = re.search(r"(?m)^\s*pid = (\d+)\s*$",service.stdout)
    if match and int(match.group(1)) not in daemon_pids:
        raise ValueError("KS_TUN_DAEMON_IDENTITY_UNVERIFIED")
    if match:
        daemon_pids.intersection_update({int(match.group(1))})
    elif daemon_pids:
        raise ValueError("KS_TUN_DAEMON_IDENTITY_UNVERIFIED")
    if not daemon_pids:
        return None
    if len(daemon_pids)!=1:
        raise ValueError("KS_TUN_DAEMON_AMBIGUOUS")
    daemon_pid=next(iter(daemon_pids))
    candidates=[]
    for pid,(parent,cmd) in processes.items():
        if parent!=daemon_pid:
            continue
        match=re.fullmatch(re.escape(str(TUN_ROOT))+
             r"/(sing-box|mbox) run -c ("+re.escape(str(TUN_ROOT))+
             r"/active-[0-9a-f]{32}\.json)",cmd)
        if match:
            candidates.append((pid,match.group(1),Path(match.group(2))))
    if not candidates:
        return None
    if len(candidates)!=1:
        raise ValueError("KS_TUN_ENGINE_AMBIGUOUS")
    pid,engine,path=candidates[0]
    config=root_private_json(path)
    iface=route_interface("1.1.1.1")
    if not isinstance(iface,str) or not re.fullmatch(r"utun[0-9]{1,4}",iface) or route_interface("129.0.0.1")!=iface:
        raise ValueError("KS_TUNNEL_ROUTE_UNVERIFIED")
    inbounds=config.get("inbounds",[])
    inner_iface=None
    if (len(inbounds)==1 and inbounds[0].get("type")=="tun" and
            inbounds[0].get("address")==["172.19.0.1/30"]):
        interface_info=run("/sbin/ifconfig",iface)
        if (interface_info.returncode==0 and
                re.search(r"(?m)^\s*inet 172\.19\.0\.1\s+-->\s+172\.19\.0\.1\s+netmask 0xfffffffc\b",interface_info.stdout)):
            inner_iface=iface
    protocol,outbound,transport=modern_outbound(config)
    if (engine=="mbox")!=(protocol=="mieru"):
        raise ValueError("KS_TUN_ENGINE_IDENTITY_UNVERIFIED")
    if outbound.get("server")=="127.0.0.1":
        if protocol!="socks5" or outbound.get("network")!="tcp":
            raise ValueError("KS_SECONDARY_PROFILE_INVALID")
        evidence=secondary_evidence(processes,daemon_pid,pid,path,iface,require_live,inner_iface)
        return (evidence,path,pid) if with_path else evidence
    if protocol=="socks5" and outbound.get("network")!="tcp":
        raise ValueError("KS_SOCKS_UDP_POLICY_NOT_ATTESTED")
    # For now, never resolve an unpinned domain while deriving an exception.
    # A DNS result alone does not establish the live transport identity.
    host=outbound.get("server")
    if not isinstance(host,str):
        raise ValueError("KS_TUN_ENDPOINT_NOT_PINNED")
    try:
        expected=Transport(host,outbound.get("server_port"),transport)
    except (TypeError,ValueError):
        raise ValueError("KS_TUN_ENDPOINT_NOT_PINNED") from None
    observed=live_peers(pid,inner_iface)
    if (require_live and observed!={expected}) or not observed.issubset({expected}):
        raise ValueError("KS_TUN_TRANSPORT_UNATTESTED")
    uplink=route_interface(expected.ip)
    if not isinstance(uplink,str) or not re.fullmatch(r"en[0-9]{1,3}",uplink):
        raise ValueError("KS_TRANSPORT_ROUTE_UNVERIFIED")
    evidence=Evidence(protocol,iface,uplink,(expected,),pid)
    return (evidence,path,pid) if with_path else evidence


def tun_session_identity(require_live=True):
    # The daemon writes metadata only after spawning its verified, root-owned
    # engine. Bind the exact runtime and console UID, not the selected UI row.
    item=tun_evidence(observed_tun_processes(),require_live,True)
    if item is None:
        raise ValueError("KS_TUN_SESSION_MISSING")
    evidence,path,primary=item
    meta=root_private_json(path.with_suffix(".meta"))
    digest=meta.get("digest")
    if (evidence.protocol not in TUN_PROTOCOLS or len(evidence.transports)!=1 or
            meta.get("primary_pid")!=primary or
            meta.get("owner")!=os.stat("/dev/console").st_uid or
            meta.get("config_sha256")!=hashlib.sha256(root_private_bytes(path)).hexdigest() or
            not isinstance(digest,str) or not re.fullmatch(r"[0-9a-f]{64}",digest)):
        raise ValueError("KS_TUN_PROFILE_UNVERIFIED")
    if evidence.protocol in ("trusttunnel","sudoku"):
        secondary=path.with_suffix(".tt.toml" if evidence.protocol=="trusttunnel" else ".sudoku.json")
        if meta.get("secondary_sha256")!=hashlib.sha256(root_private_bytes(secondary)).hexdigest():
            raise ValueError("KS_TUN_SECONDARY_PROFILE_UNVERIFIED")
    # Even an idle connection must still have the exact pinned transport.
    if require_live:
        static=tun_evidence(observed_tun_processes(),False)
        if static!=evidence:
            raise ValueError("KS_TUN_ENDPOINT_AMBIGUOUS")
    peer=evidence.transports[0]
    return evidence,{"protocol":evidence.protocol,"digest":digest,
                     "ip":peer.ip,"port":peer.port,"transport":peer.proto,
                     "uplink":evidence.uplink,"primary_pid":primary}


def read_guard(directory):
    try:
        return root_private_json(directory/"state.json")
    except FileNotFoundError:
        return None


def collect(require_tun_live=True):
    # A second active route guard invalidates ownership; never select a
    # winner by process enumeration order or a user's protocol preference.
    found=[]
    for name, directory in (("wireguard",WG_ROOT),("cisco",CISCO_ROOT),
                             ("openvpn",OPENVPN_ROOT),("l2tp",L2TP_ROOT)):
        state=read_guard(directory)
        if state:
            found.append((name,state))
    if len(found)>1:
        raise ValueError("KS_MULTIPLE_ENGINE_GUARDS")
    if found:
        name,state=found[0]
        if name=="wireguard": return wireguard_evidence(state)
        if name=="cisco": return cisco_evidence(state)
        if name=="openvpn": return openvpn_evidence(state)
        raise ValueError("KS_"+name.upper()+"_TRANSPORT_NOT_ATTESTED")
    return tun_evidence(observed_tun_processes(),require_tun_live)


def report():
    if sys.platform!="darwin" or os.geteuid()!=0:
        raise ValueError("KS_ROOT_MACOS_REQUIRED")
    item=collect()
    if item is None:
        return {"state":"not_active","reason":"KS_NO_ATTESTED_ENGINE",
                "firewall_changed":False,"leak_verified":False}
    valid=validate_kernel_syntax(item.rules())
    return {"state":"candidate_validated_not_active" if valid else "candidate_rejected",
            "protocol":item.protocol,"transport_count":len(item.transports),
            "firewall_changed":False,"leak_verified":False}


if __name__=="__main__":
    try:
        if sys.argv[1:]!=["--check"]:
            raise ValueError("KS_ACTION_INVALID")
        print(json.dumps(report()))
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        reason=str(exc)
        if not re.fullmatch(r"KS_[A-Z0-9_]{1,80}",reason):
            reason="KS_ATTESTATION_UNAVAILABLE"
        print(json.dumps({"state":"not_active","reason":reason,
                          "firewall_changed":False,"leak_verified":False}))
        raise SystemExit(2)
