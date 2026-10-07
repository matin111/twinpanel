import base64
import hashlib
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, x25519
from cryptography.x509.oid import (
    NameOID,
    ExtendedKeyUsageOID,
)
from sqlalchemy.orm import Session

from .mother_access import (
    decrypt_setting_value,
    encrypt_setting_value,
    get_value,
    set_value,
    get_bool,
    set_bool,
)


CISCO_CERT_KEY = "vpn.identity.cisco.cert_encrypted"
CISCO_PRIVATE_KEY = "vpn.identity.cisco.private_key_encrypted"

OPENVPN_CA_CERT_KEY = "vpn.identity.openvpn.ca_cert_encrypted"
OPENVPN_CA_PRIVATE_KEY = "vpn.identity.openvpn.ca_private_key_encrypted"

WIREGUARD_PRIVATE_KEY = "vpn.identity.wireguard.private_key_encrypted"

OPENVPN_CENTRAL_PKI_ENABLED_KEY = (
    "vpn.openvpn.central_pki_enabled"
)


def is_openvpn_central_pki_enabled(
    db: Session,
) -> bool:
    """
    Migration safety switch.

    False = OpenVPN فعلی بدون هیچ تغییری کار می‌کند.
    True  = Central PKI مجاز به استفاده است.
    """
    return get_bool(
        db,
        OPENVPN_CENTRAL_PKI_ENABLED_KEY,
        False,
    )


def set_openvpn_central_pki_enabled(
    db: Session,
    enabled: bool,
) -> None:
    set_bool(
        db,
        OPENVPN_CENTRAL_PKI_ENABLED_KEY,
        bool(enabled),
    )
    db.commit()


def _get_secret(
    db: Session,
    key: str,
) -> str:
    encrypted = get_value(
        db,
        key,
        "",
    )

    if not encrypted:
        return ""

    return decrypt_setting_value(
        encrypted
    )


def _set_secret(
    db: Session,
    key: str,
    value: str,
) -> None:
    value = str(
        value or ""
    ).strip()

    if not value:
        raise ValueError(
            f"Identity value cannot be empty: {key}"
        )

    set_value(
        db,
        key,
        encrypt_setting_value(value),
    )


def _rsa_private_pem(
    key,
) -> str:
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


def _certificate_pem(
    cert: x509.Certificate,
) -> str:
    return cert.public_bytes(
        serialization.Encoding.PEM
    ).decode()


def _generate_self_signed_certificate(
    common_name: str,
    *,
    is_ca: bool,
) -> tuple[str, str]:

    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=3072,
    )

    subject = x509.Name([
        x509.NameAttribute(
            NameOID.COMMON_NAME,
            common_name,
        )
    ])

    now = datetime.now(
        timezone.utc
    )

    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(
            private_key.public_key()
        )
        .serial_number(
            x509.random_serial_number()
        )
        .not_valid_before(
            now - timedelta(days=1)
        )
        .not_valid_after(
            now + timedelta(days=3650)
        )
        .add_extension(
            x509.BasicConstraints(
                ca=is_ca,
                path_length=None,
            ),
            critical=True,
        )
    )

    if is_ca:
        builder = builder.add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )

    certificate = builder.sign(
        private_key=private_key,
        algorithm=hashes.SHA256(),
    )

    return (
        _certificate_pem(
            certificate
        ),
        _rsa_private_pem(
            private_key
        ),
    )


