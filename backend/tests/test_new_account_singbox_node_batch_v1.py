"""Fast-new-account sing-box provisioning uses one mutation per node."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.routers import modern_account_delivery_v1 as delivery
from app.singbox_subscription_accounts import SingBoxAccountSecret


def secret(protocol):
    return SingBoxAccountSecret(
        protocol=protocol, username="tp-sub-51", password="same-user-secret",
        uuid="3c6b78aa-2255-440b-9ef1-150cdefaca11" if protocol == "tuic" else None,
    )


class FastNewSingBoxNodeBatchTests(unittest.TestCase):
    def test_new_account_groups_multiple_protocols_once_per_node(self):
        async def run():
            db = MagicMock()
            db.query.return_value.filter.return_value.first.return_value = None
            sub = SimpleNamespace(id=51)
            node = SimpleNamespace(id=7, name="Exit-7")
            credentials = {
                p: SimpleNamespace(username=None, secret_encrypted=None,
                                   config_text_encrypted=None, is_active=False)
                for p in ("anytls", "hysteria2")
            }
            ad = SimpleNamespace(ssh_connect_saved=AsyncMock(), _enc=lambda value: value)
            conn = MagicMock()
            conn.wait_closed = AsyncMock()
            ad.ssh_connect_saved.return_value = conn
            batch = AsyncMock(return_value=[
                {"node_id": 7, "outbound": {"type": "anytls", "password": "same-user-secret"}},
                {"node_id": 7, "outbound": {"type": "hysteria2", "password": "same-user-secret"}},
            ])

            async def timeout_passthrough(awaitable, **kwargs):
                return await awaitable

            with patch.object(delivery, "_get_credential",
                              side_effect=lambda db, sub_id, p: credentials[p]), \
                 patch.object(delivery, "_singbox_secret",
                              side_effect=lambda ad, cred, p, sub: secret(p)), \
                 patch.object(delivery, "_modern_runtime_config",
                              return_value=SimpleNamespace(status="online")), \
                 patch.object(delivery, "await_hard_timeout",
                              side_effect=timeout_passthrough), \
                 patch("app.singbox_subscription_accounts.apply_accounts_batch", batch):
                result = await delivery._provision_new_singbox_node_batches(
                    ad, db, sub, ["anytls", "hysteria2"], [node],
                )

            by_protocol, errors = result
            self.assertEqual(errors, [])
            self.assertEqual(len(by_protocol["anytls"]), 1)
            self.assertEqual(len(by_protocol["hysteria2"]), 1)
            self.assertEqual(batch.await_count, 1)
            self.assertEqual(ad.ssh_connect_saved.await_count, 1)
            self.assertEqual(conn.close.call_count, 1)
            self.assertEqual(conn.wait_closed.await_count, 1)
            self.assertEqual(credentials["anytls"].username, "tp-sub-51")
            self.assertEqual(credentials["anytls"].secret_encrypted["password"], "same-user-secret")
            self.assertTrue(credentials["hysteria2"].is_active)

        asyncio.run(run())

    def test_existing_account_never_enters_new_batch(self):
        async def run():
            db = MagicMock()
            db.query.return_value.filter.return_value.first.return_value = (123,)
            with patch.object(delivery, "_get_credential") as get_cred:
                result = await delivery._provision_new_singbox_node_batches(
                    SimpleNamespace(), db, SimpleNamespace(id=51),
                    ["anytls", "hysteria2"], [SimpleNamespace(id=7)],
                )
                self.assertIsNone(result)
                get_cred.assert_not_called()
        asyncio.run(run())

    def test_only_one_singbox_protocol_preserves_legacy(self):
        async def run():
            db = MagicMock()
            result = await delivery._provision_new_singbox_node_batches(
                SimpleNamespace(), db, SimpleNamespace(id=51),
                ["anytls", "openvpn"], [SimpleNamespace(id=7)],
            )
            self.assertIsNone(result)
            db.query.assert_not_called()
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
