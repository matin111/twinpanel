"""Fast controller-side OpenVPN signing without changing legacy credentials."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.services import central_openvpn_node_signer_v2 as signer


class CentralOpenVpnIdentityBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        now=datetime.now(timezone.utc)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,"isolated-test-ca")])
        cert=(x509.CertificateBuilder()
              .subject_name(name).issuer_name(name)
              .public_key(key.public_key())
              .serial_number(x509.random_serial_number())
              .not_valid_before(now-timedelta(hours=1))
              .not_valid_after(now+timedelta(days=14))
              .add_extension(x509.BasicConstraints(ca=True,path_length=None),critical=True)
              .sign(key,hashes.SHA256()))
        cls.ca_cert=cert.public_bytes(serialization.Encoding.PEM).decode()
        cls.ca_key=key.private_bytes(
            serialization.Encoding.PEM,serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption()).decode()

    def test_batch_preserves_exact_rsa_identity_contract_and_is_unique(self):
        ids=list(range(101,131))
        batch=signer.issue_client_identities_batch(
            self.ca_cert,self.ca_key,ids,16,max_workers=8)
        self.assertEqual(list(batch),ids)
        cert_serials=set()
        for sid,item in batch.items():
            self.assertEqual(item["common_name"],f"mv{sid}n16")
            self.assertEqual(item["ca"],self.ca_cert)
            signer.verify_client_identity(item,self.ca_cert,sid,16)
            key=serialization.load_pem_private_key(
                item["private_key"].encode(),password=None)
            self.assertIsInstance(key,rsa.RSAPrivateKey)
            cert=x509.load_pem_x509_certificate(item["certificate"].encode())
            cert_serials.add(cert.serial_number)
        self.assertEqual(len(cert_serials),len(ids))

    def test_ca_is_validated_once_for_large_batch(self):
        original=signer.validate_ca
        with patch.object(signer,"validate_ca",wraps=original) as checked:
            signer.issue_client_identities_batch(
                self.ca_cert,self.ca_key,[101,102,103,104],16)
            checked.assert_called_once_with(self.ca_cert,self.ca_key)

    def test_empty_batch_does_not_create_any_keys(self):
        with patch.object(signer,"validate_ca") as checked:
            self.assertEqual(signer.issue_client_identities_batch(
                "no-ca","no-key",[],16),{})
            checked.assert_not_called()

    def test_rejects_duplicate_or_invalid_subscriptions(self):
        for ids in ([123,123],[0,1],[-1,1],list(range(1,3002))):
            with self.assertRaises(ValueError):
                signer.issue_client_identities_batch(
                    self.ca_cert,self.ca_key,ids,16)
        with self.assertRaises(ValueError):
            signer.issue_client_identities_batch(
                self.ca_cert,self.ca_key,[123],16,max_workers=0)

    def test_existing_single_identity_still_verifies(self):
        old=signer.issue_client_identity(self.ca_cert,self.ca_key,123,16)
        self.assertEqual(
            signer.verify_client_identity(old,self.ca_cert,123,16),old,
        )


if __name__=="__main__":
    unittest.main()
