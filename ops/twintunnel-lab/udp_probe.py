#!/usr/bin/env python3
"""TwinTunnel isolated UDP loopback-forward probe (no production VPN traffic)."""
import argparse
import json
import socket
import statistics
import struct
import threading
import time

MAGIC = b"TTLB1"
HEADER = len(MAGIC) + 4 + 8


def packet(seq: int, size: int) -> bytes:
    return MAGIC + struct.pack("!IQ", seq, time.monotonic_ns()) + b"T" * (size - HEADER)


def percentile(seq, pct):
    if not seq:
        return None
    values = sorted(seq)
    return round(values[min(len(values) - 1, int((len(values) - 1) * pct))], 2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=37921)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--size", type=int, default=256)
    parser.add_argument("--timeout", type=float, default=1.5)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--rate-mbps", type=float, default=0.0)
    parser.add_argument("--seconds", type=float, default=4.0)
    args = parser.parse_args()
    if args.host != "127.0.0.1":
        parser.error("This isolated test can only send to 127.0.0.1")
    if not (HEADER <= args.size <= 1200):
        parser.error("packet size must be between 17 and 1200 bytes")
    if not (1 <= args.count <= 1000 and 0.2 <= args.timeout <= 5):
        parser.error("invalid count/timeout")
    if args.rate_mbps and not (0.1 <= args.rate_mbps <= 20 and 1 <= args.seconds <= 10):
        parser.error("burst rate must be 0.1-20 Mbit/s over 1-10 s")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    addr = (args.host, args.port)
    losses, rtts = 0, []
    started = time.monotonic()
    if args.rate_mbps:
        recv = set()
        stop = threading.Event()
        sock.settimeout(0.1)

        def receiver():
            while not stop.is_set():
                try:
                    data, _src = sock.recvfrom(1500)
                except socket.timeout:
                    continue
                if data.startswith(MAGIC) and len(data) == args.size:
                    seq, tick = struct.unpack("!IQ", data[len(MAGIC):HEADER])
                    recv.add(seq)
                    rtts.append((time.monotonic_ns() - tick) / 1e6)

        worker = threading.Thread(target=receiver, daemon=True)
        worker.start()
        total = int(args.rate_mbps * 1_000_000 * args.seconds / (args.size * 8))
        gap = args.seconds / max(1, total)
        for i in range(total):
            wait = started + (i * gap) - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            sock.sendto(packet(i, args.size), addr)
        elapsed = time.monotonic() - started
        time.sleep(min(2, args.timeout))
        stop.set()
        worker.join(timeout=1)
        received = len(recv)
        sent = total
        effective_mbps = round(received * args.size * 8 / max(elapsed, 1e-6) / 1e6, 3)
    else:
        sock.settimeout(args.timeout)
        for i in range(args.count):
            payload = packet(i, args.size)
            sent_at = time.monotonic_ns()
            sock.sendto(payload, addr)
            try:
                data, _src = sock.recvfrom(1500)
                if data == payload:
                    rtts.append((time.monotonic_ns() - sent_at) / 1e6)
                else:
                    losses += 1
            except socket.timeout:
                losses += 1
            if args.interval > 0:
                time.sleep(args.interval)
        sent = args.count
        received = len(rtts)
        elapsed = time.monotonic() - started
        effective_mbps = None

    result = {
        "brand": "TwinTunnel", "carrier": "Shabdiz-GRE",
        "sent": sent, "received": received,
        "loss_pct": round(100 * (sent - received) / max(sent, 1), 2),
        "rtt_avg_ms": round(statistics.mean(rtts), 2) if rtts else None,
        "rtt_p95_ms": percentile(rtts, 0.95),
        "elapsed_s": round(elapsed, 2),
        "echoed_mbps_at_test_rate": effective_mbps,
    }
    print(json.dumps(result, ensure_ascii=False))
    sock.close()
    if received == 0:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