def set_cisco_identity(
    db: Session,
    certificate: str,
    private_key: str,
) -> dict[str, str]:

    cert_text = str(
        certificate or ""
    ).strip()

    key_text = str(
        private_key or ""
    ).strip()

    if not cert_text or not key_text:
        raise ValueError(
            "Cisco certificate/private key cannot be empty"
        )

    cert_obj = (
        x509.load_pem_x509_certificate(
            cert_text.encode()
        )
    )

    key_obj = (
        serialization.load_pem_private_key(
            key_text.encode(),
            password=None,
        )
    )

    cert_public = (
        cert_obj.public_key()
        .public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    key_public = (
        key_obj.public_key()
        .public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    if cert_public != key_public:
        raise ValueError(
            "Cisco private key does not match certificate"
        )

    _set_secret(
        db,
        CISCO_CERT_KEY,
        cert_text,
    )

    _set_secret(
        db,
        CISCO_PRIVATE_KEY,
        key_text,
    )

    db.commit()

    return {
        "certificate": cert_text,
        "private_key": key_text,
    }


def get_or_create_cisco_identity(
    db: Session,
) -> dict[str, str]:

    cert = _get_secret(
        db,
        CISCO_CERT_KEY,
    )

    private_key = _get_secret(
        db,
        CISCO_PRIVATE_KEY,
    )

    if cert and private_key:
        return {
            "certificate": cert,
            "private_key": private_key,
        }

    cert, private_key = (
        _generate_self_signed_certificate(
            "TwinPanel VPN",
            is_ca=False,
        )
    )

    _set_secret(
        db,
        CISCO_CERT_KEY,
        cert,
    )

    _set_secret(
        db,
        CISCO_PRIVATE_KEY,
        private_key,
    )

    db.commit()

    return {
        "certificate": cert,
        "private_key": private_key,
    }


def get_or_create_openvpn_ca(
    db: Session,
) -> dict[str, str]:

    cert = _get_secret(
        db,
        OPENVPN_CA_CERT_KEY,
    )

    private_key = _get_secret(
        db,
        OPENVPN_CA_PRIVATE_KEY,
    )

    if cert and private_key:
        return {
            "ca_certificate": cert,
            "ca_private_key": private_key,
        }

    cert, private_key = (
        _generate_self_signed_certificate(
            "TwinPanel OpenVPN CA",
            is_ca=True,
        )
    )

    _set_secret(
        db,
        OPENVPN_CA_CERT_KEY,
        cert,
    )

    _set_secret(
        db,
        OPENVPN_CA_PRIVATE_KEY,
        private_key,
    )

    db.commit()

    return {
        "ca_certificate": cert,
        "ca_private_key": private_key,
    }


def set_openvpn_ca_identity(
    db: Session,
    ca_certificate: str,
    ca_private_key: str,
) -> dict[str, str]:
    """
    یک CA موجود را بعد از اعتبارسنجی به‌عنوان
    Central OpenVPN CA ذخیره می‌کند.
    """

    cert_text = str(
        ca_certificate or ""
    ).strip()

    key_text = str(
        ca_private_key or ""
    ).strip()

    if not cert_text or not key_text:
        raise ValueError(
            "OpenVPN CA certificate/key cannot be empty"
        )

    cert = x509.load_pem_x509_certificate(
        cert_text.encode()
    )

    private_key = (
        serialization.load_pem_private_key(
            key_text.encode(),
            password=None,
        )
    )

    cert_public = (
        cert.public_key()
        .public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    key_public = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    if cert_public != key_public:
        raise ValueError(
            "OpenVPN CA private key does not match certificate"
        )

    constraints = (
        cert.extensions
        .get_extension_for_class(
            x509.BasicConstraints
        )
        .value
    )

    if not constraints.ca:
        raise ValueError(
            "Certificate is not a CA certificate"
        )

    _set_secret(
        db,
        OPENVPN_CA_CERT_KEY,
        cert_text,
    )

    _set_secret(
        db,
        OPENVPN_CA_PRIVATE_KEY,
        key_text,
    )

    db.commit()

    return {
        "ca_certificate": cert_text,
        "ca_private_key": key_text,
    }


def _openvpn_server_setting_keys(
    node_id: int,
) -> tuple[str, str]:

    node_id = int(node_id)

    if node_id <= 0:
        raise ValueError(
            "Invalid OpenVPN node id"
        )

    base = (
        "vpn.identity.openvpn."
        f"server.{node_id}"
    )

    return (
        base + ".cert_encrypted",
        base + ".private_key_encrypted",
    )


def _load_private_key(
    value: str,
):
    return serialization.load_pem_private_key(
        value.encode(),
        password=None,
    )


def _issue_openvpn_server_certificate(
    ca_certificate: str,
    ca_private_key: str,
    node_id: int,
) -> tuple[str, str]:

    ca_cert = (
        x509.load_pem_x509_certificate(
            ca_certificate.encode()
        )
    )

    ca_key = _load_private_key(
        ca_private_key
    )

    server_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=3072,
    )

    subject = x509.Name([
        x509.NameAttribute(
            NameOID.COMMON_NAME,
            f"TwinPanel OpenVPN Server {int(node_id)}",
        )
    ])

    now = datetime.now(
        timezone.utc
    )

    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(
            ca_cert.subject
        )
        .public_key(
            server_key.public_key()
        )
        .serial_number(
            x509.random_serial_number()
        )
        .not_valid_before(
            now - timedelta(days=1)
        )
        .not_valid_after(
            now + timedelta(days=825)
        )
        .add_extension(
            x509.BasicConstraints(
                ca=False,
                path_length=None,
            ),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([
                ExtendedKeyUsageOID.SERVER_AUTH,
            ]),
            critical=False,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(
                server_key.public_key()
            ),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(
                ca_key.public_key()
            ),
            critical=False,
        )
        .sign(
            private_key=ca_key,
            algorithm=hashes.SHA256(),
        )
    )

    return (
        _certificate_pem(
            certificate
        ),
        _rsa_private_pem(
            server_key
        ),
    )


def get_or_create_openvpn_server_identity(
    db: Session,
    node_id: int,
) -> dict[str, str]:

    cert_key, private_key_key = (
        _openvpn_server_setting_keys(
            node_id
        )
    )

    certificate = _get_secret(
        db,
        cert_key,
    )

    private_key = _get_secret(
        db,
        private_key_key,
    )

    ca = get_or_create_openvpn_ca(
        db
    )

    valid_existing = False

    if certificate and private_key:
        try:
            cert_obj = (
                x509.load_pem_x509_certificate(
                    certificate.encode()
                )
            )

            ca_obj = (
                x509.load_pem_x509_certificate(
                    ca["ca_certificate"].encode()
                )
            )

            cn_rows = (
                cert_obj.subject
                .get_attributes_for_oid(
                    NameOID.COMMON_NAME
                )
            )

            expected_cn = (
                f"TwinPanel OpenVPN Server "
                f"{int(node_id)}"
            )

            eku = (
                cert_obj.extensions
                .get_extension_for_class(
                    x509.ExtendedKeyUsage
                )
                .value
            )

            valid_existing = (
                cert_obj.issuer
                == ca_obj.subject
                and bool(cn_rows)
                and cn_rows[0].value
                == expected_cn
                and ExtendedKeyUsageOID.SERVER_AUTH
                in eku
                and _certificate_matches_private_key(
                    certificate,
                    private_key,
                )
            )

        except Exception:
            valid_existing = False

    if valid_existing:
        return {
            "ca_certificate":
                ca["ca_certificate"],
            "server_certificate":
                certificate,
            "server_private_key":
                private_key,
        }

    certificate, private_key = (
        _issue_openvpn_server_certificate(
            ca["ca_certificate"],
            ca["ca_private_key"],
            node_id,
        )
    )

    _set_secret(
        db,
        cert_key,
        certificate,
    )

    _set_secret(
        db,
        private_key_key,
        private_key,
    )

    db.commit()

    return {
        "ca_certificate":
            ca["ca_certificate"],
        "server_certificate":
            certificate,
        "server_private_key":
            private_key,
    }


def issue_openvpn_client_identity(
    db: Session,
    common_name: str,
) -> dict[str, str]:
    """
    یک Client Certificate جدید با CA مرکزی OpenVPN صادر می‌کند.

    این تابع خودش چیزی ذخیره نمی‌کند.
    Persist کردن Identity کاربر در مرحله Account Delivery
    انجام خواهد شد.
    """

    common_name = str(
        common_name or ""
    ).strip()

    if not common_name:
        raise ValueError(
            "OpenVPN client common name cannot be empty"
        )

    if len(common_name) > 120:
        raise ValueError(
            "OpenVPN client common name is too long"
        )

    ca = get_or_create_openvpn_ca(
        db
    )

    ca_cert = (
        x509.load_pem_x509_certificate(
            ca["ca_certificate"].encode()
        )
    )

    ca_key = _load_private_key(
        ca["ca_private_key"]
    )

    client_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=3072,
    )

    subject = x509.Name([
        x509.NameAttribute(
            NameOID.COMMON_NAME,
            common_name,
        )
    ])

    now = datetime.now(
        timezone.utc
    )

    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(
            ca_cert.subject
        )
        .public_key(
            client_key.public_key()
        )
        .serial_number(
            x509.random_serial_number()
        )
        .not_valid_before(
            now - timedelta(days=1)
        )
        .not_valid_after(
            now + timedelta(days=825)
        )
        .add_extension(
            x509.BasicConstraints(
                ca=False,
                path_length=None,
            ),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=None,
                decipher_only=None,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([
                ExtendedKeyUsageOID.CLIENT_AUTH,
            ]),
            critical=False,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(
                client_key.public_key()
            ),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(
                ca_key.public_key()
            ),
            critical=False,
        )
        .sign(
            private_key=ca_key,
            algorithm=hashes.SHA256(),
        )
    )

    return {
        "ca_certificate": (
            ca["ca_certificate"]
        ),
        "client_certificate": (
            _certificate_pem(
                certificate
            )
        ),
        "client_private_key": (
            _rsa_private_pem(
                client_key
            )
        ),
        "common_name": common_name,
    }


