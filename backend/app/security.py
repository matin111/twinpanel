from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {"sub": subject, "purpose": "access", "exp": expire}
    return jwt.encode(payload, settings.app_secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=[ALGORITHM])

        # Reject temporary 2FA challenge tokens as API access tokens.
        if payload.get("purpose") == "2fa":
            return None

        return payload.get("sub")
    except JWTError:
        return None


# TWINPANEL_REAL_2FA_CHALLENGE_TOKEN_V1
def create_two_factor_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    payload = {
        "sub": subject,
        "purpose": "2fa",
        "exp": expire,
    }
    return jwt.encode(
        payload,
        settings.app_secret_key,
        algorithm=ALGORITHM,
    )


def decode_two_factor_token(token: str) -> str | None:
    try:
        payload = jwt.decode(
            token,
            settings.app_secret_key,
            algorithms=[ALGORITHM],
        )

        if payload.get("purpose") != "2fa":
            return None

        return payload.get("sub")

    except JWTError:
        return None
