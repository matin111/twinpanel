#!/usr/bin/env python3
"""OpenVPN data-channel probe with bounded-rate stress and socket-drop telemetry."""
import argparse
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TARGET = "198.18.77.1"
TUN_CLIENT = "tunTTudpc"
TUN_SERVER = "tunTTudps"
SERVER_PORT = 37984

def counter(device, metric):
    return int(Path(f"/sys/class/net/{device}/statistics/{metric}").read_text())

def udp_socket_info(port):
    result = subprocess.run(
        ["ss", "-u", "-a", "-n", "-m"],
        capture_output=True, text=True, check=False, timeout=8,
    )
    lines = result.stdout.splitlines()
    for index, line in enumerate(lines):
        if re.search(rf":{int(port)}(?:\s|$)", line):
            detail = lines[index + 1] if index + 1 < len(lines) else ""
            rcv = re.search(r"\brb(\d+)\b", detail)
            drops = re.search(r"\bd(\d+)\b", detail)
            return {
                "rcvbuf": int(rcv.group(1)) if rcv else None,
                "drops": int(drops.group(1)) if drops else None,
            }
    return {"rcvbuf": None, "drops": None}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=int(os.environ.get("TT_PROBE_COUNT", "80")))
    parser.add_argument("--interval", type=float, default=float(os.environ.get("TT_PROBE_INTERVAL", "0.20")))
    args = parser.parse_args()
    if not 1 <= args.count <= 20000:
        parser.error("count must be 1..20000")
    if not 0.002 <= args.interval <= 2.0:
        parser.error("interval must be 0.002..2.0 seconds")

    existing = subprocess.run(
        ["ip", "route", "show", f"{TARGET}/32"],
        capture_output=True, text=True, check=True,
    )
    if existing.stdout.strip():
        raise RuntimeError("ABORT: benchmark route already exists; not touching")
    before = counter(TUN_SERVER, "rx_packets")
    before_bytes = counter(TUN_SERVER, "rx_bytes")
    sock_before = udp_socket_info(SERVER_PORT)
    subprocess.run(
        ["ip", "route", "add", f"{TARGET}/32", "dev", TUN_CLIENT, "metric", "999"],
        check=True,
    )
    capture = None
    capture_file = None
    capture_path = None
    try:
        fd, name = tempfile.mkstemp(prefix="ovpn-udp-capture-", suffix=".log",
                                    dir="/opt/twintunnel-test/results")
        capture_path = Path(name)
        capture_file = open(fd, "w", buffering=1, closefd=True)
        capture = subprocess.Popen(
            ["tcpdump", "-nli", TUN_SERVER, "icmp", "and", "dst", "host", TARGET],
            stdout=capture_file, stderr=subprocess.PIPE, text=True,
        )
        time.sleep(0.6)
        if capture.poll() is not None:
            raise RuntimeError("tcpdump exited before packet probe")
        print(f"PACKET_PROBE_READY count={args.count} interval={args.interval}", flush=True)
        start = time.monotonic()
        ping = subprocess.run(
            ["ping", "-n", "-I", TUN_CLIENT, "-c", str(args.count),
             "-i", str(args.interval), "-w", str(max(30, int(args.count * args.interval + 15))),
             TARGET],
            capture_output=True, text=True,
            timeout=max(45, int(args.count * args.interval + 35)),
        )
        duration = round(time.monotonic() - start, 2)
        time.sleep(0.8)
        capture.send_signal(signal.SIGINT)
        _, caperr = capture.communicate(timeout=12)
        capture_file.close()
        capture_file = None
        capout = capture_path.read_text(errors="ignore")
        captured_seqs = [
            int(z) for z in re.findall(
                r"ICMP echo request,\s+id\s+\d+,\s+seq\s+(\d+)", capout
            )
        ]
        after = counter(TUN_SERVER, "rx_packets")
        after_bytes = counter(TUN_SERVER, "rx_bytes")
        sock_after = udp_socket_info(SERVER_PORT)
        drop_delta = None
        if sock_before["drops"] is not None and sock_after["drops"] is not None:
            drop_delta = sock_after["drops"] - sock_before["drops"]
        print(
            "PACKET_PROBE_RESULT",
            f"sent={args.count}",
            f"delivered_capture={len(captured_seqs)}",
            f"unique_seq={len(set(captured_seqs))}",
            f"missing_seqs={sorted(set(range(1, args.count + 1))-set(captured_seqs))[:40]}",
            f"server_tun_rx_packet_delta={after-before}",
            f"server_tun_rx_byte_delta={after_bytes-before_bytes}",
            f"openvpn_udp_socket_rcvbuf={sock_after['rcvbuf']}",
            f"openvpn_udp_socket_drop_delta={drop_delta}",
            f"duration_s={duration}",
            f"ping_exit={ping.returncode}",
            flush=True,
        )
        print("NOTE: ping targets a nonresponding benchmark address; 0 replies are expected", flush=True)
        if len(set(captured_seqs)) != args.count or (after - before) != args.count:
            print("ERROR: packet counts mismatch", flush=True)
            return 2
        if drop_delta not in (None, 0):
            print("ERROR: OpenVPN UDP socket dropped datagrams during probe", flush=True)
            return 3
        return 0
    finally:
        if capture is not None and capture.poll() is None:
            capture.terminate()
            try:
                capture.wait(timeout=3)
            except subprocess.TimeoutExpired:
                capture.kill()
        if capture_file is not None:
            capture_file.close()
        if capture_path is not None:
            capture_path.unlink(missing_ok=True)
        subprocess.run(
            ["ip", "route", "del", f"{TARGET}/32", "dev", TUN_CLIENT],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("PACKET_PROBE_ERROR", repr(exc), flush=True)
        sys.exit(2)