def _openvpn_client_setting_keys(
    subscription_id: int,
) -> tuple[str, str]:

    subscription_id = int(
        subscription_id
    )

    if subscription_id <= 0:
        raise ValueError(
            "Invalid OpenVPN subscription id"
        )

    base = (
        "vpn.identity.openvpn."
        f"client.subscription.{subscription_id}"
    )

    return (
        base + ".cert_encrypted",
        base + ".private_key_encrypted",
    )


def _certificate_matches_private_key(
    certificate_pem: str,
    private_key_pem: str,
) -> bool:

    try:
        certificate = (
            x509.load_pem_x509_certificate(
                certificate_pem.encode()
            )
        )

        private_key = (
            _load_private_key(
                private_key_pem
            )
        )

        cert_public = (
            certificate.public_key()
            .public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )

        key_public = (
            private_key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
        )

        return cert_public == key_public

    except Exception:
        return False


def get_or_create_openvpn_client_identity(
    db: Session,
    subscription_id: int,
) -> dict[str, str]:
    """
    یک Identity پایدار برای هر Subscription.

    Certificate/Private Key فقط یک بار صادر می‌شوند
    و در Control Plane به‌صورت رمزنگاری‌شده نگهداری می‌شوند.
    """

    subscription_id = int(
        subscription_id
    )

    cert_key, private_key_key = (
        _openvpn_client_setting_keys(
            subscription_id
        )
    )

    certificate = _get_secret(
        db,
        cert_key,
    )

    private_key = _get_secret(
        db,
        private_key_key,
    )

    common_name = (
        f"mv-sub-{subscription_id}"
    )

    ca = get_or_create_openvpn_ca(
        db
    )

    valid_existing = False

    if certificate and private_key:
        try:
            cert_obj = (
                x509.load_pem_x509_certificate(
                    certificate.encode()
                )
            )

            ca_obj = (
                x509.load_pem_x509_certificate(
                    ca["ca_certificate"].encode()
                )
            )

            cn_rows = (
                cert_obj.subject
                .get_attributes_for_oid(
                    NameOID.COMMON_NAME
                )
            )

            cert_cn = (
                cn_rows[0].value
                if cn_rows
                else ""
            )

            valid_existing = (
                cert_obj.issuer
                == ca_obj.subject
                and cert_cn
                == common_name
                and _certificate_matches_private_key(
                    certificate,
                    private_key,
                )
            )

        except Exception:
            valid_existing = False

    if valid_existing:
        return {
            "ca_certificate": (
                ca["ca_certificate"]
            ),
            "client_certificate": certificate,
            "client_private_key": private_key,
            "common_name": common_name,
        }

    identity = (
        issue_openvpn_client_identity(
            db,
            common_name,
        )
    )

    _set_secret(
        db,
        cert_key,
        identity[
            "client_certificate"
        ],
    )

    _set_secret(
        db,
        private_key_key,
        identity[
            "client_private_key"
        ],
    )

    db.commit()

    return identity


