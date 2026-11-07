"""No migrated user secret is destroyed by central Exit key staging."""
import json
import unittest
from unittest.mock import MagicMock,patch

from app.services import central_node_identity_store_v1 as store
from scripts import twinpanel_central_openvpn_node_bulk_v1 as openvpn


class IdentityStoreTests(unittest.TestCase):
    def test_stable_key_per_protocol_subscription_and_exit(self):
        self.assertNotEqual(store.key("wireguard",17,14),
                            store.key("wireguard",17,15))
        self.assertNotEqual(store.key("wireguard",17,14),
                            store.key("openvpn",17,14))

    def test_retry_reuses_identical_key_and_rejects_rotation(self):
        values={}
        with (
            patch.object(store,"get_value",
                         side_effect=lambda db,k,default="": values.get(k,default)),
            patch.object(store,"set_value",
                         side_effect=lambda db,k,v: values.__setitem__(k,v)),
            patch.object(store,"encrypt_setting_value",
                         side_effect=lambda raw:"encrypted:"+raw),
            patch.object(store,"decrypt_setting_value",
                         side_effect=lambda token:token[len("encrypted:"):]),
        ):
            db=MagicMock()
            key={"private":"first","public":"public"}
            store.store_once(db,"wireguard",17,14,key)
            self.assertEqual(store.load(db,"wireguard",17,14),key)
            store.store_once(db,"wireguard",17,14,key)
            self.assertEqual(len(values),1)
            with self.assertRaisesRegex(RuntimeError,"ROTATION_BLOCKED"):
                store.store_once(db,"wireguard",17,14,
                                 {"private":"other","public":"public"})

    def test_ciphertext_without_valid_key_fails_closed(self):
        with (patch.object(store,"get_value",return_value="encrypted"),
              patch.object(store,"decrypt_setting_value",return_value="")):
            with self.assertRaisesRegex(RuntimeError,"CANNOT_DECRYPT"):
                store.load(MagicMock(),"openvpn",22,14)

    def test_unreadable_imported_openvpn_secret_is_untouched(self):
        cred=MagicMock()
        cred.subscription_id=17
        cred.secret_encrypted="legacy-undecodable"
        with (patch.object(openvpn,"load_node_identity",return_value=None),
              patch.object(openvpn.ad,"_dec",return_value=None)):
            self.assertIsNone(
                openvpn.saved_node_identity(MagicMock(),cred,14,"ca"))
        self.assertEqual(cred.secret_encrypted,"legacy-undecodable")

    def test_old_readable_openvpn_identity_is_migrated_without_rewriting_secret(self):
        cred=MagicMock()
        cred.subscription_id=17
        cred.secret_encrypted="old-ciphertext"
        document={"central_local_openvpn_nodes":{"14":{"cert":"a","private":"b"}}}
        with (patch.object(openvpn,"load_node_identity",return_value=None),
              patch.object(openvpn.ad,"_dec",return_value=document),
              patch.object(openvpn,"verify_client_identity"),
              patch.object(openvpn,"store_node_identity") as save):
            result=openvpn.saved_node_identity(MagicMock(),cred,14,"ca")
        self.assertEqual(result,document["central_local_openvpn_nodes"]["14"])
        self.assertEqual(cred.secret_encrypted,"old-ciphertext")
        save.assert_called_once()


if __name__=="__main__":
    unittest.main()
