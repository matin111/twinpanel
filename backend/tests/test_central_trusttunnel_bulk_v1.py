"""TrustTunnel central bulk contracts without live SSH or service restart."""
import unittest
from types import SimpleNamespace

from app.central_trusttunnel_bulk_runtime_v1 import remote_source, verify_accounts
from app.standalone_subscription_accounts import StandaloneAccountSecret
from scripts.twinpanel_central_trusttunnel_node_bulk_v1 import client_item, args


class TrustTunnelCentralTests(unittest.TestCase):
    def test_remote_compiles_and_restarts_once(self):
        source=remote_source()
        compile(source,"<trusttunnel-bulk-remote>","exec")
        self.assertIn('["systemctl","restart",SERVICE]',source)
        self.assertIn('"--format","deeplink"',source)
        self.assertNotIn("shell=True",source)

    def test_rejects_duplicate_and_invalid_accounts(self):
        row={"username":"tp-sub-55","password":"password-123456"}
        verify_accounts([row])
        with self.assertRaises(ValueError):
            verify_accounts([row,row])
        with self.assertRaises(ValueError):
            verify_accounts([{"username":"root","password":"password-123456"}])

    def test_client_item_requires_actual_tt_uri(self):
        node=SimpleNamespace(id=14,name="Exit",public_ip="203.0.113.12",public_domain="")
        secret=StandaloneAccountSecret(protocol="trusttunnel",subscription_id=55,
            username="tp-sub-55",password="password-123456")
        with self.assertRaisesRegex(RuntimeError,"DEEPLINK_UNVERIFIED"):
            client_item(node,secret,8443,"not a link")
        item=client_item(node,secret,8443,"tt://supplied-by-exporter")
        self.assertEqual(item["uri"],"tt://supplied-by-exporter")
        self.assertEqual(item["config_format"],"trusttunnel-deeplink")

    def test_explicit_confirmation_required(self):
        with self.assertRaises(SystemExit):
            args(["--node-id","14","--apply"])
        self.assertTrue(args(["--node-id","14","--apply",
            "--confirm-node-id","14"]).apply)


if __name__ == "__main__":
    unittest.main()
