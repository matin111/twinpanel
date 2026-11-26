from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import User, UserRole
from .security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    subject = decode_access_token(token)
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = db.query(User).filter(User.id == int(subject)).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User unavailable")
    # FastAPI shares this Session with the endpoint. Release the auth-only
    # SELECT transaction now, before an async handler may await SSH/HTTP for
    # tens of seconds. expire_on_commit=False retains the loaded User fields.
    # Authentication has not executed any account/billing writes.
    db.commit()
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


def require_reseller(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from .models_reseller import Reseller

    reseller = (
        db.query(Reseller)
        .filter(
            Reseller.owner_user_id == user.id
        )
        .first()
    )

    if not reseller:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Reseller access required",
        )

    if not reseller.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="نمایندگی غیرفعال است",
        )

    # The reseller lookup is also read-only. Do not let the authentication
    # dependency pin a request-pool connection while the handler awaits I/O.
    db.commit()
    return reseller
