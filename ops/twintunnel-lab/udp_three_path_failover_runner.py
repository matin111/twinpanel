#!/usr/bin/env python3
"""Bounded Iran-local continuous UDP flow with direct lab carriers disabled for 8s.
Changes ONLY the two named isolated Rakhsh lab units, auto-restored on exit.
Never changes production routing, public ports, customers or profiles.
"""
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path("/opt/twintunnel-test")
RESULTS=ROOT/"results"
DIRECT=("twintunnel-lab@entry.service","twintunnel-lab@entry-udp.service")
PROBE=ROOT/"udp_three_path_fault_probe.py"
LOG=RESULTS/"third_path_fault_continuity.log"

def cmd(*args,check=True,timeout=16):
    x=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if check and x.returncode:
        raise RuntimeError("failed command "+str(args)+" "+x.stderr[-200:])
    return x

def main():
    RESULTS.mkdir(parents=True,exist_ok=True)
    for service in DIRECT:
        if cmd("systemctl","is-active",service,check=False).stdout.strip()!="active":
            raise RuntimeError("lab carrier was not active "+service)
    if cmd("ss","-Hlunp").stdout.count(":37981")==0:
        raise RuntimeError("Iran mux test listener not running")
    for service in DIRECT:
        desc=cmd("systemctl","show",service,"-p","ExecStart","--value").stdout
        if "/etc/twintunnel-test/" not in desc:
            raise RuntimeError("refusing to stop nonlab service "+service)
    proc=None
    with LOG.open("w",buffering=1) as f:
        try:
            proc=subprocess.Popen([sys.executable,"-u",str(PROBE),"--count","480",
                                   "--interval","0.045"],stdout=f,stderr=subprocess.STDOUT)
            time.sleep(3)
            if proc.poll() is not None:
                raise RuntimeError("probe exited before failover")
            print("THIRD_PATH_FAULT_START="+str(time.time()),flush=True)
            cmd("systemctl","stop",*DIRECT,timeout=28)
            time.sleep(8)
            print("THIRD_PATH_FAULT_END="+str(time.time()),flush=True)
        finally:
            result=cmd("systemctl","start",*DIRECT,check=False,timeout=28)
            print("RESTORE_RESULT="+str(result.returncode),flush=True)
            print("RESTORED_LABS="+",".join(
                cmd("systemctl","is-active",x,check=False).stdout.strip() for x in DIRECT
            ),flush=True)
            if proc:
                try:proc.wait(timeout=45)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try:proc.wait(timeout=4)
                    except subprocess.TimeoutExpired:proc.kill()
                print("PROBE_EXIT="+str(proc.returncode),flush=True)
    print("PROBE_LOG="+LOG.read_text(errors="ignore")[-2500:],flush=True)
    return proc.returncode if proc else 3

if __name__=="__main__":
    try:sys.exit(main())
    except Exception as exc:
        print("THIRD_PATH_FAULT_ERROR="+repr(exc),flush=True)
        sys.exit(3)