def _generate_wireguard_private_key() -> str:
    raw = bytearray(
        __import__("secrets").token_bytes(32)
    )

    raw[0] &= 248
    raw[31] &= 127
    raw[31] |= 64

    return base64.b64encode(
        bytes(raw)
    ).decode()


def wireguard_public_key(
    private_key: str,
) -> str:

    raw = base64.b64decode(
        private_key
    )

    if len(raw) != 32:
        raise ValueError(
            "Invalid WireGuard private key"
        )

    private = (
        x25519.X25519PrivateKey
        .from_private_bytes(raw)
    )

    public = (
        private.public_key()
        .public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )

    return base64.b64encode(
        public
    ).decode()


def set_wireguard_identity(
    db: Session,
    private_key: str,
) -> dict[str, str]:

    key_text = str(
        private_key or ""
    ).strip()

    if not key_text:
        raise ValueError(
            "WireGuard private key cannot be empty"
        )

    try:
        raw = base64.b64decode(
            key_text,
            validate=True,
        )
    except Exception as exc:
        raise ValueError(
            "Invalid WireGuard private key encoding"
        ) from exc

    if len(raw) != 32:
        raise ValueError(
            "Invalid WireGuard private key length"
        )

    public_key = wireguard_public_key(
        key_text
    )

    _set_secret(
        db,
        WIREGUARD_PRIVATE_KEY,
        key_text,
    )

    db.commit()

    return {
        "private_key": key_text,
        "public_key": public_key,
    }


def get_or_create_wireguard_identity(
    db: Session,
) -> dict[str, str]:

    private_key = _get_secret(
        db,
        WIREGUARD_PRIVATE_KEY,
    )

    if not private_key:
        private_key = (
            _generate_wireguard_private_key()
        )

        _set_secret(
            db,
            WIREGUARD_PRIVATE_KEY,
            private_key,
        )

        db.commit()

    return {
        "private_key": private_key,
        "public_key": wireguard_public_key(
            private_key
        ),
    }


def identity_fingerprint(
    value: str,
) -> str:
    """
    Stable fingerprint.

    For X.509 PEM certificates, fingerprint the actual
    certificate DER bytes instead of PEM text formatting.
    For other values, normalize surrounding whitespace.
    """

    raw = str(value or "").strip()

    if not raw:
        return ""

    if "BEGIN CERTIFICATE" in raw:
        cert = x509.load_pem_x509_certificate(
            raw.encode()
        )

        return cert.fingerprint(
            hashes.SHA256()
        ).hex()[:16]

    return hashlib.sha256(
        raw.encode()
    ).hexdigest()[:16]
