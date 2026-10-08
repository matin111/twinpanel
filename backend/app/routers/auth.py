from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..two_factor_models import UserTwoFactor
from ..schemas import EmailChangeIn, LoginIn, LoginOut, PasswordChangeIn, RegisterIn, TokenOut, UserOut
from ..security import create_access_token, create_two_factor_token, hash_password, verify_password

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut)
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=409, detail="این ایمیل قبلاً ثبت شده است")

    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return TokenOut(access_token=create_access_token(str(user.id)))


@router.post("/login", response_model=LoginOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="ایمیل یا رمز عبور اشتباه است")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="حساب کاربری غیرفعال است")

    two_factor = (
        db.query(UserTwoFactor)
        .filter(UserTwoFactor.user_id == user.id)
        .first()
    )

    if two_factor and two_factor.is_enabled:
        return LoginOut(
            requires_2fa=True,
            two_factor_token=create_two_factor_token(str(user.id)),
        )

    return LoginOut(
        access_token=create_access_token(str(user.id)),
        requires_2fa=False,
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


# TWINPANEL_CUSTOMER_EMAIL_CHANGE_V1
@router.patch("/me/email", response_model=UserOut)
def change_email(
    payload: EmailChangeIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(
        payload.current_password,
        user.password_hash,
    ):
        raise HTTPException(
            status_code=400,
            detail="رمز فعلی صحیح نیست",
        )

    new_email = payload.email.strip().lower()

    existing = (
        db.query(User)
        .filter(
            User.email == new_email,
            User.id != user.id,
        )
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="این ایمیل قبلاً ثبت شده است",
        )

    user.email = new_email
    db.commit()
    db.refresh(user)

    return user


@router.post("/change-password")
def change_password(
    payload: PasswordChangeIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="رمز فعلی صحیح نیست")

    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"ok": True, "message": "رمز عبور تغییر کرد"}
