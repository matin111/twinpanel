"""AmneziaWG bulk staging contract tests, without production services."""
from __future__ import annotations
import base64
import unittest
from types import SimpleNamespace

from app.central_amneziawg_bulk_runtime_v1 import (
    validate_peers,remote_source,
)
from scripts.twinpanel_central_amneziawg_node_bulk_v1 import (
    new_central_secret,client_item,args,
)


class AmneziaWGBulkTests(unittest.TestCase):
    def test_remote_script_compiles(self):
        program=remote_source()
        compile(program,"<amneziawg-central-remote>","exec")
        self.assertIn('["systemctl","restart",SERVICE]',program)
        self.assertIn("AWG_UNMANAGED_PEERS_PRESENT",program)

    def test_central_identity_and_client_config(self):
        secret=new_central_secret(78)
        self.assertEqual(secret.address,"10.254.0.79/32")
        self.assertEqual(len(base64.b64decode(secret.client_private_key)),32)
        validate_peers([{"username":secret.username,
                         "public_key":secret.client_public_key,
                         "address":secret.address}])
        node=SimpleNamespace(id=14,name="Hidden Exit",
                             public_ip="203.0.113.12",public_domain="")
        client=client_item(node,secret,35000,"server-public-key")
        self.assertIn("Jc = 6",client["config"])
        self.assertIn("Address = 10.254.0.79/32",client["config"])
        self.assertEqual(client["telemetry_identity"],secret.client_public_key)

    def test_invalid_duplicate_address_rejected(self):
        first=new_central_secret(12)
        second=new_central_secret(12+65533)
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):
            validate_peers([
                {"username":s.username,"public_key":s.client_public_key,
                 "address":s.address}
                for s in (first,second)
            ])

    def test_apply_requires_matching_node(self):
        with self.assertRaises(SystemExit):
            args(["--node-id","14","--apply"])
        self.assertTrue(args(["--node-id","14","--apply",
                              "--confirm-node-id","14"]).apply)


if __name__=="__main__":
    unittest.main()
