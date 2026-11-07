"""Prove the new Sudoku runtime is ONE daemon with independent user keys."""
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from app.central_sudoku_shared_runtime_v2 import (
    SHARED_PORT, SHARED_SERVICE, user_hash, users_manifest, remote_source,
)
from app.services.central_sudoku_shared_bootstrap_v2 import (
    BINARY_SHA256, TARGET, _check_binary,
)
from scripts import twinpanel_central_sudoku_shared_v2 as adapter


class SharedSudokuTests(unittest.TestCase):
    def test_user_hash_matches_official_handshake_spec(self):
        key = "01" * 64
        self.assertEqual(
            user_hash(key),
            hashlib.sha256(bytes.fromhex(key)).digest()[:8].hex(),
        )

    def test_manifest_is_all_users_in_one_shared_server(self):
        keys = ["01" * 64, "02" * 64, "03" * 64]
        users = users_manifest([
            {"subscription_id": 3, "client_key": keys[2]},
            {"subscription_id": 1, "client_key": keys[0]},
            {"subscription_id": 2, "client_key": keys[1]},
        ])
        self.assertEqual([u["alias"] for u in users],
                         ["tp-sub-1", "tp-sub-2", "tp-sub-3"])
        self.assertEqual(len(set(u["key"] for u in users)), 3)
        self.assertTrue(all(len(u["key"]) == 16 for u in users))

    def test_duplicate_client_keys_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_USER_HASH"):
            users_manifest([
                {"subscription_id": 1, "client_key": "ab" * 64},
                {"subscription_id": 2, "client_key": "ab" * 64},
            ])
        with self.assertRaisesRegex(ValueError, "DUPLICATE_ID"):
            users_manifest([
                {"subscription_id": 1, "client_key": "ab" * 64},
                {"subscription_id": 1, "client_key": "cd" * 64},
            ])

    def test_remote_script_compiles_and_creates_no_per_user_services(self):
        source = remote_source()
        compile(source, "<shared-sudoku-node>", "exec")
        self.assertIn('SERVICE="twinpanel-sudoku-shared.service"', source)
        self.assertIn('"users":clean', source)
        self.assertIn('"key":master["public"]', source)
        self.assertIn('["systemctl","restart",SERVICE]', source)
        self.assertIn('if previous==new', source)
        self.assertNotIn("twinpanel-sudoku-sub-", source)
        self.assertNotIn("systemctl enable --now",source)

    def test_node_specific_client_identity_and_same_port(self):
        from types import SimpleNamespace
        node = SimpleNamespace(id=14, name="Test Exit",
                               public_ip="203.0.113.9",public_domain=None)
        result=adapter.client_item(node,3,"ab"*64)
        self.assertEqual(result["port"],SHARED_PORT)
        self.assertEqual(result["node_id"],14)
        doc=json.loads(result["config"])
        self.assertEqual(doc["server_address"],"203.0.113.9:18553")
        self.assertEqual(doc["key"],"ab"*64)

    def test_saved_node_identity_is_separate_from_legacy_account_secret(self):
        from app.standalone_subscription_accounts import StandaloneAccountSecret,secret_to_dict
        secret=secret_to_dict(StandaloneAccountSecret(
            protocol="sudoku",subscription_id=31,username="tp-sub-31",
            sudoku_client_key="old",sudoku_port=30030,
        ))
        secret["central_shared_sudoku_nodes"]={
            "14":{"client_key":"01"*64,"master_public":"ab"*32,"port":18553}
        }
        self.assertEqual(adapter.node_identity(secret,14)["port"],18553)
        self.assertIsNone(adapter.node_identity(secret,15))
        self.assertEqual(secret["sudoku_client_key"],"old")
        self.assertEqual(secret["sudoku_port"],30030)

    def test_invalid_unpinned_binary_must_never_be_uploaded(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"fake"
            path.write_bytes(b"not official sudoku binary")
            with self.assertRaisesRegex(RuntimeError,"PINNED_BINARY_MISMATCH"):
                _check_binary(path)
        self.assertEqual(TARGET,"/usr/local/bin/twinpanel-sudoku-shared")
        self.assertEqual(len(BINARY_SHA256),64)


if __name__=="__main__":
    unittest.main()
