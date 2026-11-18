#!/usr/bin/env python3
"""Constrained Iran HTTP CONNECT bootstrap relay for TwinConnect control APIs.

Permits exactly CONNECT panel.matindnspro.sbs:443 and forwards unchanged TLS
bytes to the pinned French panel. It does not decrypt, log or store passwords,
session tokens, node profiles, URLs, HTTP headers or request/response bodies.
The client still validates the genuine panel TLS certificate and hostname.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
import ipaddress
import logging

PANEL_HOST = "panel.matindnspro.sbs"
PANEL_IP = "217.179.6.142"
MAX_CONNECTIONS = 512
MAX_PER_CLIENT = 32
HEADER_TIMEOUT = 6
UPSTREAM_TIMEOUT = 6
IDLE_TIMEOUT = 90
HEADER_MAX = 4096
logger = logging.getLogger("twinconnect-iran-connect")


def permitted_connect_header(header: bytes) -> bool:
    if not header.endswith(b"\r\n\r\n") or len(header) > HEADER_MAX:
        return False
    try:
        first, *rest = header[:-4].split(b"\r\n")
        method, target, version = first.split(b" ")
        if method != b"CONNECT" or version not in (b"HTTP/1.1", b"HTTP/1.0"):
            return False
        if target != f"{PANEL_HOST}:443".encode("ascii"):
            return False
        if not rest or any(b"\x00" in line or len(line) > 1024 for line in rest):
            return False
        for line in rest:
            if line and b":" not in line:
                return False
        return True
    except (ValueError, UnicodeError):
        return False


async def pump(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
    while True:
        chunk = await asyncio.wait_for(src.read(65536), timeout=IDLE_TIMEOUT)
        if not chunk:
            return
        dst.write(chunk)
        await dst.drain()


async def run_gateway(host: str, port: int, upstream_ip: str = PANEL_IP,
                      upstream_port: int = 443) -> None:
    ipaddress.ip_address(upstream_ip)
    active = Counter()
    slots = asyncio.Semaphore(MAX_CONNECTIONS)

    async def handle(client: asyncio.StreamReader,
                     writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        client_ip = str(peer[0]) if isinstance(peer, tuple) else "unknown"
        if slots.locked() or active[client_ip] >= MAX_PER_CLIENT:
            writer.close()
            await writer.wait_closed()
            return
        await slots.acquire()
        active[client_ip] += 1
        server_writer: asyncio.StreamWriter | None = None
        try:
            header = await asyncio.wait_for(
                client.readuntil(b"\r\n\r\n"), timeout=HEADER_TIMEOUT)
            if not permitted_connect_header(header):
                writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
                return
            upstream_reader, server_writer = await asyncio.wait_for(
                asyncio.open_connection(upstream_ip, upstream_port),
                timeout=UPSTREAM_TIMEOUT,
            )
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            tasks = [
                asyncio.create_task(pump(client, server_writer)),
                asyncio.create_task(pump(upstream_reader, writer)),
            ]
            complete, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in complete:
                try:
                    task.result()
                except (ConnectionError, TimeoutError, OSError):
                    pass
        except (OSError, ValueError, TimeoutError, asyncio.LimitOverrunError,
                asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            if server_writer is not None:
                server_writer.close()
                try:
                    await asyncio.wait_for(server_writer.wait_closed(), timeout=2)
                except (OSError, ConnectionError, TimeoutError):
                    pass
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=2)
            except (OSError, ConnectionError, TimeoutError):
                pass
            active[client_ip] -= 1
            if active[client_ip] <= 0:
                active.pop(client_ip, None)
            slots.release()

    server = await asyncio.start_server(handle, host, port, backlog=512,
                                        limit=HEADER_MAX)
    logger.info("CONNECT relay online port=%s allowed_host=%s", port, PANEL_HOST)
    async with server:
        await server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18080)
    parser.add_argument("--upstream-ip", default=PANEL_IP)
    parser.add_argument("--upstream-port", type=int, default=443)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 1 <= args.upstream_port <= 65535:
        parser.error("invalid port")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(run_gateway(args.bind, args.port, args.upstream_ip,
                            args.upstream_port))


if __name__ == "__main__":
    main()
