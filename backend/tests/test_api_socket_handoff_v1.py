"""Non-production regression tests for optional API listener handoff."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from unittest import mock

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "twinpanel_api_socket_handoff_v1.py"
SPEC = importlib.util.spec_from_file_location("tp_socket_handoff", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class SocketUnitContract(unittest.TestCase):
    def test_socket_listens_on_loopback_only(self) -> None:
        rendered = module.socket_unit(8095)
        self.assertIn("ListenStream=127.0.0.1:8095\n", rendered)
        self.assertIn("Backlog=2048\n", rendered)
        self.assertIn("Accept=no\n", rendered)
        self.assertIn("Service=twinpanel-api.service\n", rendered)
        self.assertNotIn("0.0.0.0:8095", rendered)
        with self.assertRaises(ValueError):
            module.socket_unit(0)

    def test_dropin_uses_systemd_fd_three_and_existing_api_runtime(self) -> None:
        override = module.service_override()
        self.assertIn("Requires=twinpanel-api.socket", override)
        self.assertIn("After=twinpanel-api.socket", override)
        self.assertIn("Sockets=twinpanel-api.socket", override)
        self.assertIn("ExecStart=\n", override)
        self.assertIn("uvicorn app.main:app --fd 3 --workers 1", override)

    def test_read_only_default_cannot_restart_service(self) -> None:
        capture = io.StringIO()
        with mock.patch.object(module, "ensure_safe_state", return_value=(8095, "1.1.0-rc.737")), \
             mock.patch.object(module, "run") as calls, \
             contextlib.redirect_stdout(capture):
            self.assertEqual(module.main([]), 0)
        self.assertEqual(json.loads(capture.getvalue())["mode"], "read_only")
        calls.assert_not_called()

    def test_explicit_cutover_ack_required(self) -> None:
        with mock.patch.object(module, "ensure_safe_state", return_value=(8095, "1.1.0-rc.737")), \
             mock.patch.object(module, "enable") as enable, \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                module.main(["--apply"])
            enable.assert_not_called()

    def test_failed_activation_restores_normal_bind_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            socket_unit = root / "twinpanel-api.socket"
            override = root / "twinpanel-api.service.d" / "90-socket-handoff.conf"
            executed = []
            def command(*args: str, check: bool = True):
                executed.append(args)
                return subprocess.CompletedProcess(args, 0, "", "")
            with mock.patch.object(module, "SOCKET_UNIT", socket_unit), \
                 mock.patch.object(module, "OVERRIDE", override), \
                 mock.patch.object(module, "is_active", side_effect=lambda x: x == "twinpanel-api.service"), \
                 mock.patch.object(module, "check_health", side_effect=(True, False)), \
                 mock.patch.object(module, "run", side_effect=command):
                with self.assertRaisesRegex(RuntimeError, "API_SOCKET_HEALTH_GATE_FAILED"):
                    module.enable(8095, "1.1.0-rc.737")
            self.assertFalse(socket_unit.exists())
            self.assertFalse(override.exists())
            self.assertIn(("disable", "--now", "twinpanel-api.socket"), executed)
            self.assertEqual(executed[-1], ("start", "twinpanel-api.service"))


class InheritedUvicornListener(unittest.TestCase):
    """An isolated loopback ephemeral socket; never touches systemd or TwinPanel."""

    def test_request_survives_worker_replacement_without_refused_connection(self):
        try:
            import uvicorn  # noqa: F401
        except ImportError:
            self.skipTest("uvicorn is not available")
        with tempfile.TemporaryDirectory(prefix="tp-api-socket-ci-") as dirname:
            root = Path(dirname)
            (root / "socket_app.py").write_text(
                "async def app(scope, receive, send):\n"
                "    await send({'type': 'http.response.start', 'status': 200, 'headers': []})\n"
                "    await send({'type': 'http.response.body', 'body': b'ok'})\n",
                encoding="utf-8",
            )
            listen = socket.socket()
            listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listen.bind(("127.0.0.1", 0))
            listen.listen(64)
            listen.set_inheritable(True)
            port = listen.getsockname()[1]
            env = dict(os.environ)
            env["PYTHONPATH"] = str(root)
            processes = []

            def start_worker():
                worker = subprocess.Popen(
                    [sys.executable, "-m", "uvicorn", "socket_app:app",
                     "--fd", str(listen.fileno()), "--workers", "1", "--log-level", "error"],
                    env=env, pass_fds=(listen.fileno(),),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                processes.append(worker)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    try:
                        with urllib.request.urlopen(
                            "http://127.0.0.1:" + str(port), timeout=0.5
                        ) as response:
                            if response.status == 200 and response.read() == b"ok":
                                return worker
                    except OSError:
                        time.sleep(0.1)
                raise RuntimeError("isolated Uvicorn socket worker failed to start")

            try:
                first = start_worker()
                first.terminate()
                first.wait(timeout=5)
                queued = socket.socket()
                queued.settimeout(10)
                try:
                    # The parent-owned listener stays open while no child runs.
                    queued.connect(("127.0.0.1", port))
                    queued.sendall(b"GET / HTTP/1.0\r\nHost: localhost\r\n\r\n")
                    start_worker()
                    response = queued.recv(4096)
                    self.assertIn(b"200 OK", response)
                finally:
                    queued.close()
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.terminate()
                        process.wait(timeout=5)
                listen.close()


if __name__ == "__main__":
    unittest.main()
