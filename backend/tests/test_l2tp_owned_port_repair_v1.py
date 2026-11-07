"""Regression: L2TP repair must recognize its own IPsec ports, not foreign ones."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# App startup reads backend Settings. CI uses a disposable SQLite bootstrap.
_bootstrap = tempfile.TemporaryDirectory(prefix="tp-l2tp-preflight-")
os.environ.setdefault("APP_SECRET_KEY", "test-only-l2tp-preflight-key")
os.environ.setdefault(
    "DATABASE_URL",
    f"sqlite+pysqlite:///{Path(_bootstrap.name) / 'bootstrap.sqlite3'}",
)
os.environ.setdefault("NODE_AGENT_SHARED_SECRET", "test-only-l2tp-preflight-shared")

from app.routers import provision


class OwnedPortPreflightTests(unittest.IsolatedAsyncioTestCase):
    async def run_preflight(self, ports=(), owners=None, ipsec=None, active_services=None):
        owners = owners or {}
        active_services = active_services if active_services is not None else True
        requests = []

        async def fake_listener(conn, port, proto):
            self.assertEqual(proto, "udp")
            return port in ports

        async def fake_cmd(conn, command, check=False):
            requests.append(command)
            if command.startswith("ss -H "):
                port = int(command.rsplit(":", 1)[-1].split("'")[0])
                owner = owners.get(port, "charon" if port in (500, 4500) else "xl2tpd")
                if owner == "unavailable":
                    return "UNCONN 0 0 0.0.0.0:500 0.0.0.0:*"
                return (
                    f'UNCONN 0 0 0.0.0.0:{port} 0.0.0.0:* '
                    f'users:(("{owner}",pid=123,fd=4))'
                )
            if command == "ipsec status":
                return ipsec if ipsec is not None else (
                    "Security Associations (0 up, 0 connecting):\n none"
                )
            self.fail(f"Unexpected remote command: {command}")

        async def fake_active(conn, *services):
            self.assertTrue(services)
            return active_services

        with (
            patch.object(provision, "listener", side_effect=fake_listener),
            patch.object(provision, "cmd", side_effect=fake_cmd),
            patch.object(provision, "active", side_effect=fake_active),
        ):
            await provision.preflight_l2tp_ports(object())
        return requests

    async def test_new_node_without_listeners_is_allowed(self):
        requests = await self.run_preflight(ports=())
        self.assertEqual(requests, [])

    async def test_existing_strongswan_owned_ports_are_allowed(self):
        commands = await self.run_preflight(ports=(500, 4500))
        self.assertTrue(any(s == "ipsec status" for s in commands))

    async def test_existing_xl2tpd_owner_is_allowed(self):
        commands = await self.run_preflight(ports=(500, 4500, 1701))
        self.assertEqual(len([s for s in commands if s.startswith("ss -H ")]), 3)

    async def test_foreign_listener_is_never_adopted(self):
        with self.assertRaisesRegex(RuntimeError, "سرویس ناشناس"):
            await self.run_preflight(ports=(500,), owners={500: "openvpn"})

    async def test_hidden_process_owner_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "سرویس ناشناس"):
            await self.run_preflight(ports=(500,), owners={500: "unavailable"})

    async def test_inactive_owning_service_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "فعال نیست"):
            await self.run_preflight(ports=(500,), active_services=False)

    async def test_existing_active_ipsec_association_is_protected(self):
        with self.assertRaisesRegex(RuntimeError, "IPsec"):
            await self.run_preflight(
                ports=(500, 4500),
                ipsec="Security Associations (1 up, 0 connecting):",
            )

    async def test_unknown_ipsec_association_count_is_protected(self):
        with self.assertRaisesRegex(RuntimeError, "IPsec"):
            await self.run_preflight(ports=(500,), ipsec="IPsec status unavailable")

    async def test_l2tp_existing_health_checks_entire_stack(self):
        p = provision.ProtocolSettings()
        async def true_listener(conn, port, proto):
            return port in (500, 4500, 1701)
        async def partial_active(conn, *services):
            return services != ("xl2tpd",)
        with (
            patch.object(provision, "listener", side_effect=true_listener),
            patch.object(provision, "active", side_effect=partial_active),
        ):
            self.assertFalse(await provision.existing_ok(object(), "l2tp", p))
        with (
            patch.object(provision, "listener", side_effect=true_listener),
            patch.object(provision, "active", return_value=True),
        ):
            self.assertTrue(await provision.existing_ok(object(), "l2tp", p))


if __name__ == "__main__":
    unittest.main()
