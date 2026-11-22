#!/usr/bin/env python3
"""Offline tests; never calls route or touches the host routing table."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch

SOURCE = Path(__file__).with_name("macos_openvpn_full_route_guard.py")
spec = importlib.util.spec_from_file_location("macos_openvpn_full_route_guard", SOURCE)
assert spec and spec.loader
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def reply(stdout: str, code: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], code, stdout, "")


class GuardTests(unittest.TestCase):
    def test_management_peer_detected_from_established_ssh(self) -> None:
        data = ("tcp4 0 0 185.236.39.36.22 203.0.113.8.54321 ESTABLISHED\n"
                "tcp4 0 0 185.236.39.36.22 8.8.8.8.54321 ESTABLISHED\n")
        # Documentation-only TEST-NET peer is never treated as a real route.
        with patch.object(guard, "run", return_value=reply(data)):
            self.assertEqual(guard.management_peers(), ["8.8.8.8"])

    def test_termalin_outbound_control_peer_is_pinned(self) -> None:
        sample = ("COMMAND PID USER FD TYPE DEVICE SIZE/OFF NODE NAME\\n"
                  "termalin-agent 77 root 13u IPv4 0t0 TCP "
                  "185.236.39.36:54006->188.114.97.3:443 (ESTABLISHED)\\n"
                  "termalin-agent 77 root 14u IPv4 0t0 TCP "
                  "127.0.0.1:54007->127.0.0.1:22 (ESTABLISHED)\\n")
        def fake_run(*args: str) -> subprocess.CompletedProcess[str]:
            if "pgrep" in args[0]:
                return reply("77\\n")
            if "lsof" in args[0]:
                return reply(sample)
            return reply("", 1)
        with patch.object(guard, "run", side_effect=fake_run):
            self.assertEqual(guard.termalin_control_peers(), ["188.114.97.3"])

    def test_no_ssh_fails_without_installing_routes(self) -> None:
        # Pretend that a valid tunnel, daemon, baseline gateway and
        # transport endpoint exist; management peer gate still blocks.
        def fake_run(*args: str) -> subprocess.CompletedProcess[str]:
            if "ifconfig" in args[0]:
                return reply("en0 utun4")
            if "launchctl" in args[0]:
                return reply("state = running")
            if "netstat" in args[0]:
                return reply("")
            return reply("")
        with (patch.object(guard, "load", return_value={}),
              patch.object(guard, "run", side_effect=fake_run),
              patch.object(guard, "management_peers", return_value=[]),
              patch.object(guard, "get_route",
                           return_value={"interface": "en0", "gateway": "192.0.2.1"}),
              patch.object(guard, "SESSION", Mock(read_text=Mock(return_value=
                           '{"worker_pid":222,"interface":"utun4",'
                           '"state":"tunnel_established_unrouted",'
                           '"deadline":99999999999}'))),
              patch.object(guard.os, "kill", return_value=None),
              patch.object(guard, "store") as store):
            self.assertEqual(guard.trial("8.8.8.8"),
                             "REMOTE_MANAGEMENT_PEER_REQUIRED")
            store.assert_not_called()


if __name__ == "__main__":
    unittest.main()
