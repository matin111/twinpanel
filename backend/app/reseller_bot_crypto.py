import os
from pathlib import Path

from cryptography.fernet import Fernet


KEY_FILE = "/etc/twinpanel-reseller-bot.key"


def _key_path() -> Path:
    return Path(KEY_FILE)


def _read_key(path: Path) -> bytes:
    try:
        key = path.read_bytes().strip()
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Reseller bot encryption key is missing: {path}"
        ) from exc

    if not key:
        raise RuntimeError(
            f"Reseller bot encryption key is empty: {path}"
        )

    try:
        Fernet(key)
    except Exception as exc:
        raise RuntimeError(
            f"Reseller bot encryption key is invalid: {path}"
        ) from exc

    return key


def _create_key_if_missing(path: Path) -> bytes:
    """Create the persistent reseller-bot key exactly once.

    The first token save on older/migrated installs may happen before the
    optional reseller-bot supervisor installer has created the key.  Create it
    atomically here, but never replace an existing/empty/invalid key: replacing
    an existing key would make already encrypted bot tokens unrecoverable.
    """

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    key = Fernet.generate_key()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL

    try:
        fd = os.open(
            path,
            flags,
            0o600,
        )
    except FileExistsError:
        return _read_key(path)
    except OSError as exc:
        raise RuntimeError(
            f"Unable to create reseller bot encryption key: {path}"
        ) from exc

    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(key + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        try:
            path.unlink(missing_ok=True)
        finally:
            raise

    os.chmod(path, 0o600)
    return key


def _fernet(*, create_if_missing: bool = False) -> Fernet:
    path = _key_path()

    try:
        key = _read_key(path)
    except RuntimeError as exc:
        if (
            create_if_missing
            and not path.exists()
        ):
            key = _create_key_if_missing(path)
        else:
            raise exc

    return Fernet(key)


def encrypt_bot_token(
    token: str,
) -> str:
    value = token.strip()

    if not value:
        raise ValueError(
            "Telegram bot token is empty"
        )

    return (
        _fernet(create_if_missing=True)
        .encrypt(
            value.encode("utf-8")
        )
        .decode("utf-8")
    )


def decrypt_bot_token(
    encrypted: str,
) -> str:
    # Never auto-create a replacement key while decrypting.  If a key that
    # protected existing tokens is lost, fail closed instead of silently
    # rotating it and making historical ciphertext permanently unreadable.
    return (
        _fernet(create_if_missing=False)
        .decrypt(
            encrypted.encode("utf-8")
        )
        .decode("utf-8")
    )
