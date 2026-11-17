#!/usr/bin/env python3
"""Loopback-only UDP echo used to measure TwinTunnel, never customer traffic."""
import argparse
import socket
import signal


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=37922)
    args = p.parse_args()
    if args.host not in {"127.0.0.1", "::1"}:
        p.error("Public listening is intentionally prohibited in the lab")
    family = socket.AF_INET6 if args.host == "::1" else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_DGRAM)
    sock.bind((args.host, args.port))
    sock.settimeout(1.0)
    alive = True

    def shutdown(_signal, _frame):
        nonlocal alive
        alive = False

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    print(f"TWINTUNNEL_UDP_ECHO_READY {args.host}:{args.port}", flush=True)
    try:
        while alive:
            try:
                data, addr = sock.recvfrom(1500)
            except socket.timeout:
                continue
            if data.startswith(b"TTLB1") and 17 <= len(data) <= 1400:
                sock.sendto(data, addr)
    finally:
        sock.close()


if __name__ == "__main__":
    main()
