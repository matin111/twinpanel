#!/usr/bin/env python3
"""Local-only OpenVPN UDP socket-buffer stress test with rollback-safe cleanup."""
from pathlib import Path
import os
import re
import signal
import subprocess
import sys
import tempfile
import time

ROOT=Path("/opt/twintunnel-test")
RESULTS=ROOT/"results"
SERVICE="twintunnel-lab-udp-echo.service"
SERVER_CFG=Path("/etc/twintunnel-ovpn-test/server-udp.conf")
CLIENT_CFG=Path("/etc/twintunnel-ovpn-test/hairpin-client-udp.conf")
CLIENT_IF="tunTTudpc"
SERVER_IF="tunTTudps"
TARGET="198.18.77.1/32"
PROBE=ROOT/"openvpn_udp_mux_data_probe.py"
OWN=[]

def run(args,check=True,timeout=15):
    p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if check and p.returncode:
        raise RuntimeError("command failed "+str(args)+" "+p.stderr[-300:])
    return p

def start(args,name):
    log=(RESULTS/(name+".log")).open("w",buffering=1)
    p=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT)
    OWN.append((p,log))
    return p,log

def clean(p,log):
    if p.poll() is None:
        p.terminate()
        try:p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill();p.wait(timeout=3)
    log.close()

def main():
    RESULTS.mkdir(parents=True,exist_ok=True,mode=0o700)
    if run(["systemctl","is-active",SERVICE],False).stdout.strip()!="active":
        raise RuntimeError("original lab echo not active; refusing to continue")
    if not SERVER_CFG.is_file() or not CLIENT_CFG.is_file() or not PROBE.is_file():
        raise RuntimeError("dedicated lab config/probe missing")
    if Path("/sys/class/net",CLIENT_IF).exists() or Path("/sys/class/net",SERVER_IF).exists():
        raise RuntimeError("test TUN already exists; abort")
    if run(["ip","route","show",TARGET]).stdout.strip():
        raise RuntimeError("test route already exists; abort")
    original=CLIENT_CFG.read_text()
    local,replaced=re.subn(r"(?m)^remote\s+\S+\s+\d+\s*$",
                           "remote 127.0.0.1 37984",original,count=1)
    if replaced!=1:
        raise RuntimeError("expected one remote endpoint in dedicated client config")
    fd,name=tempfile.mkstemp(prefix="ovpn-local-client-",suffix=".conf",dir=RESULTS)
    local_cfg=Path(name)
    with os.fdopen(fd,"w") as f:
        f.write(local)
    os.chmod(local_cfg,0o600)
    print("LOCAL_OPENVPN_BUFFER_TEST_START",flush=True)
    try:
        run(["systemctl","stop",SERVICE])
        server,server_log=start(["/usr/sbin/openvpn","--config",str(SERVER_CFG)],"local_ovpn_udp_server")
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            if Path("/sys/class/net",SERVER_IF).exists():break
            if server.poll() is not None:raise RuntimeError("lab OpenVPN server exited")
            time.sleep(.2)
        else:raise RuntimeError("lab server TUN did not appear")
        client,client_log=start(["/usr/sbin/openvpn","--config",str(local_cfg)],"local_ovpn_udp_client")
        deadline=time.monotonic()+18
        log_path=RESULTS/"local_ovpn_udp_client.log"
        while time.monotonic()<deadline:
            if client.poll() is not None:raise RuntimeError("lab OpenVPN client exited")
            if Path("/sys/class/net",CLIENT_IF).exists() and "Initialization Sequence Completed" in log_path.read_text(errors="ignore"):
                break
            time.sleep(.2)
        else:raise RuntimeError("local OpenVPN handshake did not complete")
        print("LOCAL_OPENVPN_TUNNEL_READY",flush=True)
        count=os.environ.get("TT_PROBE_COUNT","5000")
        interval=os.environ.get("TT_PROBE_INTERVAL","0.002")
        probe=run([sys.executable,"-u",str(PROBE),"--count",count,"--interval",interval],False,timeout=110)
        print(probe.stdout[-5000:],end="",flush=True)
        if probe.stderr:print(probe.stderr[-800:],end="",flush=True)
        print("LOCAL_OPENVPN_PROBE_EXIT="+str(probe.returncode),flush=True)
        return probe.returncode
    finally:
        for p,log in reversed(OWN):clean(p,log)
        run(["ip","route","del",TARGET,"dev",CLIENT_IF],False)
        local_cfg.unlink(missing_ok=True)
        run(["systemctl","start",SERVICE])
        print("ORIGINAL_LAB_ECHO_RESTORED="+run(["systemctl","is-active",SERVICE],False).stdout.strip(),flush=True)
        print("TEST_TUNS_GONE="+str(not Path("/sys/class/net",CLIENT_IF).exists() and not Path("/sys/class/net",SERVER_IF).exists()),flush=True)
        print("PRODUCTION_OPENVPN_STATES="+",".join(run(["systemctl","is-active","openvpn-server@server.service","openvpn-server@twinpanel.service"],False).stdout.split()),flush=True)

if __name__=="__main__":
    try:sys.exit(main())
    except Exception as exc:
        print("LOCAL_OPENVPN_TEST_ERROR="+repr(exc),flush=True)
        sys.exit(3)
