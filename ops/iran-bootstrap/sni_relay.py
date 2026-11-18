#!/usr/bin/env python3
"""Iran-side TLS passthrough for the TwinConnect *control plane*.

Clients dial the Iranian IP while retaining https://panel.matindnspro.sbs.
The original TLS ClientHello/SNI and TLS stream are passed unchanged to
the licensed French panel. The gateway never sees passwords, bearer tokens,
private profiles, HTTP paths or response bodies in plaintext.

Default bind port 18443 is deliberately a non-production staging port.
Production 443 must be SNI-integrated with the existing 443 multiplexer
without replacing other VPN routes.
"""
from __future__ import annotations

import argparse
import asyncio
import ipaddress
import logging
import struct

PANEL_HOST = "panel.matindnspro.sbs"
PANEL_UPSTREAM_IPV4 = "217.179.6.142"
MAX_CLIENT_HELLO = 65536
MAX_ACTIVE = 256
CONNECT_TIMEOUT = 6
HELLO_TIMEOUT = 5
IDLE_TIMEOUT = 75
log = logging.getLogger("iran-bootstrap")


def _need(data: bytes, offset: int, count: int) -> bytes:
    if count < 0 or offset + count > len(data):
        raise ValueError("short TLS ClientHello")
    return data[offset:offset + count]


def parse_sni(client_hello_record: bytes) -> str | None:
    """Parse only the unencrypted TLS ClientHello SNI, never TLS application data."""
    if len(client_hello_record) < 9 or client_hello_record[0] != 22:
        return None
    length = struct.unpack("!H", client_hello_record[3:5])[0]
    if length < 4 or length > MAX_CLIENT_HELLO or len(client_hello_record) != length + 5:
        return None
    body = client_hello_record[5:]
    if body[0] != 1:  # handshake ClientHello
        return None
    n = int.from_bytes(body[1:4], "big")
    if n + 4 > len(body):
        return None
    offset = 4 + 2 + 32  # TLS version and random
    session_len = _need(body, offset, 1)[0]
    offset += 1 + session_len
    cipher_len = struct.unpack("!H", _need(body, offset, 2))[0]
    offset += 2 + cipher_len
    compression_len = _need(body, offset, 1)[0]
    offset += 1 + compression_len
    extension_len = struct.unpack("!H", _need(body, offset, 2))[0]
    offset += 2
    end = offset + extension_len
    if end > len(body):
        return None
    while offset + 4 <= end:
        ext_type, ext_len = struct.unpack("!HH", _need(body, offset, 4))
        offset += 4
        ext_end = offset + ext_len
        if ext_end > end:
            return None
        if ext_type == 0 and ext_len >= 5:
            names_len = struct.unpack("!H", _need(body, offset, 2))[0]
            pos = offset + 2
            names_end = pos + names_len
            if names_end > ext_end:
                return None
            while pos + 3 <= names_end:
                name_type = body[pos]
                name_len = struct.unpack("!H", body[pos+1:pos+3])[0]
                pos += 3
                if pos + name_len > names_end:
                    return None
                if name_type == 0:
                    try:
                        return body[pos:pos+name_len].decode("ascii").lower().rstrip(".")
                    except UnicodeDecodeError:
                        return None
                pos += name_len
        offset = ext_end
    return None


async def read_client_hello(reader: asyncio.StreamReader) -> bytes:
    header = await asyncio.wait_for(reader.readexactly(5), timeout=HELLO_TIMEOUT)
    if header[0] != 22:
        raise ValueError("non-TLS packet")
    length = int.from_bytes(header[3:5], "big")
    if length == 0 or length > MAX_CLIENT_HELLO:
        raise ValueError("oversized hello")
    body = await asyncio.wait_for(reader.readexactly(length), timeout=HELLO_TIMEOUT)
    return header + body


async def transfer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while True:
        data = await asyncio.wait_for(reader.read(65536), timeout=IDLE_TIMEOUT)
        if not data:
            return
        writer.write(data)
        await writer.drain()


async def serve(bind_host: str, port: int, upstream_ip: str,
                upstream_port: int = 443) -> None:
    ipaddress.ip_address(upstream_ip)
    slots = asyncio.Semaphore(MAX_ACTIVE)

    async def handle(incoming: asyncio.StreamReader,
                     outgoing: asyncio.StreamWriter) -> None:
        if slots.locked():
            outgoing.close()
            await outgoing.wait_closed()
            return
        await slots.acquire()
        remote_writer: asyncio.StreamWriter | None = None
        try:
            hello = await read_client_hello(incoming)
            if parse_sni(hello) != PANEL_HOST:
                return
            remote_reader, remote_writer = await asyncio.wait_for(
                asyncio.open_connection(upstream_ip, upstream_port),
                timeout=CONNECT_TIMEOUT,
            )
            remote_writer.write(hello)
            await remote_writer.drain()
            tasks = [
                asyncio.create_task(transfer(incoming, remote_writer)),
                asyncio.create_task(transfer(remote_reader, outgoing)),
            ]
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                try:
                    task.result()
                except (ConnectionError, TimeoutError, OSError):
                    pass
        except (ValueError, OSError, asyncio.TimeoutError,
                asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            if remote_writer is not None:
                remote_writer.close()
                try:
                    await asyncio.wait_for(remote_writer.wait_closed(), timeout=2)
                except (ConnectionError, OSError, TimeoutError):
                    pass
            outgoing.close()
            try:
                await asyncio.wait_for(outgoing.wait_closed(), timeout=2)
            except (ConnectionError, OSError, TimeoutError):
                pass
            slots.release()

    server = await asyncio.start_server(handle, bind_host, port, backlog=512)
    log.info("iran bootstrap ready port=%s, SNI allowlist=%s", port, PANEL_HOST)
    async with server:
        await server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18443)
    parser.add_argument("--upstream-ip", default=PANEL_UPSTREAM_IPV4)
    parser.add_argument("--upstream-port", type=int, default=443)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or not 1 <= args.upstream_port <= 65535:
        parser.error("invalid port")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    asyncio.run(serve(args.bind, args.port, args.upstream_ip, args.upstream_port))


if __name__ == "__main__":
    main()
