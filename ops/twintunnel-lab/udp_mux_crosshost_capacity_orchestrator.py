#!/usr/bin/env python3
"""Bounded Iran/France Rakhsh dual-carrier concurrency test; lab-only.

Requires the isolated Iran UDP mux and two Rakhsh Shabdiz test carriers active.
Only temporarily replaces the France UDP lab echo on 127.0.0.1:37922.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT=Path("/opt/twintunnel-test")
RESULTS=ROOT/"results"
SERVICE="twintunnel-lab-udp-echo.service"
OWNED=[]

def cmd(args,check=True,timeout=35):
    p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if check and p.returncode:
        raise RuntimeError("failed: "+str(args)+" return="+str(p.returncode)+" stderr="+p.stderr[-200:])
    return p

def start(args,label):
    logfile=(RESULTS/(label+".log")).open("w",buffering=1)
    proc=subprocess.Popen(args,stdout=logfile,stderr=subprocess.STDOUT)
    OWNED.append((proc,logfile))
    return proc

def clean():
    for p,f in reversed(OWNED):
        if p.poll() is None:
            p.terminate()
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill();p.wait(timeout=3)
        f.close()

def main():
    RESULTS.mkdir(exist_ok=True,parents=True,mode=0o700)
    if cmd(["systemctl","is-active",SERVICE],False).stdout.strip()!="active":
        raise RuntimeError("isolated echo service not active; refuse to change")
    ss=cmd(["ss","-Hlunp"]).stdout.splitlines()
    for port in (37983,37984):
        if any((":"+str(port)+" ") in line for line in ss):
            raise RuntimeError("test target port already occupied "+str(port))
    for unit in ("twintunnel-lab@exit.service","twintunnel-lab@exit-udp.service",
                 "openvpn-server@twinpanel.service","openvpn-server@server.service"):
        if cmd(["systemctl","is-active",unit],False).stdout.strip()!="active":
            raise RuntimeError("required unit inactive "+unit)
    print("CROSSHOST_CAPACITY_START paths=Rakhsh-GRE+Shabdiz-UDP",flush=True)
    results=[]
    try:
        cmd(["systemctl","stop",SERVICE])
        echo=start([sys.executable,"-u",str(ROOT/"udp_mux_echo_targets.py"),
                    "--duration","140"],"crosshost_capacity_echo")
        exit_mux=start([sys.executable,"-u",str(ROOT/"udp_multiuser_mux.py"),
                        "--role","exit","--wg-target","37983","--ovpn-target","37984",
                        "--duration","140"],"crosshost_capacity_exit")
        time.sleep(1.3)
        if any(p.poll() is not None for p,f in OWNED):
            raise RuntimeError("isolated echo/mux failed to start")
        for clients_each in (8,16,32):
            result=cmd([sys.executable,"-u",str(ROOT/"udp_mux_multi_client_probe.py"),
                        "--clients-per-service",str(clients_each),
                        "--count","36","--interval","0.02"],
                       check=False,timeout=60)
            encoded=next((line.partition(" ")[2] for line in result.stdout.splitlines()
                          if line.startswith("MULTIUSER_TEST_RESULT ")),None)
            if encoded is None:
                raise RuntimeError("probe returned no JSON "+result.stderr[-200:])
            metrics=json.loads(encoded)
            metrics["clients_each"]=clients_each
            metrics["exit_code"]=result.returncode
            results.append(metrics)
            print("CROSSHOST_CAPACITY_STAGE "+
                  json.dumps({"clients":metrics["clients"],"sent":metrics["sent"],
                              "received":metrics["received"],
                              "missing":metrics["sent"]-metrics["received"],
                              "exit_code":metrics["exit_code"]},separators=(",",":")),flush=True)
            if any(p.poll() is not None for p,f in OWNED):
                raise RuntimeError("isolated mux/echo stopped early")
        all_sent=sum(r["sent"] for r in results)
        all_received=sum(r["received"] for r in results)
        summary={"test":"isolated real Iran-France Rakhsh underlays, not customer VPN",
                 "clients_peak":max(r["clients"] for r in results),
                 "sent":all_sent,"received":all_received,
                 "loss_percent":round((all_sent-all_received)/all_sent*100,2),
                 "stages":[{"clients":r["clients"],"sent":r["sent"],
                            "received":r["received"],"exit_code":r["exit_code"]} for r in results]}
        (RESULTS/"udp_mux_crosshost_capacity_20261117.json").write_text(
            json.dumps(summary,indent=2)+"\n")
        print("CROSSHOST_CAPACITY_SUMMARY "+json.dumps(summary,separators=(",",":")),flush=True)
        return 0 if all(r["exit_code"]==0 for r in results) else 2
    finally:
        clean()
        restore=cmd(["systemctl","start",SERVICE],False)
        print("ECHO_RESTORE_RC="+str(restore.returncode),flush=True)
        print("ECHO_STATE="+cmd(["systemctl","is-active",SERVICE],False).stdout.strip(),flush=True)
        print("VPN_UNITS="+",".join(cmd(["systemctl","is-active",
              "openvpn-server@server.service","openvpn-server@twinpanel.service"],False).stdout.split()),flush=True)
        print("TEST_PROCESSES_CLEAN="+str(all(p.poll() is not None for p,f in OWNED)),flush=True)

if __name__=="__main__":
    try:sys.exit(main())
    except Exception as exc:
        print("CROSSHOST_CAPACITY_ERROR="+repr(exc),flush=True)
        sys.exit(3)
