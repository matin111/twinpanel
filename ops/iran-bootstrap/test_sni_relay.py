"""Synthetic local tests: never connect to customer servers or private APIs."""
import asyncio
import contextlib
import importlib.util
import socket
import struct
import unittest
from pathlib import Path

src = Path(__file__).with_name("sni_relay.py")
spec = importlib.util.spec_from_file_location("iran_bootstrap_sni", src)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def fake_client_hello(host="panel.matindnspro.sbs"):
    name = host.encode("ascii")
    names = bytes([0]) + struct.pack("!H", len(name)) + name
    sni = struct.pack("!H", len(names)) + names
    ext = struct.pack("!HH", 0, len(sni)) + sni
    payload = (
        b"\x03\x03" + bytes(range(32)) +
        b"\x00" +  # empty session ID
        b"\x00\x02\x13\x01" +  # one cipher suite
        b"\x01\x00" +  # single null compression
        struct.pack("!H", len(ext)) + ext
    )
    handshake = b"\x01" + len(payload).to_bytes(3, "big") + payload
    return b"\x16\x03\x01" + struct.pack("!H", len(handshake)) + handshake


def vacant_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class PacketContract(unittest.TestCase):
    def test_sni_extracts_only_exact_panel(self):
        self.assertEqual(module.parse_sni(fake_client_hello()),
                         "panel.matindnspro.sbs")
        self.assertEqual(module.parse_sni(fake_client_hello("ATTACKER.invalid")),
                         "attacker.invalid")
        self.assertIsNone(module.parse_sni(b"POST / HTTP/1.1\r\n"))
        self.assertIsNone(module.parse_sni(fake_client_hello()[:6]))

    def test_oversized_handshake_is_disallowed(self):
        packet = bytearray(fake_client_hello())
        packet[3:5] = b"\xff\xff"
        self.assertIsNone(module.parse_sni(bytes(packet)))


class TunnelContract(unittest.IsolatedAsyncioTestCase):
    async def test_allowed_sni_passes_tls_bytes_untouched(self):
        upstream_receipts = []
        allowed = fake_client_hello()

        async def fake_panel(reader, writer):
            data = await reader.readexactly(len(allowed))
            upstream_receipts.append(data)
            writer.write(b"TLS_HANDSHAKE_REPLY")
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        upstream = await asyncio.start_server(fake_panel, "127.0.0.1", 0)
        port = vacant_port()
        task = asyncio.create_task(module.serve(
            "127.0.0.1", port, "127.0.0.1",
            upstream.sockets[0].getsockname()[1],
        ))
        try:
            await asyncio.sleep(0.07)
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(allowed)
            await writer.drain()
            reply = await asyncio.wait_for(reader.read(100), timeout=2)
            self.assertEqual(reply, b"TLS_HANDSHAKE_REPLY")
            self.assertEqual(upstream_receipts, [allowed])
            writer.close()
            await writer.wait_closed()

            denied = fake_client_hello("untrusted.example.com")
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(denied)
            await writer.drain()
            self.assertEqual(await asyncio.wait_for(reader.read(100), timeout=2),
                             b"")
            self.assertEqual(len(upstream_receipts), 1)
            writer.close()
            await writer.wait_closed()
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            upstream.close()
            await upstream.wait_closed()


if __name__ == "__main__":
    unittest.main()
