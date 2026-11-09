"""Central-new-Exit installation must never invoke legacy account creation."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import NodeType
from app.services.central_first_exit_bootstrap_v1 import (
    bootstrap_hidden_central_exit,
)
from app.routers import provision as prov


def payload(*, node_type=NodeType.EXIT, defer=True):
    return SimpleNamespace(
        name="uk-test", node_type=node_type, defer_subscription_sync=defer,
        host="203.0.113.15", port=22, username="root",
        country_code="GB", capacity_users=10000,
        install_cisco=True, install_openvpn=True,
        install_wireguard=True, install_l2tp=True, install_v2ray=True,
    )


class CentralFirstExitBootstrapTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_exit_bootstraps_daemons_only_without_legacy_installer(self):
        db=MagicMock()
        db.query.return_value.filter.return_value.first.return_value=None
        def allocate_node_id():
            db.add.call_args.args[0].id=15
        db.flush.side_effect=allocate_node_id

        async def check_read_transaction_closed(conn):
            # The read-only duplicate lookup must not hold a connection
            # while apt, Xray and other remote installs are awaited.
            db.rollback.assert_called_once()
            return "ubuntu"
        conn=MagicMock()
        conn.wait_closed=AsyncMock()
        with (
            patch.object(prov,"ssh_connect",new_callable=AsyncMock,
                         return_value=conn),
            patch.object(prov,"cmd",new_callable=AsyncMock,
                         return_value="ubuntu"),
            patch.object(prov,"remote_supported_os_id",
                         new_callable=AsyncMock,
                         side_effect=check_read_transaction_closed) as remote_os,
            patch.object(prov,"ensure_base",new_callable=AsyncMock),
            patch.object(prov,"provision_protocols",new_callable=AsyncMock,
                         return_value=({"openvpn":{"ok":True}},[],{})) as daemons,
            patch("app.services.central_new_exit_wireguard_pool_v1.prepare_hidden_exit_wireguard_pool",
                  new_callable=AsyncMock,
                  return_value={"ok":True,"pool":"10.96/21"}) as wgpool,
            patch.object(prov,"_install_or_upgrade_agent",
                         new_callable=AsyncMock,return_value={"ok":True}),
            patch.object(prov,"_ensure_node_key_on_remote",
                         new_callable=AsyncMock),
            patch.object(prov,"_install_tunnel_fabric_base",
                         new_callable=AsyncMock,return_value={"ok":True}),
            patch("app.services.central_first_exit_bootstrap_v1.bootstrap_fresh_hidden_exit_quota",
                  return_value={"ok":True,"devices":0}) as quota,
            patch.object(prov,"install_node",new_callable=AsyncMock) as legacy,
        ):
            result=await bootstrap_hidden_central_exit(payload(),MagicMock(),db)
            self.assertTrue(result["ok"])
            self.assertEqual(result["installation_authority"],"central_runtime_v1")
            self.assertEqual(result["node_id"],15)
            self.assertEqual(result["subscription_sync"]["reason"],
                             "central_runtime_owns_all_subscriptions")
            self.assertFalse(db.add.call_args.args[0].show_to_users)
            remote_os.assert_awaited_once_with(conn)
            db.flush.assert_called()
            db.refresh.assert_not_called()
            db.rollback.assert_called_once()
            daemons.assert_awaited_once()
            self.assertIs(daemons.await_args.args[4],False)
            quota.assert_called_once_with(db,15)
            wgpool.assert_awaited_once_with(conn)
            legacy.assert_not_awaited()
            conn.close.assert_called_once()
            conn.wait_closed.assert_awaited_once()

    async def test_not_hidden_and_not_exit_fails_before_remote_install(self):
        for p in (payload(defer=False),payload(node_type=NodeType.IRAN)):
            with patch.object(prov,"ssh_connect",new_callable=AsyncMock) as ssh:
                with self.assertRaisesRegex(RuntimeError,"REQUIRES_HIDDEN_EXIT"):
                    await bootstrap_hidden_central_exit(p,MagicMock(),MagicMock())
                ssh.assert_not_awaited()


if __name__=="__main__":
    unittest.main()
