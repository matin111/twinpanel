"""Node-local OpenVPN CA import and centralized client certificate issuance.

Use the EXISTING CA trusted by a specific Exit's installed OpenVPN server.
Import its CA certificate/private key exactly once over saved SSH and encrypt
both in controller settings. Never enable global PKI on legacy nodes.
No per-user SSH, EasyRSA process or protocol restart is required.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from ..mother_access import (
    get_value, set_value, encrypt_setting_value, decrypt_setting_value,
)

def _keys(node_id:int):
    if int(node_id)<1:raise ValueError("INVALID_NODE_ID")
    prefix=f"vpn.identity.openvpn.exit.{int(node_id)}"
    return prefix+".ca_cert", prefix+".ca_private"


def validate_ca(cert_pem:str,key_pem:str):
    try:
        cert=x509.load_pem_x509_certificate(cert_pem.encode())
        key=serialization.load_pem_private_key(key_pem.encode(),password=None)
        ca=cert.extensions.get_extension_for_class(x509.BasicConstraints).value
        match=cert.public_key().public_numbers()==key.public_key().public_numbers()
    except (ValueError,TypeError,x509.ExtensionNotFound) as exc:
        raise RuntimeError("OPENVPN_NODE_CA_INVALID") from exc
    if not ca.ca or not match:
        raise RuntimeError("OPENVPN_NODE_CA_MISMATCH")
    if cert.not_valid_after_utc<=datetime.now(timezone.utc):
        raise RuntimeError("OPENVPN_NODE_CA_EXPIRED")
    return cert,key


async def load_or_import_node_ca(db,node,conn):
    ckey,pkey=_keys(node.id)
    old_cert=get_value(db,ckey,"")
    old_key=get_value(db,pkey,"")
    if bool(old_cert)!=bool(old_key):
        raise RuntimeError("OPENVPN_NODE_CA_PARTIAL_CONTROLLER_IDENTITY")
    if old_cert and old_key:
        cert=decrypt_setting_value(old_cert)
        key=decrypt_setting_value(old_key)
        if not cert or not key:
            raise RuntimeError("OPENVPN_NODE_CA_CANNOT_DECRYPT")
        validate_ca(cert,key)
        return {"cert":cert,"private":key,"imported":False}
    # Both files are the server's existing EasyRSA PKI. Verify the actual
    # OpenVPN server config refers to this CA before importing secrets.
    remote=r'''python3 - <<'PY_OVPN_CA'
from pathlib import Path
import json,shlex
server=Path("/etc/openvpn/server/twinpanel.conf")
cert=Path("/etc/openvpn/easy-rsa/pki/ca.crt")
private=Path("/etc/openvpn/easy-rsa/pki/private/ca.key")
if not server.is_file() or not cert.is_file() or not private.is_file():
    raise RuntimeError("OPENVPN_NODE_LOCAL_CA_MISSING")
line=[x.strip() for x in server.read_text().splitlines() if x.strip().startswith("ca ")]
if len(line)!=1 or shlex.split(line[0])[1]!=str(cert):
    raise RuntimeError("OPENVPN_NODE_CA_IS_NOT_SERVER_CA")
if private.stat().st_mode & 0o007:
    raise RuntimeError("OPENVPN_NODE_CA_PRIVATE_WORLD_ACCESSIBLE")
print(json.dumps({"cert":cert.read_text(),"private":private.read_text()}))
PY_OVPN_CA'''
    result=await asyncio.wait_for(conn.run(remote,check=False),timeout=25)
    if result.exit_status:
        raise RuntimeError("OPENVPN_NODE_CA_READ_FAILED")
    try:
        document=json.loads(result.stdout.strip().splitlines()[-1])
        cert=document["cert"]
        key=document["private"]
    except (ValueError,IndexError,KeyError,TypeError) as exc:
        raise RuntimeError("OPENVPN_NODE_CA_REMOTE_DOCUMENT_INVALID") from exc
    validate_ca(cert,key)
    set_value(db,ckey,encrypt_setting_value(cert))
    set_value(db,pkey,encrypt_setting_value(key))
    db.commit()
    return {"cert":cert,"private":key,"imported":True}


def issue_client_identity(ca_cert_pem:str,ca_key_pem:str,sub_id:int,node_id:int):
    if sub_id<=0 or node_id<=0:
        raise ValueError("OPENVPN_CLIENT_INVALID_SUBSCRIPTION_ID")
    cert,key=validate_ca(ca_cert_pem,ca_key_pem)
    client_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    subject=x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME,f"mv{sub_id}n{node_id}"),
    ])
    now=datetime.now(timezone.utc)
    signed=(
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(cert.subject)
        .public_key(client_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now-timedelta(hours=1))
        .not_valid_after(min(now+timedelta(days=825),cert.not_valid_after_utc))
        .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),critical=False)
        .add_extension(x509.KeyUsage(
            digital_signature=True,content_commitment=False,
            key_encipherment=True,data_encipherment=False,key_agreement=False,
            key_cert_sign=False,crl_sign=False,
            encipher_only=None,decipher_only=None,
        ),critical=True)
        .sign(key,hashes.SHA256())
    )
    return {
        "ca":ca_cert_pem,
        "certificate":signed.public_bytes(serialization.Encoding.PEM).decode(),
        "private_key":client_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ).decode(),
        "common_name":f"mv{sub_id}n{node_id}",
    }


def verify_client_identity(doc,ca_cert_pem,sub_id,node_id):
    if not isinstance(doc,dict):
        raise RuntimeError("OPENVPN_NODE_CLIENT_IDENTITY_MISSING")
    try:
        ca=x509.load_pem_x509_certificate(ca_cert_pem.encode())
        cert=x509.load_pem_x509_certificate(doc["certificate"].encode())
        key=serialization.load_pem_private_key(doc["private_key"].encode(),password=None)
        cn=cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        eku=cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        ca.public_key().verify(cert.signature,cert.tbs_certificate_bytes,
            padding.PKCS1v15(),cert.signature_hash_algorithm)
        if (cert.issuer!=ca.subject or cn!=f"mv{sub_id}n{node_id}"
            or ExtendedKeyUsageOID.CLIENT_AUTH not in eku
            or cert.public_key().public_numbers()!=key.public_key().public_numbers()):
            raise ValueError("identity mismatch")
    except Exception as exc:
        raise RuntimeError("OPENVPN_NODE_CLIENT_CERT_INVALID") from exc
    return doc
