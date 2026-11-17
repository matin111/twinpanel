#!/usr/bin/env python3
"""Rollback-safe local 512-flow capacity exercise; production VPNs untouched."""
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path("/opt/twintunnel-test")
RESULTS=ROOT/"results"
ECHO_SERVICE="twintunnel-lab-udp-echo.service"
CHILDREN=[]
FILES=[]

def run(args,check=True,timeout=15):
    p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if check and p.returncode:
        raise RuntimeError("command failed "+str(args)+" "+p.stderr[-300:])
    return p

def start(args,name):
    f=(RESULTS/(name+".log")).open("w",buffering=1)
    p=subprocess.Popen(args,stdout=f,stderr=subprocess.STDOUT)
    CHILDREN.append(p);FILES.append(f)
    return p

def stop_all():
    for p in reversed(CHILDREN):
        if p.poll() is None:
            p.terminate()
            try:p.wait(timeout=4)
            except subprocess.TimeoutExpired:p.kill();p.wait(timeout=3)
    for f in FILES:f.close()

def main():
    RESULTS.mkdir(parents=True,exist_ok=True,mode=0o700)
    if run(["systemctl","is-active",ECHO_SERVICE],False).stdout.strip()!="active":
        raise RuntimeError("original isolated echo must be active")
    ports=(37981,37982,38921,38922,38933)
    ss=run(["ss","-Hlun"]).stdout
    for port in ports:
        if any((":"+str(port)) in line for line in ss.splitlines()):
            raise RuntimeError("capacity test port busy: "+str(port))
    for name in ("udp_multiuser_mux.py","udp_mux_local_carrier_bridge.py","udp_mux_capacity_probe.py","udp_mux_echo_targets.py"):
        if not (ROOT/name).is_file():raise RuntimeError("missing "+name)
    print("MUX_CAPACITY_TEST_START flows=512",flush=True)
    try:
        run(["systemctl","stop",ECHO_SERVICE])
        start([sys.executable,"-u",str(ROOT/"udp_mux_echo_targets.py"),"--duration","80"],"capacity_echo")
        exit_mux=start([sys.executable,"-u",str(ROOT/"udp_multiuser_mux.py"),
             "--role","exit","--duration","75","--wg-target","37983",
             "--ovpn-target","37984","--exit-port","38922"],"capacity_exit_mux")
        bridge=start([sys.executable,"-u",str(ROOT/"udp_mux_local_carrier_bridge.py"),
             "--path1-port","38921","--path2-port","38933","--exit-port","38922",
             "--duration","75"],"capacity_local_bridge")
        entry_mux=start([sys.executable,"-u",str(ROOT/"udp_multiuser_mux.py"),
             "--role","entry","--duration","75","--bind-ip","127.0.0.1",
             "--allow-source","127.0.0.1","--path1-port","38921","--path2-port","38933"],
             "capacity_entry_mux")
        time.sleep(1)
        if any(p.poll() is not None for p in CHILDREN):
            raise RuntimeError("a local MUX capacity component exited early")
        probe=run([sys.executable,"-u",str(ROOT/"udp_mux_capacity_probe.py"),
             "--clients-per-service","256","--count","20","--interval","0.002"],
             False,timeout=70)
        print(probe.stdout[-5000:],end="",flush=True)
        if probe.stderr:print(probe.stderr[-600:],end="",flush=True)
        print("MUX_CAPACITY_PROBE_EXIT="+str(probe.returncode),flush=True)
        if probe.returncode:raise RuntimeError("512-flow capacity probe failed")
    finally:
        stop_all()
        run(["systemctl","start",ECHO_SERVICE])
        print("ORIGINAL_ECHO_RESTORED="+run(["systemctl","is-active",ECHO_SERVICE],False).stdout.strip(),flush=True)
        print("TEMP_PROCESSES_CLEAN="+str(all(p.poll() is not None for p in CHILDREN)),flush=True)
        print("PRODUCTION_OPENVPN_STATES="+",".join(run(["systemctl","is-active","openvpn-server@server.service","openvpn-server@twinpanel.service"],False).stdout.split()),flush=True)

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("MUX_CAPACITY_TEST_ERROR="+repr(exc),flush=True)
        sys.exit(3)
