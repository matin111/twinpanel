"""Node-only Sing-box aliases must never bypass expiry/quota enforcement."""
from __future__ import annotations
import os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,AsyncMock
from dataclasses import is_dataclass

tmp=tempfile.TemporaryDirectory(prefix="tp-quota-alias-")
os.environ.setdefault("APP_SECRET_KEY","ci-quota-node-identity")
os.environ.setdefault("DATABASE_URL",f"sqlite+pysqlite:///{Path(tmp.name)/'db.sqlite'}")
os.environ.setdefault("NODE_AGENT_SHARED_SECRET","ci-quota-node-agent")

from app.services.account_enforcement_v2 import _singbox_node_secret
from app.singbox_subscription_accounts import SingBoxAccountSecret,remove_account


class NodeAliasEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.secret=SingBoxAccountSecret(protocol="naive",username="shared-mother",
                                       password="unchanged-password")
        self.cred=SimpleNamespace(config_text_encrypted="mock")

    def test_restore_uses_actual_node_item_and_preserves_password(self):
        with patch("app.routers.account_delivery._dec",return_value=[
            {"node_id":19,"username":"tp-central-23-naive"},
            {"node_id":7,"username":"shared-mother"},
        ]):
            on_new=_singbox_node_secret(self.cred,"naive",19,self.secret)
            on_old=_singbox_node_secret(self.cred,"naive",7,self.secret)
            legacy=_singbox_node_secret(self.cred,"naive",3,self.secret)
        self.assertEqual(on_new.username,"tp-central-23-naive")
        self.assertEqual(on_old.username,"shared-mother")
        self.assertEqual(legacy.username,"shared-mother")
        self.assertEqual(on_new.password,self.secret.password)
        self.assertEqual(self.secret.username,"shared-mother")
        self.assertTrue(is_dataclass(on_new))

    def test_missing_item_username_fails_closed(self):
        with patch("app.routers.account_delivery._dec",return_value=[
            {"node_id":19,"username":""},
        ]):
            with self.assertRaisesRegex(RuntimeError,"identity missing"):
                _singbox_node_secret(self.cred,"naive",19,self.secret)

    def test_duplicate_items_on_same_node_are_rejected(self):
        with patch("app.routers.account_delivery._dec",return_value=[
            {"node_id":19,"username":"first"},
            {"node_id":19,"username":"second"},
        ]):
            with self.assertRaisesRegex(RuntimeError,"duplicate"):
                _singbox_node_secret(self.cred,"naive",19,self.secret)

    def test_revoke_uses_actual_node_identity_not_account_id(self):
        import asyncio
        with patch("app.singbox_subscription_accounts._commit_account_config",
                   new_callable=AsyncMock) as commit:
            asyncio.run(remove_account(object(),"naive",23,
                                        node_username="tp-central-23-naive"))
        source=commit.await_args.args[1]
        self.assertIn("tp-central-23-naive",source)
        self.assertNotIn("tp-sub-23",source)

    def test_global_mother_credential_not_mutated_by_node_bulk(self):
        script=(Path(__file__).resolve().parents[1]/
                "scripts/twinpanel_central_singbox_node_bulk_v1.py").read_text()
        self.assertIn("cred.username=mother_name",script)
        self.assertIn("if not cred.secret_encrypted:",script)
        self.assertIn("cred.config_text_encrypted=ad._enc(old)",script)
        self.assertIn("bound_mother_names",script)
        self.assertIn("resolve_node_login_collisions(",script)

if __name__=="__main__":
    unittest.main()
