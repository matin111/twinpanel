import asyncio
import contextlib
import importlib.util
import socket
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "iran_connect", Path(__file__).with_name("connect_proxy.py")
)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


class ConnectHeaderTest(unittest.TestCase):
    def test_only_exact_tls_panel_allowed(self):
        allowed = b"CONNECT panel.matindnspro.sbs:443 HTTP/1.1\r\nHost: panel.matindnspro.sbs:443\r\n\r\n"
        self.assertTrue(module.permitted_connect_header(allowed))
        for bad in [
            b"CONNECT malicious.example:443 HTTP/1.1\r\nHost: malicious.example\r\n\r\n",
            b"CONNECT panel.matindnspro.sbs:80 HTTP/1.1\r\nHost: panel.matindnspro.sbs:80\r\n\r\n",
            b"CONNECT 127.0.0.1:443 HTTP/1.1\r\nHost: localhost\r\n\r\n",
            b"GET http://panel.matindnspro.sbs/ HTTP/1.1\r\nHost: panel.matindnspro.sbs\r\n\r\n",
            b"CONNECT panel.matindnspro.sbs:443 HTTP/1.1\r\nHost: panel.matindnspro.sbs\r\n",
            b"CONNECT panel.matindnspro.sbs:443 HTTP/1.1\r\nHost: panel.matindnspro.sbs\x00\r\n\r\n",
        ]:
            self.assertFalse(module.permitted_connect_header(bad))


class ConnectFlowTest(unittest.IsolatedAsyncioTestCase):
    async def test_connect_forwards_only_authorized_opaque_stream(self):
        seen = []
        async def fake_upstream(reader, writer):
            seen.append(await reader.readexactly(7))
            writer.write(b"TLS_OK")
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        upstream = await asyncio.start_server(fake_upstream, "127.0.0.1", 0)
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        task = asyncio.create_task(module.run_gateway(
            "127.0.0.1", port, "127.0.0.1",
            upstream.sockets[0].getsockname()[1],
        ))
        try:
            await asyncio.sleep(0.07)
            r, w = await asyncio.open_connection("127.0.0.1", port)
            w.write(b"CONNECT panel.matindnspro.sbs:443 HTTP/1.1\r\nHost: panel.matindnspro.sbs:443\r\n\r\n")
            await w.drain()
            self.assertEqual(await r.readuntil(b"\r\n\r\n"),
                             b"HTTP/1.1 200 Connection Established\r\n\r\n")
            w.write(b"TLSDATA")
            await w.drain()
            self.assertEqual(await asyncio.wait_for(r.readexactly(6), 2),
                             b"TLS_OK")
            self.assertEqual(seen, [b"TLSDATA"])
            w.close()
            await w.wait_closed()

            r, w = await asyncio.open_connection("127.0.0.1", port)
            w.write(b"CONNECT google.com:443 HTTP/1.1\r\nHost: google.com\r\n\r\n")
            await w.drain()
            self.assertTrue((await asyncio.wait_for(r.read(100), 2))
                            .startswith(b"HTTP/1.1 403"))
            self.assertEqual(seen, [b"TLSDATA"])
            w.close()
            await w.wait_closed()
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            upstream.close()
            await upstream.wait_closed()
