"""Durable central WireGuard identity regression tests."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from scripts import twinpanel_central_wireguard_node_bulk_v1 as bulk


class WireGuardStagedIdentityTests(unittest.TestCase):
    def make_db(self, stored=None):
        db = MagicMock()
        cred = SimpleNamespace(subscription_id=17, protocol="wireguard",
                               secret_encrypted=stored)
        db.query.return_value.filter.return_value.with_for_update.return_value.all.return_value = [cred]
        return db, cred

    def test_keypair_is_reused_after_remote_or_db_interruption(self):
        db, cred = self.make_db()
        pair = ("private-on-controller", "public-to-node")
        with (patch.object(bulk, "new_keypair", return_value=pair) as create,
              patch.object(bulk.ad, "_enc", side_effect=json.dumps),
              patch.object(bulk.ad, "_dec", side_effect=json.loads)):
            first = bulk.prepare_persistent_identities(
                db, 14, [SimpleNamespace(id=17)])
            second = bulk.prepare_persistent_identities(
                db, 14, [SimpleNamespace(id=17)])
        self.assertEqual(first, second)
        self.assertEqual(create.call_count, 1)
        self.assertEqual(db.commit.call_count, 2)
        self.assertEqual(
            json.loads(cred.secret_encrypted)[bulk.STAGED_SECRET_KEY]["14"],
            {"private": pair[0], "public": pair[1]},
        )

    def test_other_secret_fields_are_retained(self):
        db, cred = self.make_db(json.dumps({"legacy": "preserve"}))
        with (patch.object(bulk, "new_keypair", return_value=("a", "b")),
              patch.object(bulk.ad, "_enc", side_effect=json.dumps),
              patch.object(bulk.ad, "_dec", side_effect=json.loads)):
            bulk.prepare_persistent_identities(
                db, 14, [SimpleNamespace(id=17)])
        self.assertEqual(json.loads(cred.secret_encrypted)["legacy"], "preserve")

    def test_unreadable_secret_fails_without_remote_provisioning(self):
        db, _ = self.make_db("invalid")
        with patch.object(bulk.ad, "_dec", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "UNREADABLE"):
                bulk.prepare_persistent_identities(
                    db, 14, [SimpleNamespace(id=17)])
        db.commit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
