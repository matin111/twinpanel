#!/usr/bin/env python3
"""Local-only France lab echo runner for Iran-origin multi-user UDP tests.

Stops only the existing isolated lab UDP echo; restores it in finally.
No customer VPN configs, no production routes or accounts are modified.
"""
from pathlib import Path
import subprocess
import signal
import sys
import time

ROOT=Path("/opt/twintunnel-test")
SERVICE="twintunnel-lab-udp-echo.service"
stop_requested=False
def handler(*_):
    global stop_requested
    stop_requested=True
signal.signal(signal.SIGTERM,handler)
signal.signal(signal.SIGINT,handler)

def run(args,check=True):
    p=subprocess.run(args,text=True,capture_output=True,timeout=15)
    if check and p.returncode:
        raise RuntimeError("command failed: "+str(args)+" "+p.stderr[:200])
    return p

def main():
    logs=ROOT/"results"
    logs.mkdir(parents=True,exist_ok=True,mode=0o700)
    if run(["systemctl","is-active",SERVICE],False).stdout.strip()!="active":
        raise RuntimeError("original lab echo is not active")
    for port in (37983,37984):
        if ":"+str(port) in run(["ss","-Hlun"]).stdout:
            raise RuntimeError("test target port busy")
    own=[]
    files=[]
    print("IRAN_CLIENT_BENCH_FRANCE_READYING",flush=True)
    try:
        run(["systemctl","stop",SERVICE])
        def spawn(command,name):
            f=(logs/(name+".log")).open("w")
            p=subprocess.Popen(command,stdout=f,stderr=subprocess.STDOUT)
            own.append(p)
            files.append(f)
        spawn([sys.executable,"-u",str(ROOT/"udp_mux_echo_targets.py"),"--duration","70"],"iran_origin_echo")
        spawn([sys.executable,"-u",str(ROOT/"udp_multiuser_mux.py"),"--role","exit",
              "--wg-target","37983","--ovpn-target","37984",
              "--duration","70"],"iran_origin_mux")
        time.sleep(1)
        if any(p.poll() is not None for p in own):
            raise RuntimeError("temporary echo/mux exited immediately")
        print("IRAN_CLIENT_BENCH_FRANCE_READY",flush=True)
        until=time.monotonic()+55
        while time.monotonic()<until and not stop_requested:
            time.sleep(.2)
    finally:
        for p in reversed(own):
            if p.poll() is None:
                p.terminate()
                try:p.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    p.kill();p.wait(timeout=3)
        for f in files:f.close()
        run(["systemctl","start",SERVICE])
        print("ORIGINAL_UDP_ECHO_RESTORED="+run(["systemctl","is-active",SERVICE],False).stdout.strip(),flush=True)
        print("MAIN_OPENVPN_STATES="+",".join(run(["systemctl","is-active","openvpn-server@server.service","openvpn-server@twinpanel.service"],False).stdout.split()),flush=True)
        print("TEMP_TEST_PROCESSES_CLEAN="+str(all(p.poll() is not None for p in own)),flush=True)
if __name__=="__main__":
    main()