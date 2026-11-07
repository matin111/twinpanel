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
        store = {}
        def read(_,protocol,sid,node_id):
            return store.get((protocol,sid,node_id))
        def persist(_,protocol,sid,node_id,data):
            lookup=(protocol,sid,node_id)
            if lookup in store and store[lookup]!=data:
                raise RuntimeError("CENTRAL_NODE_IDENTITY_ROTATION_BLOCKED")
            store[lookup]=dict(data)
            return data
        with (patch.object(bulk, "new_keypair", return_value=pair) as create,
              patch.object(bulk, "load_node_identity", side_effect=read),
              patch.object(bulk, "store_node_identity",side_effect=persist)):
            first=bulk.prepare_persistent_identities(
                db,14,[SimpleNamespace(id=17)])
            second=bulk.prepare_persistent_identities(
                db,14,[SimpleNamespace(id=17)])
        self.assertEqual(first,second)
        self.assertEqual(create.call_count,1)
        self.assertEqual(db.commit.call_count,2)
        self.assertEqual(cred.secret_encrypted,None)
        self.assertEqual(store[("wireguard",17,14)],
                         {"private":pair[0],"public":pair[1]})

    def test_other_secret_fields_are_retained(self):
        original=json.dumps({"legacy":"preserve"})
        db,cred=self.make_db(original)
        with (patch.object(bulk,"new_keypair",return_value=("a","b")),
              patch.object(bulk,"load_node_identity",return_value=None),
              patch.object(bulk,"store_node_identity",return_value=None),
              patch.object(bulk.ad,"_dec",side_effect=json.loads)):
            bulk.prepare_persistent_identities(db,14,[SimpleNamespace(id=17)])
        self.assertEqual(cred.secret_encrypted,original)

    def test_unreadable_legacy_secret_does_not_block_new_node_identity(self):
        db,cred=self.make_db("legacy-unreadable-ciphertext")
        with (patch.object(bulk,"new_keypair",return_value=("private","public")),
              patch.object(bulk.ad,"_dec",return_value=None),
              patch.object(bulk,"load_node_identity",return_value=None),
              patch.object(bulk,"store_node_identity",return_value=None)):
            created=bulk.prepare_persistent_identities(
                db,14,[SimpleNamespace(id=17)])
        self.assertEqual(created[17],("private","public"))
        self.assertEqual(cred.secret_encrypted,"legacy-unreadable-ciphertext")

    def test_invalid_existing_new_node_identity_never_rotates(self):
        db,cred=self.make_db("opaque")
        with (patch.object(bulk.ad,"_dec",return_value=None),
              patch.object(bulk,"load_node_identity",
                           return_value={"private":None,"public":"public"}),
              patch.object(bulk,"new_keypair") as creator):
            with self.assertRaisesRegex(RuntimeError,"KEYPAIR_INVALID"):
                bulk.prepare_persistent_identities(
                    db,14,[SimpleNamespace(id=17)])
            creator.assert_not_called()


if __name__ == "__main__":
    unittest.main()
