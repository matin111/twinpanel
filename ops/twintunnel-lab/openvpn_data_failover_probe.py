#!/usr/bin/env python3
"""France-only OpenVPN data-channel probe through Iran/Rakhsh and back.
Receives on server TUN; no echo replies are expected from the benchmark target.
Adds and removes one 198.18.254.254/32 route for the lifetime of this test.
"""
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

TARGET = "198.18.254.254"
TUN_CLIENT = "tunTTcl"
TUN_SERVER = "tunTTsv"
COUNT = 80

def counter(device, metric):
    return int(Path(f"/sys/class/net/{device}/statistics/{metric}").read_text())

def main():
    existing = subprocess.run(["ip","route","show",f"{TARGET}/32"],capture_output=True,text=True,check=True)
    if existing.stdout.strip():
        raise RuntimeError("ABORT: benchmark route already exists; not touching")
    before = counter(TUN_SERVER,"rx_packets")
    before_bytes = counter(TUN_SERVER,"rx_bytes")
    subprocess.run(["ip","route","add",f"{TARGET}/32","dev",TUN_CLIENT,"metric","999"],check=True)
    capture = None
    try:
        capture = subprocess.Popen(
            ["tcpdump","-nli",TUN_SERVER,"icmp","and","dst","host",TARGET],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
        )
        time.sleep(0.6)
        print("PACKET_PROBE_READY count="+str(COUNT),flush=True)
        start = time.monotonic()
        ping = subprocess.run(
            ["ping","-n","-I",TUN_CLIENT,"-c",str(COUNT),"-i","0.20","-W","1",TARGET],
            capture_output=True,text=True,timeout=45,
        )
        duration = round(time.monotonic()-start,2)
        time.sleep(1.0)
        capture.send_signal(signal.SIGINT)
        capout,caperr = capture.communicate(timeout=10)
        captured_seqs = [int(z) for z in re.findall(r"ICMP echo request,\s+id\s+\d+,\s+seq\s+(\d+)",capout)]
        after = counter(TUN_SERVER,"rx_packets")
        after_bytes = counter(TUN_SERVER,"rx_bytes")
        print("PACKET_PROBE_RESULT",
              f"sent={COUNT} delivered_capture={len(captured_seqs)}",
              f"unique_seq={len(set(captured_seqs))}",
              f"missing_seqs={sorted(set(range(1,COUNT+1))-set(captured_seqs))}",
              f"server_tun_rx_packet_delta={after-before}",
              f"server_tun_rx_byte_delta={after_bytes-before_bytes}",
              f"duration_s={duration}",
              f"ping_exit={ping.returncode}",
              flush=True)
        print("NOTE: ping targets a nonresponding benchmark address; 0 replies is expected",flush=True)
        if len(set(captured_seqs)) != COUNT or (after-before) != COUNT:
            print("ERROR: packet counts mismatch",flush=True)
            return 2
        return 0
    finally:
        if capture is not None and capture.poll() is None:
            capture.terminate()
            try:capture.wait(timeout=3)
            except subprocess.TimeoutExpired:capture.kill()
        subprocess.run(["ip","route","del",f"{TARGET}/32","dev",TUN_CLIENT],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

if __name__ == "__main__":
    try:sys.exit(main())
    except Exception as exc:
        print("PACKET_PROBE_ERROR",repr(exc),flush=True)
        sys.exit(2)