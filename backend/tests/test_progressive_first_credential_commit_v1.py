"""The fast new-account path must publish a usable first protocol promptly.

Tests use fake SSH/node/DB objects and make no changes to active subscriptions.
"""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.routers import modern_account_delivery_v1 as delivery


class ProgressiveFirstCredentialTests(unittest.IsolatedAsyncioTestCase):
    async def _batch(self, early: bool, fail_first: bool = False):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        sub = SimpleNamespace(id=987654, account_username="test-account")
        nodes = [
            SimpleNamespace(id=11, name="first"),
            SimpleNamespace(id=12, name="second"),
        ]
        creds = {
            p: SimpleNamespace(
                protocol=p, username=None, is_active=False,
                config_text_encrypted=None, secret_encrypted=None,
            )
            for p in ("hysteria2", "tuic")
        }
        ad = SimpleNamespace()
        ad._enc = lambda v: "encrypted-nonempty"
        conn = MagicMock()
        conn.wait_closed = AsyncMock()
        ad.ssh_connect_saved = AsyncMock(return_value=conn)
        attempted = []

        async def node_batch(connection, node, secrets):
            attempted.append(node.id)
            if fail_first and node.id == 11:
                raise RuntimeError("test node is unreachable")
            if node.id == 12 and early:
                # The first successful node must already be visible, even
                # before the next node finishes its setup.
                self.assertEqual(db.commit.call_count, 1 if not fail_first else 0)
            return [
                {"node_id": node.id, "config": "usable-live-client-config"}
                for _ in secrets
            ]

        def fake_get_credential(_db, _sid, protocol):
            return creds[protocol]

        with (
            patch.object(delivery, "_get_credential", side_effect=fake_get_credential),
            patch.object(delivery, "_modern_runtime_config", return_value=SimpleNamespace(status="online")),
            patch.object(delivery, "_singbox_secret",
                         side_effect=lambda _ad, _cred, proto, _sub: SimpleNamespace(
                             protocol=proto, username=f"test-{proto}"
                         )),
            patch("app.singbox_subscription_accounts.apply_accounts_batch",
                  side_effect=node_batch),
            patch("app.singbox_subscription_accounts.secret_to_dict",
                  side_effect=lambda secret: {"protocol": secret.protocol}),
        ):
            grouped, errors = await delivery._provision_new_singbox_node_batches(
                ad, db, sub, ["hysteria2", "tuic"], nodes,
                publish_first_credential=early,
            )
        return db, creds, grouped, errors, attempted

    async def test_early_first_node_is_committed_before_second_node(self):
        db, creds, grouped, errors, attempted = await self._batch(True)
        self.assertEqual(attempted, [11, 12])
        db.commit.assert_called_once()
        self.assertTrue(all(cred.is_active for cred in creds.values()))
        self.assertTrue(all(cred.config_text_encrypted for cred in creds.values()))
        self.assertEqual(len(grouped["hysteria2"]), 2)
        self.assertEqual(len(grouped["tuic"]), 2)
        self.assertEqual(errors, [])

    async def test_non_fast_provisioning_retains_original_transaction_boundary(self):
        db, _, grouped, _, _ = await self._batch(False)
        db.commit.assert_not_called()
        self.assertEqual(len(grouped["hysteria2"]), 2)

    async def test_first_failed_node_does_not_publish_unusable_credential(self):
        db, _, grouped, errors, _ = await self._batch(True, fail_first=True)
        db.commit.assert_called_once()  # The second, successful node is first.
        self.assertEqual(len(grouped["hysteria2"]), 1)
        self.assertTrue(any("unreachable" in str(e["error"]) for e in errors))

    def test_fallback_first_protocol_and_guarded_fast_only(self):
        import inspect
        source = inspect.getsource(delivery._provision_account_v1_locked)
        fast_source = inspect.getsource(delivery.provision_new_account_fast_v1)
        self.assertIn("if publish_first_credential and not first_credential_published", source)
        self.assertIn("if cred.is_active and cred.config_text_encrypted:", source)
        self.assertIn("publish_first_credential=True", fast_source)
        self.assertIn("db.commit()", source)


if __name__ == "__main__":
    unittest.main()
