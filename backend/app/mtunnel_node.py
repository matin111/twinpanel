#!/usr/bin/env python3
# TWINPANEL_MTUNNEL_NODE_V1

import base64
import fcntl
import json
import os
import select
import signal
import socket
import struct
import subprocess
import sys
import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


TUNSETIFF = 0x400454CA
IFF_TUN = 0x0001
IFF_NO_PI = 0x1000


def run(*args):
    subprocess.run(
        args,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def open_tun(name: str):
    fd = os.open(
        "/dev/net/tun",
        os.O_RDWR,
    )

    ifr = struct.pack(
        "16sH",
        name.encode(),
        IFF_TUN | IFF_NO_PI,
    )

    fcntl.ioctl(
        fd,
        TUNSETIFF,
        ifr,
    )

    return fd


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "usage: mtunnel_node.py CONFIG"
        )

    with open(
        sys.argv[1],
        "r",
        encoding="utf-8",
    ) as f:
        cfg = json.load(f)

    iface = cfg["interface"]
    addr = cfg["address"]
    role = cfg["role"]
    port = int(cfg["port"])
    mtu = int(cfg.get("mtu", 1280))

    key = base64.b64decode(
        cfg["key"]
    )

    if len(key) != 32:
        raise RuntimeError(
            "MTunnel AES key must be 32 bytes"
        )

    aes = AESGCM(key)

    tun = open_tun(iface)

    run(
        "ip",
        "addr",
        "replace",
        addr,
        "dev",
        iface,
    )

    run(
        "ip",
        "link",
        "set",
        "dev",
        iface,
        "mtu",
        str(mtu),
        "up",
    )

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
    )

    sock.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_RCVBUF,
        4 * 1024 * 1024,
    )

    sock.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_SNDBUF,
        4 * 1024 * 1024,
    )

    peer = None

    if role == "server":
        sock.bind(
            ("0.0.0.0", port)
        )
    else:
        peer = (
            cfg["peer_ip"],
            port,
        )

        # TWINPANEL_MTUNNEL_CLIENT_NO_LISTEN_V1
        #
        # Client side must not listen on the remote port.
        # Kernel chooses the UDP source port automatically.
        #
        # This prevents:
        # client :39051 -> server :39051
        # binding collision and broken session tracking.

        source_port = cfg.get(
            "source_port"
        )

        if source_port:
            sock.bind(
                (
                    "0.0.0.0",
                    int(source_port),
                )
            )

    aad = (
        f"twinpanel-mtunnel:"
        f"{cfg['tunnel_id']}"
    ).encode()

    running = True

    def stop_handler(*_):
        nonlocal running
        running = False

    signal.signal(
        signal.SIGTERM,
        stop_handler,
    )

    signal.signal(
        signal.SIGINT,
        stop_handler,
    )

    def encrypt(
        packet_type: int,
        payload: bytes = b"",
    ):
        nonce = os.urandom(12)

        plaintext = (
            bytes([packet_type])
            + payload
        )

        return (
            nonce
            + aes.encrypt(
                nonce,
                plaintext,
                aad,
            )
        )

    def decrypt(data: bytes):
        if len(data) < 29:
            return None

        nonce = data[:12]

        try:
            return aes.decrypt(
                nonce,
                data[12:],
                aad,
            )
        except Exception:
            return None

    last_keepalive = 0.0

    while running:
        now = time.monotonic()

        if (
            role == "client"
            and peer
            and now - last_keepalive >= 5
        ):
            try:
                sock.sendto(
                    encrypt(0),
                    peer,
                )
            except OSError:
                pass

            last_keepalive = now

        readable, _, _ = select.select(
            [tun, sock],
            [],
            [],
            1.0,
        )

        for item in readable:

            if item == tun:
                packet = os.read(
                    tun,
                    65535,
                )

                if peer:
                    try:
                        sock.sendto(
                            encrypt(
                                1,
                                packet,
                            ),
                            peer,
                        )
                    except OSError:
                        pass

            else:
                data, source = sock.recvfrom(
                    65535
                )

                plain = decrypt(data)

                if not plain:
                    continue

                if role == "server":
                    peer = source

                packet_type = plain[0]

                if packet_type == 1:
                    os.write(
                        tun,
                        plain[1:],
                    )

    sock.close()
    os.close(tun)


if __name__ == "__main__":
    main()
