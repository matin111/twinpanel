#!/usr/bin/env python3
"""Bounded/rollback-safe six-user UDP echo lab benchmark, France side.
Use with a time-bounded Iran ingress mux. Not for customer traffic.
"""
from pathlib import Path
import json
import subprocess
import sys
import time

ROOT=Path("/opt/twintunnel-test")
SERVICE="twintunnel-lab-udp-echo.service"
CHILDREN=[]
FILES=[]
def cmd(args,check=True):
    p=subprocess.run(args,capture_output=True,text=True,timeout=14)
    if check and p.returncode:
        raise RuntimeError("command failed: "+str(args)+" code="+str(p.returncode)+" err="+p.stderr[:120])
    return p
def start(args,name):
    f=(ROOT/"results"/(name+".log")).open("w")
    proc=subprocess.Popen(args,stdout=f,stderr=subprocess.STDOUT)
    CHILDREN.append(proc)
    FILES.append(f)
    return proc
def stop_all():
    for p in reversed(CHILDREN):
        if p.poll() is None:
            p.terminate()
            try:p.wait(timeout=4)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait(timeout=3)
    for f in FILES:
        f.close()
def main():
    folder=ROOT/"results"
    folder.mkdir(mode=0o700,parents=True,exist_ok=True)
    if cmd(["systemctl","is-active",SERVICE],False).stdout.strip()!="active":
        raise RuntimeError("original lab echo is not active; refusing to replace")
    for port in (37983,37984):
        if ":"+str(port) in cmd(["ss","-Hlunp"]).stdout:
            raise RuntimeError("lab target port already used; abort")
    result=[]
    print("ECHO_BENCH_START",flush=True)
    try:
        cmd(["systemctl","stop",SERVICE])
        echo=start([sys.executable,"-u",str(ROOT/"udp_mux_echo_targets.py"),"--duration","85"],"multiuser_echo_bench")
        mux=start([sys.executable,"-u",str(ROOT/"udp_multiuser_mux.py"),
                   "--role","exit","--wg-target","37983","--ovpn-target","37984",
                   "--duration","85"],"multiuser_exit_bench")
        time.sleep(1.2)
        if echo.poll() is not None or mux.poll() is not None:
            raise RuntimeError("one of the isolated echo/mux processes exited early")
        for trial in range(1,4):
            probe=cmd([sys.executable,"-u",str(ROOT/"udp_mux_multi_client_probe.py"),
                      "--clients-per-service","3","--count","40","--interval","0.03"],False)
            line=next((x for x in probe.stdout.splitlines() if x.startswith("MULTIUSER_TEST_RESULT ")),None)
            if not line:
                raise RuntimeError("missing probe output: "+probe.stderr[:250])
            data=json.loads(line.partition(" ")[2])
            data["trial"]=trial
            data["exit_code"]=probe.returncode
            result.append(data)
            print("TRIAL_RESULT",json.dumps({"trial":trial,"sent":data["sent"],
                  "received":data["received"],"missing":data["sent"]-data["received"],
                  "exit_code":probe.returncode}),flush=True)
            if echo.poll() is not None or mux.poll() is not None:
                raise RuntimeError("lab echo/mux died mid-test")
        print("ECHO_BENCH_SUMMARY",json.dumps({"runs":len(result),
              "sent":sum(a["sent"] for a in result),
              "received":sum(a["received"] for a in result),
              "missing":sum(a["sent"]-a["received"] for a in result),
              "miss_pct":round(100*sum(a["sent"]-a["received"] for a in result)/sum(a["sent"] for a in result),2),
              "per_run":[{"trial":x["trial"],"received":x["received"]} for x in result]}),flush=True)
        (folder/"udp_mux_batched_repeated_trials.json").write_text(json.dumps(result,indent=2)+"\n")
    finally:
        stop_all()
        cmd(["systemctl","start",SERVICE])
        print("ORIGINAL_LAB_ECHO_RESTORED="+cmd(["systemctl","is-active",SERVICE],False).stdout.strip(),flush=True)
        print("PRODUCTION_OPENVPN_UNTOUCHED="+",".join(cmd(["systemctl","is-active","openvpn-server@server.service","openvpn-server@twinpanel.service"],False).stdout.split()),flush=True)
        print("TEMP_PROCESSES_CLEANED="+str(all(p.poll() is not None for p in CHILDREN)),flush=True)
if __name__=="__main__":
    try:main()
    except Exception as error:
        print("BENCH_ERROR",type(error).__name__,str(error)[:200],flush=True)
        raise