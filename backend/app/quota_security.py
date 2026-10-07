import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from urllib.parse import unquote

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import Header, HTTPException
from sqlalchemy.orm import Session

from .quota_models import QuotaAgentIdentity


def advisory_key(namespace: str, value: str) -> int:
    digest = hashlib.blake2b(f"{namespace}:{value}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


def command_signer():
    from .services.quota_key_manager import load_private_key
    return load_private_key()


def sign_command(unsigned: dict) -> str:
    canonical = json.dumps(
        unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return base64.b64encode(command_signer().sign(canonical)).decode("ascii")


def public_key_b64() -> str:
    from cryptography.hazmat.primitives import serialization

    raw = command_signer().public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return base64.b64encode(raw).decode("ascii")



def proxy_shared_secret() -> str:
    path = os.environ.get(
        "TWINPANEL_MTLS_PROXY_SHARED_SECRET_FILE",
        "/etc/vpnshop/quota-mtls-proxy.secret",
    )

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as handle:
            value = handle.read().strip()

        if value:
            return value

    except OSError:
        pass

    return os.environ.get(
        "TWINPANEL_MTLS_PROXY_SHARED_SECRET",
        "",
    )


def require_node_identity(
    db: Session,
    node_id: int,
    proxy_auth: str | None,
    escaped_certificate: str | None,
) -> QuotaAgentIdentity:
    expected = proxy_shared_secret()
    if not expected or not proxy_auth or not hmac.compare_digest(proxy_auth, expected):
        raise HTTPException(status_code=403, detail="untrusted_mtls_proxy")
    try:
        certificate = x509.load_pem_x509_certificate(unquote(escaped_certificate or "").encode("ascii"))
        fingerprint = certificate.fingerprint(hashes.SHA256()).hex()
    except (ValueError, UnicodeEncodeError) as exc:
        raise HTTPException(status_code=403, detail="invalid_client_certificate") from exc

    identity = db.get(QuotaAgentIdentity, node_id)
    if (
        identity is None
        or not identity.is_active
        or not hmac.compare_digest(identity.certificate_fingerprint_sha256, fingerprint)
    ):
        raise HTTPException(status_code=403, detail="node_identity_rejected")
    if identity.certificate_not_after and identity.certificate_not_after <= datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(status_code=403, detail="node_certificate_expired")
    return identity
