#!/usr/bin/env python3
"""Bounded France-side OpenVPN UDP-through-Rakhsh lab with guaranteed cleanup.

Requires the separate Iran multi-user ingress lab to already be active.
Runs only dedicated test configs, routes and processes; no customer changes.
"""
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path("/opt/twintunnel-test")
R=ROOT/"results"
ECHO="twintunnel-lab-udp-echo.service"
CLIENT_CFG="/etc/twintunnel-ovpn-test/hairpin-client-udp.conf"
SERVER_CFG="/etc/twintunnel-ovpn-test/server-udp.conf"
MISSING_ROUTE="198.18.77.1/32"

def run(args,check=True):
    p=subprocess.run(args,capture_output=True,text=True,timeout=12)
    if check and p.returncode:
        raise RuntimeError("failed command "+args[0]+" "+str(p.returncode)+" "+p.stderr[:120])
    return p

def pspawn(cmd,name):
    file=open(R/(name+".log"),"w",buffering=1)
    p=subprocess.Popen(cmd,stdout=file,stderr=subprocess.STDOUT)
    return p,file

def active_iface(iface):
    return Path("/sys/class/net",iface).exists()

def clean_process(p):
    if p.poll() is None:
        p.terminate()
        try:p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait(timeout=4)

def main():
    R.mkdir(parents=True,exist_ok=True,mode=0o700)
    if run(["systemctl","is-active",ECHO],False).stdout.strip()!="active":
        raise RuntimeError("original isolated UDP echo not active: abort")
    if run(["ip","route","show",MISSING_ROUTE]).stdout.strip():
        raise RuntimeError("test route unexpectedly preexists")
    if active_iface("tunTTudpc") or active_iface("tunTTudps"):
        raise RuntimeError("preexisting test interface, abort")
    own=[]
    print("UDP_OPENVPN_ORCHESTRATOR_START",flush=True)
    try:
        run(["systemctl","stop",ECHO])
        p,f=pspawn([sys.executable,"-u",str(ROOT/"udp_multiuser_mux.py"),"--role","exit","--wg-target","37983","--ovpn-target","37984","--duration","115"],"mux_exit_orchestrated")
        own.append((p,f))
        p,f=pspawn(["/usr/sbin/openvpn","--config",SERVER_CFG],"ovpn_udp_server_orchestrated")
        own.append((p,f))
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            if active_iface("tunTTudps"):break
            if p.poll() is not None:raise RuntimeError("lab server exited early")
            time.sleep(.2)
        else:raise RuntimeError("test server did not create TUN")
        p,f=pspawn(["/usr/sbin/openvpn","--config",CLIENT_CFG],"ovpn_udp_client_orchestrated")
        own.append((p,f))
        deadline=time.monotonic()+25
        logfile=R/"ovpn_udp_client_orchestrated.log"
        while time.monotonic()<deadline:
            if p.poll() is not None:raise RuntimeError("test OpenVPN client exited")
            if active_iface("tunTTudpc") and "Initialization Sequence Completed" in logfile.read_text(errors="ignore"):
                break
            time.sleep(.3)
        else:raise RuntimeError("OpenVPN client TLS handshake not completed")
        print("UDP_OPENVPN_TUNNEL_READY",flush=True)
        print("UDP_OPENVPN_PROBE_START",flush=True)
        probe=subprocess.run(
            [sys.executable,"-u",str(ROOT/"openvpn_udp_mux_data_probe.py")],
            capture_output=True,text=True,timeout=65,
        )
        print(probe.stdout[-3500:],end="",flush=True)
        print(probe.stderr[-700:],end="",flush=True)
        current=logfile.read_text(errors="ignore")
        print("OPENVPN_UDP_INITIALIZATIONS="+str(current.count("Initialization Sequence Completed")),flush=True)
        print("OPENVPN_UDP_INACTIVITY_RESTARTS="+str(current.count("Inactivity timeout")),flush=True)
        print("OPENVPN_UDP_TEST_RETURN_CODE="+str(probe.returncode),flush=True)
        return 0 if probe.returncode==0 and current.count("Initialization Sequence Completed")==1 and current.count("Inactivity timeout")==0 else 2
    finally:
        for p,f in reversed(own):
            clean_process(p)
            f.close()
        run(["ip","route","del",MISSING_ROUTE,"dev","tunTTudpc"],False)
        run(["systemctl","start",ECHO])
        print("ORIGINAL_UDP_ECHO_RESTORED="+run(["systemctl","is-active",ECHO],False).stdout.strip(),flush=True)
        print("PRODUCTION_OPENVPN_STATES="+",".join(run(["systemctl","is-active","openvpn-server@server.service","openvpn-server@twinpanel.service"],False).stdout.split()),flush=True)
        print("TEST_TUNS_GONE="+str(not active_iface("tunTTudpc") and not active_iface("tunTTudps")),flush=True)
        print("ORCHESTRATOR_CLEANUP_DONE",flush=True)

if __name__=="__main__":
    try:sys.exit(main())
    except Exception as exc:
        print("UDP_OPENVPN_ORCHESTRATOR_ERROR="+repr(exc),flush=True)
        sys.exit(3)