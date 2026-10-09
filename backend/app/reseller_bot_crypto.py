from cryptography.fernet import Fernet


KEY_FILE = "/etc/twinpanel-reseller-bot.key"


def _fernet() -> Fernet:
    with open(
        KEY_FILE,
        "rb",
    ) as handle:
        key = handle.read().strip()

    if not key:
        raise RuntimeError(
            "Reseller bot encryption key is empty"
        )

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
        _fernet()
        .encrypt(
            value.encode("utf-8")
        )
        .decode("utf-8")
    )


def decrypt_bot_token(
    encrypted: str,
) -> str:
    return (
        _fernet()
        .decrypt(
            encrypted.encode("utf-8")
        )
        .decode("utf-8")
    )
