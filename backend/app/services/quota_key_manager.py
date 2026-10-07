from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


KEY_PATH = Path(
    "/etc/vpnshop/quota-command-private.key"
)


def load_private_key():

    if KEY_PATH.exists():
        raw = KEY_PATH.read_bytes()

        if len(raw) == 32:
            return Ed25519PrivateKey.from_private_bytes(raw)

    KEY_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    key = Ed25519PrivateKey.generate()

    raw = key.private_bytes_raw()

    KEY_PATH.write_bytes(raw)

    KEY_PATH.chmod(0o600)

    return key
