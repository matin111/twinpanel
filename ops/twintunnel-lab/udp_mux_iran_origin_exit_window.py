#!/usr/bin/env python3
"""Isolated France-side UDP echo/exit window for an Iran-local-origin probe."""
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path("/opt/twintunnel-test")
RESULTS=ROOT/"results"
UNIT="twintunnel-lab-udp-echo.service"
CHILDREN=[]

def run(args,check=True):
    p=subprocess.run(args,capture_output=True,text=True,timeout=15)
    if check and p.returncode:
        raise RuntimeError("command_failed "+str(args[0])+" rc="+str(p.returncode)+" "+p.stderr[-200:])
    return p

def start(args,name):
    logfile=(RESULTS/(name+".log")).open("w",buffering=1)
    child=subprocess.Popen(args,stdout=logfile,stderr=subprocess.STDOUT)
    CHILDREN.append((child,logfile))
    return child

def main():
    if run(["systemctl","is-active",UNIT],False).stdout.strip()!="active":
        raise RuntimeError("original lab echo inactive")
    for port in (37983,37984):
        if (":"+str(port)+" ") in run(["ss","-Hlunp"]).stdout:
            raise RuntimeError("test port occupied "+str(port))
    print("IRAN_ORIGIN_EXIT_WINDOW_START",flush=True)
    try:
        run(["systemctl","stop",UNIT])
        echo=start([sys.executable,"-u",str(ROOT/"udp_mux_echo_targets.py"),
                    "--duration","80"],"iran_origin_echo")
        mux=start([sys.executable,"-u",str(ROOT/"udp_multiuser_mux.py"),
                   "--role","exit","--wg-target","37983","--ovpn-target","37984",
                   "--duration","80"],"iran_origin_exit")
        time.sleep(1.5)
        if any(p.poll() is not None for p,f in CHILDREN):
            raise RuntimeError("lab targets/mux failed to start")
        print("IRAN_ORIGIN_EXIT_WINDOW_READY",flush=True)
        for _ in range(70):
            if any(p.poll() is not None for p,f in CHILDREN):
                raise RuntimeError("lab child exited early")
            time.sleep(1)
    finally:
        for p,f in reversed(CHILDREN):
            if p.poll() is None:
                p.terminate()
                try:p.wait(timeout=4)
                except subprocess.TimeoutExpired:p.kill();p.wait(timeout=3)
            f.close()
        restore=run(["systemctl","start",UNIT],False)
        print("ORIGINAL_ECHO_RESTORED="+run(["systemctl","is-active",UNIT],False).stdout.strip(),flush=True)
        print("RESTORE_RC="+str(restore.returncode),flush=True)
        print("PRODUCTION_OPENVPN="+",".join(run(
            ["systemctl","is-active","openvpn-server@server.service","openvpn-server@twinpanel.service"],
            False).stdout.split()),flush=True)

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("IRAN_ORIGIN_WINDOW_ERROR="+repr(exc),flush=True)
        sys.exit(3)
