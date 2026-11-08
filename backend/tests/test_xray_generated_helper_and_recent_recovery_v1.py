"""Regression: generated VLESS helper valid Python and recent accounts self-heal.

The original bug shipped because the containing module compiled while its
embedded Python source missed a closing parenthesis in clients.append(client).
All tests run without live SSH, DB writes, or customer credentials.
"""
from __future__ import annotations

import os
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("APP_SECRET_KEY", "ci-vless-delivery-recovery")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:////tmp/ci-vless-recovery.sqlite3")
os.environ.setdefault("NODE_AGENT_SHARED_SECRET", "ci-vless-recovery-agent")

from app.protocol_account_registry import MODERN_PROTOCOL_KEYS as REGISTRY_MODERN
from app.routers import modern_legacy_reconcile_v1 as recovery
from app.routers import modern_account_delivery_v1 as accounts
from app import xray_hot_client_sync_v1 as xray
from app import xray_bulk_hot_sync_pilot_v1 as bulk


class XrayGeneratedScriptGuard(unittest.TestCase):
    def test_both_live_update_scripts_compile_before_release(self):
        compile(xray._REMOTE, "<xray-single-node-helper>", "exec")
        compile(bulk._REMOTE, "<xray-bulk-node-helper>", "exec")
        script=xray.hot_client_sync_script(
            "edeea23c-4610-420b-baf7-e41a27f64b62",
            "mv-3874@twinpanel",
        )
        compile(script, "<generated-vless-hot-client>", "exec")
        self.assertIn("clients.append(client)", script)
        self.assertIn('client["flow"] = "xtls-rprx-vision"', script)
        self.assertIn("VLESS UUID rotation requires explicit", script)
        self.assertNotIn("systemctl restart xray", script)
        self.assertNotIn("systemctl stop xray", script)

    def test_script_compiler_fails_closed_on_a_new_syntax_regression(self):
        broken=xray._REMOTE.replace("clients.append(client)","clients.append(client")
        self.assertNotEqual(broken,xray._REMOTE)
        with patch.object(xray,"_REMOTE",broken):
            with self.assertRaisesRegex(RuntimeError,"XRAY_HOT_CLIENT_SCRIPT_SYNTAX_INVALID"):
                xray.hot_client_sync_script(
                    "edeea23c-4610-420b-baf7-e41a27f64b62",
                    "mv-3874@twinpanel",
                )

    def test_entrypoint_does_not_expose_uuid(self):
        with patch.object(xray,"_REMOTE","def broken(: pass"):
            with self.assertRaises(RuntimeError) as err:
                xray.hot_client_sync_script(
                    "edeea23c-4610-420b-baf7-e41a27f64b62",
                    "mv-3874@twinpanel",
                )
        self.assertEqual(str(err.exception),"XRAY_HOT_CLIENT_SCRIPT_SYNTAX_INVALID")


class XrayRecoveryPolicyTests(unittest.TestCase):
    def test_v2ray_recovery_is_separate_from_plan_protocol_family(self):
        self.assertIn("v2ray", recovery.MODERN_PROTOCOL_KEYS)
        self.assertNotIn("v2ray", REGISTRY_MODERN)
        self.assertEqual(recovery.MODERN_PROTOCOL_KEYS.count("v2ray"),1)

    def test_vless_credential_does_not_require_a_fake_password(self):
        row=SimpleNamespace(protocol="v2ray",is_active=True,
                            config_text_encrypted="encrypted-config",
                            secret_encrypted=None)
        self.assertEqual(recovery.credential_state(row),"complete")
        row.is_active=False
        self.assertEqual(recovery.credential_state(row),"partial")
        row.config_text_encrypted=None
        self.assertEqual(recovery.credential_state(row),"legacy_empty")
        self.assertEqual(recovery.credential_state(None),"missing")

    def test_modern_credential_classification_is_unchanged(self):
        row=SimpleNamespace(protocol="anytls",is_active=True,
                            config_text_encrypted="encrypted-config",
                            secret_encrypted=None)
        self.assertEqual(recovery.credential_state(row),"partial")
        row.secret_encrypted="encrypted-secret"
        self.assertEqual(recovery.credential_state(row),"complete")

    def test_durable_recovery_script_still_uses_module_owned_repair_keys(self):
        root=Path(__file__).resolve().parents[1]
        script=(root/"scripts/twinpanel_recent_account_recovery_v1.py").read_text()
        self.assertIn("recovery.MODERN_PROTOCOL_KEYS",script)
        self.assertIn("recovery.reconcile_subscription_modern_accounts",script)
        self.assertIn("MigrationImportRecord.subscription_id.is_(None)",script)
        self.assertIn("Subscription.status==SubscriptionStatus.ACTIVE",script)
        self.assertIn("RECOVERY_SAFETY_STOP",script)


class XrayRecoveryIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_empty_vless_credential_retries_only_vless_with_stable_uuid(self):
        sub=SimpleNamespace(id=3874,user_id=120,
                            account_username="msabt123874")
        db=MagicMock()
        db.get.return_value=SimpleNamespace(id=120)
        nodes=[SimpleNamespace(id=19,enable_v2ray=True)]
        stable=str(uuid.uuid4())
        with (patch("app.v2ray_provision_idempotency_v1._existing_v2ray_uuid",
                    return_value=""),
              patch("app.v2ray_provision_idempotency_v1._deterministic_v2ray_uuid",
                    return_value=stable),
              patch.object(accounts,"_provision_classic_protocol",
                           new_callable=AsyncMock,return_value=([],[])) as provision):
            items,errors=await recovery._provision_missing_v2ray(
                object(),db,sub,nodes,
            )
        self.assertEqual((items,errors),([],[]))
        provision.assert_awaited_once()
        args=provision.await_args.args
        self.assertEqual(args[4],"v2ray")
        self.assertEqual(args[-1],stable)
        self.assertEqual(args[-2],"")
        self.assertEqual(args[5],nodes)

    async def test_recovery_prefers_original_uuid_when_present(self):
        sub=SimpleNamespace(id=3874,user_id=120,
                            account_username="msabt123874")
        db=MagicMock()
        db.get.return_value=SimpleNamespace(id=120)
        old_uuid="b75a06e6-a060-49c5-9d03-6a4b96ba8704"
        with (patch("app.v2ray_provision_idempotency_v1._existing_v2ray_uuid",
                    return_value=old_uuid),
              patch("app.v2ray_provision_idempotency_v1._deterministic_v2ray_uuid") as generate,
              patch.object(accounts,"_provision_classic_protocol",
                           new_callable=AsyncMock,return_value=([],[])) as provision):
            await recovery._provision_missing_v2ray(object(),db,sub,[])
        self.assertEqual(provision.await_args.args[-1],old_uuid)
        generate.assert_not_called()


if __name__=="__main__":
    unittest.main()
