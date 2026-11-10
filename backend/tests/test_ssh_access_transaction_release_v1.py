"""SSH access transaction regression: no PostgreSQL transaction across network await.

No real SSH access or database. All server/session objects are local mocks.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, mock

from fastapi import HTTPException

from app.models import NodeType
from app.node_runtime_connection import connect_protocol_runtime
from app.routers import provision


class SSHAccessTransactionTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = TemporaryDirectory()
        self.addAsyncCleanup(asyncio.to_thread, self.tmp.cleanup)
        self.key = Path(self.tmp.name) / "node.key"
        self.key.write_text("test placeholder only", encoding="utf-8")
        self.node = SimpleNamespace(id=17, public_ip="192.0.2.77",
                                    agent_url="", is_mother=False, node_type=NodeType.EXIT)
        self.access = SimpleNamespace(private_key_path=str(self.key),
                                      ssh_port=2222, ssh_username="canary")
        self.db = mock.MagicMock()
        self.db.query.return_value.filter.return_value.first.return_value = self.access
        self.db.new = set()
        self.db.dirty = set()
        self.db.deleted = set()
        self.ssh = mock.AsyncMock(return_value=object())

    async def test_opt_in_closes_access_select_transaction_before_ssh(self):
        async def fake_connect(*args, **kwargs):
            self.db.commit.assert_called_once()
            self.assertEqual(args[0], "192.0.2.77")
            self.assertEqual(kwargs["port"], 2222)
            self.assertEqual(kwargs["username"], "canary")
            self.assertEqual(kwargs["client_keys"], [str(self.key)])
            return object()
        with mock.patch.object(provision.asyncssh, "connect", side_effect=fake_connect):
            await connect_protocol_runtime(
                self.node, self.db, close_read_transaction_before_ssh=True
            )
        self.db.commit.assert_called_once()

    async def test_existing_callers_do_not_gain_transaction_commit(self):
        with mock.patch.object(provision.asyncssh, "connect", self.ssh):
            await connect_protocol_runtime(self.node, self.db)
        self.db.commit.assert_not_called()
        self.ssh.assert_awaited_once()

    async def test_opt_in_rejects_staged_writes_before_network(self):
        for field in ("new", "dirty", "deleted"):
            with self.subTest(field=field):
                self.db.reset_mock()
                self.db.new = set()
                self.db.dirty = set()
                self.db.deleted = set()
                setattr(self.db, field, {object()})
                with mock.patch.object(provision.asyncssh, "connect", self.ssh):
                    with self.assertRaisesRegex(RuntimeError, "SSH_READ_TXN_HAS_PENDING_WRITES"):
                        await connect_protocol_runtime(
                            self.node, self.db, close_read_transaction_before_ssh=True
                        )
                self.db.commit.assert_not_called()
                self.ssh.assert_not_awaited()

    async def test_missing_access_fails_closed_no_commit_or_connect(self):
        self.db.query.return_value.filter.return_value.first.return_value = None
        with mock.patch.object(provision.asyncssh, "connect", self.ssh):
            with self.assertRaises(HTTPException) as got:
                await connect_protocol_runtime(
                    self.node, self.db, close_read_transaction_before_ssh=True
                )
        self.assertEqual(got.exception.status_code, 409)
        self.db.commit.assert_not_called()
        self.ssh.assert_not_awaited()

    async def test_exit_direct_failure_can_use_iran_fallback_without_db_read_wait(self):
        from app import node_bootstrap_control_v74 as v74
        iran = SimpleNamespace(id=3, public_ip="198.51.100.3",
                               node_type=NodeType.IRAN)
        iran_connection = SimpleNamespace()
        successes = []
        async def connect_with_fallback(host, **kwargs):
            # Both direct and Iran access records are read BEFORE the await.
            self.assertEqual(self.db.commit.call_count, len(successes) + 1)
            successes.append(host)
            if host == "192.0.2.77":
                raise ConnectionError("direct unavailable")
            return iran_connection
        with mock.patch.object(provision.asyncssh, "connect",
                               side_effect=connect_with_fallback), \
             mock.patch.object(v74.v72, "_first_management_iran", return_value=iran), \
             mock.patch.object(v74.v72.NativeIranExitConnection,
                               "open_with_private_key",
                               new_callable=mock.AsyncMock,
                               return_value="native-fallback") as native:
            result = await connect_protocol_runtime(
                self.node, self.db, close_read_transaction_before_ssh=True
            )
        self.assertEqual(result, "native-fallback")
        self.assertEqual(successes, ["192.0.2.77", "198.51.100.3"])
        self.assertEqual(self.db.commit.call_count, 2)
        native.assert_awaited_once()

    async def test_failed_worker_read_commit_aborts_before_connect_or_fallback(self):
        from app import node_bootstrap_control_v74 as v74
        self.db.commit.side_effect = RuntimeError("database unavailable")
        with mock.patch.object(provision.asyncssh, "connect", self.ssh), \
             mock.patch.object(v74.v72, "_first_management_iran") as find_iran:
            with self.assertRaisesRegex(RuntimeError, "SSH_READ_TXN_CLOSE_FAILED"):
                await connect_protocol_runtime(
                    self.node, self.db, close_read_transaction_before_ssh=True
                )
        self.db.rollback.assert_called_once()
        self.ssh.assert_not_awaited()
        find_iran.assert_not_called()

    async def test_opt_in_retains_exact_original_ssh_security_options(self):
        with mock.patch.object(provision.asyncssh, "connect", self.ssh):
            await connect_protocol_runtime(
                self.node, self.db, close_read_transaction_before_ssh=True
            )
        options = self.ssh.await_args.kwargs
        self.assertIn("known_hosts", options)
        self.assertEqual(options["connect_timeout"], 12)
        self.assertEqual(options["login_timeout"], 12)


if __name__ == "__main__":
    import unittest
    unittest.main()
