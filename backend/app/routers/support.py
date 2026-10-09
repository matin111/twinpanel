from datetime import datetime
from pathlib import Path
import hashlib
import hmac
import secrets

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Header,
)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import User
from ..support_models import SupportMessage, SupportTicket
from ..telegram_notify_service import queue_telegram_notification


router = APIRouter(
    prefix="/v1/support",
    tags=["support"],
)

admin_router = APIRouter(
    prefix="/v1/admin/support",
    tags=["support-admin"],
    dependencies=[Depends(require_admin)],
)


CATEGORIES = {
    "connection": "مشکل اتصال",
    "payment": "خرید و پرداخت",
    "subscription": "اشتراک",
    "sublink": "لینک اشتراک",
    "other": "سایر موارد",
}

VALID_STATUSES = {
    "open",
    "answered",
    "closed",
}


class TicketCreateIn(BaseModel):
    category: str = Field(
        min_length=2,
        max_length=40,
    )
    subject: str = Field(
        min_length=2,
        max_length=180,
    )
    message: str = Field(
        min_length=1,
        max_length=10000,
    )


# TWINPANEL_GUEST_CHAT_API_V1
class GuestTicketCreateIn(BaseModel):
    name: str = Field(
        min_length=2,
        max_length=120,
    )
    contact: str = Field(
        min_length=3,
        max_length=190,
    )
    message: str = Field(
        min_length=1,
        max_length=10000,
    )

    source: str | None = Field(
        default=None,
        max_length=20,
    )


class MessageIn(BaseModel):
    message: str | None = Field(
        default=None,
        max_length=10000,
    )
    attachment_type: str | None = Field(
        default=None,
        max_length=40,
    )
    attachment_ref: str | None = Field(
        default=None,
        max_length=4000,
    )

    source: str | None = Field(
        default=None,
        max_length=20,
    )



def _category(value: str) -> str:
    value = str(value or "").strip().lower()

    if value not in CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail="موضوع پشتیبانی نامعتبر است",
        )

    return value


# TWINPANEL_SUPPORT_MESSAGE_SOURCE_API_V1
def _message_source(payload) -> str:
    value = str(
        getattr(payload, "source", None)
        or "web"
    ).strip().lower()

    if value not in {
        "web",
        "telegram",
    }:
        return "web"

    return value


def _require_content(payload: MessageIn) -> None:
    message = (payload.message or "").strip()
    attachment = (payload.attachment_ref or "").strip()

    if not message and not attachment:
        raise HTTPException(
            status_code=422,
            detail="پیام یا پیوست الزامی است",
        )


def _ticket_or_404(
    db: Session,
    ticket_id: int,
) -> SupportTicket:
    row = db.get(SupportTicket, ticket_id)

    if not row:
        raise HTTPException(
            status_code=404,
            detail="تیکت پیدا نشد",
        )

    return row


def _user_ticket(
    db: Session,
    ticket_id: int,
    user: User,
) -> SupportTicket:
    row = _ticket_or_404(db, ticket_id)

    if row.user_id != user.id:
        raise HTTPException(
            status_code=404,
            detail="تیکت پیدا نشد",
        )

    return row


def _guest_token_hash(value: str) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def _guest_ticket(
    db: Session,
    ticket_id: int,
    token: str,
) -> SupportTicket:
    row = _ticket_or_404(db, ticket_id)

    if row.user_id is not None:
        raise HTTPException(
            status_code=404,
            detail="گفتگو پیدا نشد",
        )

    expected = str(
        row.guest_token_hash or ""
    )

    supplied = _guest_token_hash(
        str(token or "")
    )

    if (
        not expected
        or not hmac.compare_digest(
            expected,
            supplied,
        )
    ):
        raise HTTPException(
            status_code=404,
            detail="گفتگو پیدا نشد",
        )

    return row


def _message_out(row: SupportMessage) -> dict:
    return {
        "id": row.id,
        "ticket_id": row.ticket_id,
        "sender_user_id": row.sender_user_id,
        "sender_role": row.sender_role,
        "source": getattr(row, "source", "web"),
        "message": row.message,
        "attachment_type": row.attachment_type,
        "attachment_ref": row.attachment_ref,
        "created_at": row.created_at,
    }


def _ticket_out(
    db: Session,
    row: SupportTicket,
    include_messages: bool = False,
) -> dict:
    user = (
        db.get(User, row.user_id)
        if row.user_id is not None
        else None
    )

    result = {
        "id": row.id,
        "user_id": row.user_id,
        "user": {
            "email": user.email if user else None,
            "phone": user.phone if user else None,
            "full_name": user.full_name if user else None,
        },
        "guest": {
            "name": row.guest_name,
            "contact": row.guest_contact,
        } if row.user_id is None else None,
        "category": row.category,
        "category_title": CATEGORIES.get(
            row.category,
            row.category,
        ),
        "subject": row.subject,
        "status": row.status,
        "source": row.source,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "last_message_at": row.last_message_at,
        "closed_at": row.closed_at,
    }

    if include_messages:
        messages = (
            db.query(SupportMessage)
            .filter(
                SupportMessage.ticket_id == row.id
            )
            .order_by(
                SupportMessage.id.asc()
            )
            .all()
        )

        result["messages"] = [
            _message_out(item)
            for item in messages
        ]

    return result


@router.get("/categories")
def categories():
    return [
        {
            "id": key,
            "title": title,
        }
        for key, title in CATEGORIES.items()
    ]



@router.post("/guest/tickets")
def create_guest_ticket(
    payload: GuestTicketCreateIn,
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()

    guest_token = secrets.token_urlsafe(32)

    row = SupportTicket(
        user_id=None,
        guest_name=payload.name.strip(),
        guest_contact=payload.contact.strip(),
        guest_token_hash=_guest_token_hash(
            guest_token
        ),
        category="other",
        subject="گفتگوی فروشگاه",
        status="open",
        source="store_guest",
        created_at=now,
        updated_at=now,
        last_message_at=now,
    )

    db.add(row)
    db.flush()

    db.add(
        SupportMessage(
            ticket_id=row.id,
            sender_user_id=None,
            sender_role="guest",
            message=payload.message.strip(),
            created_at=now,
        )
    )

    db.commit()
    db.refresh(row)

    result = _ticket_out(
        db,
        row,
        include_messages=True,
    )

    result["guest_token"] = guest_token

    return result


@router.get("/guest/tickets/{ticket_id}")
def guest_ticket_detail(
    ticket_id: int,
    x_guest_chat_token: str = Header(
        alias="X-Guest-Chat-Token",
    ),
    db: Session = Depends(get_db),
):
    row = _guest_ticket(
        db,
        ticket_id,
        x_guest_chat_token,
    )

    return _ticket_out(
        db,
        row,
        include_messages=True,
    )


@router.post("/guest/tickets/{ticket_id}/messages")
def guest_send_message(
    ticket_id: int,
    payload: MessageIn,
    x_guest_chat_token: str = Header(
        alias="X-Guest-Chat-Token",
    ),
    db: Session = Depends(get_db),
):
    _require_content(payload)

    row = _guest_ticket(
        db,
        ticket_id,
        x_guest_chat_token,
    )

    if row.status == "closed":
        raise HTTPException(
            status_code=409,
            detail="این گفتگو بسته شده است",
        )

    now = datetime.utcnow()

    db.add(
        SupportMessage(
            ticket_id=row.id,
            sender_user_id=None,
            sender_role="guest",
            message=(
                payload.message.strip()
                if payload.message
                else None
            ),
            attachment_type=payload.attachment_type,
            attachment_ref=payload.attachment_ref,
            created_at=now,
        )
    )

    row.status = "open"
    row.updated_at = now
    row.last_message_at = now

    db.commit()
    db.refresh(row)

    return _ticket_out(
        db,
        row,
        include_messages=True,
    )


@router.post("/guest/tickets/{ticket_id}/close")
def guest_close_ticket(
    ticket_id: int,
    x_guest_chat_token: str = Header(
        alias="X-Guest-Chat-Token",
    ),
    db: Session = Depends(get_db),
):
    row = _guest_ticket(
        db,
        ticket_id,
        x_guest_chat_token,
    )

    now = datetime.utcnow()

    row.status = "closed"
    row.closed_at = now
    row.updated_at = now

    db.commit()
    db.refresh(row)

    return _ticket_out(db, row)


@router.post("/tickets")
def create_ticket(
    payload: TicketCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()

    row = SupportTicket(
        user_id=user.id,
        category=_category(payload.category),
        subject=payload.subject.strip(),
        status="open",
        source=_message_source(payload),
        created_at=now,
        updated_at=now,
        last_message_at=now,
    )

    db.add(row)
    db.flush()

    db.add(
        SupportMessage(
            ticket_id=row.id,
            sender_user_id=user.id,
            sender_role="user",
            source=_message_source(payload),
            message=payload.message.strip(),
            created_at=now,
        )
    )

    db.commit()
    db.refresh(row)

    return _ticket_out(
        db,
        row,
        include_messages=True,
    )


@router.get("/tickets/me")
def my_tickets(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(SupportTicket)
        .filter(
            SupportTicket.user_id == user.id
        )
        .order_by(
            SupportTicket.last_message_at.desc()
        )
        .all()
    )

    return [
        _ticket_out(db, row)
        for row in rows
    ]


@router.get("/tickets/{ticket_id}")
def ticket_detail(
    ticket_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _user_ticket(
        db,
        ticket_id,
        user,
    )

    return _ticket_out(
        db,
        row,
        include_messages=True,
    )


@router.post("/tickets/{ticket_id}/messages")
def send_message(
    ticket_id: int,
    payload: MessageIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_content(payload)

    row = _user_ticket(
        db,
        ticket_id,
        user,
    )

    if row.status == "closed":
        raise HTTPException(
            status_code=409,
            detail="این تیکت بسته شده است",
        )

    now = datetime.utcnow()

    db.add(
        SupportMessage(
            ticket_id=row.id,
            sender_user_id=user.id,
            sender_role="user",
            source=_message_source(payload),
            message=(
                payload.message.strip()
                if payload.message
                else None
            ),
            attachment_type=payload.attachment_type,
            attachment_ref=payload.attachment_ref,
            created_at=now,
        )
    )

    row.status = "open"
    row.updated_at = now
    row.last_message_at = now

    db.commit()
    db.refresh(row)

    return _ticket_out(
        db,
        row,
        include_messages=True,
    )


@router.post("/tickets/{ticket_id}/close")
def close_my_ticket(
    ticket_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _user_ticket(
        db,
        ticket_id,
        user,
    )

    now = datetime.utcnow()

    row.status = "closed"
    row.closed_at = now
    row.updated_at = now

    db.commit()
    db.refresh(row)

    return _ticket_out(db, row)


@admin_router.get("/tickets")
def admin_tickets(
    status: str | None = Query(default=None),
    category: str | None = Query(default=None),
    user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    query = db.query(SupportTicket)

    if status:
        status = status.strip().lower()

        if status not in VALID_STATUSES:
            raise HTTPException(
                status_code=422,
                detail="وضعیت نامعتبر است",
            )

        query = query.filter(
            SupportTicket.status == status
        )

    if category:
        query = query.filter(
            SupportTicket.category
            == _category(category)
        )

    if user_id is not None:
        query = query.filter(
            SupportTicket.user_id == user_id
        )

    rows = (
        query
        .order_by(
            SupportTicket.last_message_at.desc()
        )
        .all()
    )

    return [
        _ticket_out(db, row)
        for row in rows
    ]


@admin_router.get("/tickets/{ticket_id}")
def admin_ticket_detail(
    ticket_id: int,
    db: Session = Depends(get_db),
):
    row = _ticket_or_404(
        db,
        ticket_id,
    )

    return _ticket_out(
        db,
        row,
        include_messages=True,
    )


@admin_router.post("/tickets/{ticket_id}/reply")
def admin_reply(
    ticket_id: int,
    payload: MessageIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _require_content(payload)

    row = _ticket_or_404(
        db,
        ticket_id,
    )

    if row.status == "closed":
        raise HTTPException(
            status_code=409,
            detail="این تیکت بسته شده است",
        )

    now = datetime.utcnow()

    db.add(
        SupportMessage(
            ticket_id=row.id,
            sender_user_id=admin.id,
            sender_role="admin",
            source="admin",
            message=(
                payload.message.strip()
                if payload.message
                else None
            ),
            attachment_type=payload.attachment_type,
            attachment_ref=payload.attachment_ref,
            created_at=now,
        )
    )

    row.status = "answered"
    row.updated_at = now
    row.last_message_at = now

    db.commit()
    db.refresh(row)

    # TWINPANEL_SUPPORT_TELEGRAM_REPLY_NOTIFY_V1
    try:
        if row.user_id is not None:
            last_admin_message = (
                db.query(SupportMessage)
                .filter(
                    SupportMessage.ticket_id
                    == row.id,
                    SupportMessage.sender_role
                    == "admin",
                )
                .order_by(
                    SupportMessage.id.desc()
                )
                .first()
            )

            if last_admin_message:
                queue_telegram_notification(
                    db,
                    user_id=row.user_id,
                    event_key=(
                        "support-reply:"
                        f"{row.id}:"
                        f"{last_admin_message.id}"
                    ),
                    kind="support_reply",
                    payload={
                        "ticket_id": row.id,
                        "message":
                            last_admin_message.message
                            or "",
                        "attachment_type":
                            last_admin_message
                            .attachment_type,
                        "attachment_ref":
                            last_admin_message
                            .attachment_ref,
                    },
                )

                db.commit()

    except Exception as exc:
        db.rollback()
        print(
            "support telegram notify failed:",
            str(exc),
            flush=True,
        )

    return _ticket_out(
        db,
        row,
        include_messages=True,
    )


@admin_router.post("/tickets/{ticket_id}/close")
def admin_close_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
):
    row = _ticket_or_404(
        db,
        ticket_id,
    )

    now = datetime.utcnow()

    row.status = "closed"
    row.closed_at = now
    row.updated_at = now

    db.commit()
    db.refresh(row)

    return _ticket_out(db, row)


@admin_router.post("/tickets/{ticket_id}/reopen")
def admin_reopen_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
):
    row = _ticket_or_404(
        db,
        ticket_id,
    )

    now = datetime.utcnow()

    row.status = "open"
    row.closed_at = None
    row.updated_at = now

    db.commit()
    db.refresh(row)

    return _ticket_out(db, row)


# TWINPANEL_SUPPORT_IMAGE_UPLOAD_V1

CHAT_IMAGE_DIR = Path(
    "/var/lib/twinpanel/support-chat"
)

CHAT_IMAGE_MAX_BYTES = 5 * 1024 * 1024


def _detect_chat_image(data: bytes) -> str | None:

    if data.startswith(
        b"\x89PNG\r\n\x1a\n"
    ):
        return "png"

    if data.startswith(
        b"\xff\xd8\xff"
    ):
        return "jpg"

    if (
        len(data) >= 12
        and data[:4] == b"RIFF"
        and data[8:12] == b"WEBP"
    ):
        return "webp"

    if (
        data.startswith(b"GIF87a")
        or data.startswith(b"GIF89a")
    ):
        return "gif"

    return None


async def _save_chat_image(
    request: Request,
) -> dict:

    data = await request.body()

    if not data:
        raise HTTPException(
            status_code=422,
            detail="فایل تصویر خالی است",
        )

    if len(data) > CHAT_IMAGE_MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail="حداکثر حجم تصویر ۵ مگابایت است",
        )

    ext = _detect_chat_image(data)

    if not ext:
        raise HTTPException(
            status_code=415,
            detail="فرمت تصویر پشتیبانی نمی‌شود",
        )

    CHAT_IMAGE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    filename = (
        secrets.token_urlsafe(24)
        + "."
        + ext
    )

    target = CHAT_IMAGE_DIR / filename

    target.write_bytes(data)

    return {
        "attachment_type": "image",
        "attachment_ref":
            f"/v1/support/files/{filename}",
    }


@router.get("/files/{filename}")
def support_image_file(
    filename: str,
):

    if (
        not filename
        or Path(filename).name != filename
    ):
        raise HTTPException(
            status_code=404,
            detail="فایل پیدا نشد",
        )

    path = CHAT_IMAGE_DIR / filename

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="فایل پیدا نشد",
        )

    from fastapi.responses import FileResponse

    return FileResponse(
        path,
        headers={
            "Cache-Control":
                "private, max-age=86400"
        },
    )


@router.post(
    "/tickets/{ticket_id}/upload-image"
)
async def user_upload_support_image(
    ticket_id: int,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    row = _user_ticket(
        db,
        ticket_id,
        user,
    )

    if row.status == "closed":
        raise HTTPException(
            status_code=409,
            detail="این گفتگو بسته شده است",
        )

    return await _save_chat_image(
        request
    )


@router.post(
    "/guest/tickets/{ticket_id}/upload-image"
)
async def guest_upload_support_image(
    ticket_id: int,
    request: Request,
    x_guest_chat_token: str = Header(
        alias="X-Guest-Chat-Token",
    ),
    db: Session = Depends(get_db),
):

    row = _guest_ticket(
        db,
        ticket_id,
        x_guest_chat_token,
    )

    if row.status == "closed":
        raise HTTPException(
            status_code=409,
            detail="این گفتگو بسته شده است",
        )

    return await _save_chat_image(
        request
    )


@admin_router.post(
    "/tickets/{ticket_id}/upload-image"
)
async def admin_upload_support_image(
    ticket_id: int,
    request: Request,
    db: Session = Depends(get_db),
):

    row = _ticket_or_404(
        db,
        ticket_id,
    )

    if row.status == "closed":
        raise HTTPException(
            status_code=409,
            detail="این گفتگو بسته شده است",
        )

    return await _save_chat_image(
        request
    )


# ============================================================
# TWINPANEL_SUPPORT_DELETE_MESSAGE_V37
# ============================================================

@admin_router.delete(
    "/tickets/{ticket_id}/messages/{message_id}"
)
def admin_delete_support_message_v37(
    ticket_id: int,
    message_id: int,
    db: Session = Depends(get_db),
):
    ticket = _ticket_or_404(
        db,
        ticket_id,
    )

    message = (
        db.query(SupportMessage)
        .filter(
            SupportMessage.id == message_id,
            SupportMessage.ticket_id == ticket_id,
        )
        .first()
    )

    if message is None:
        raise HTTPException(
            status_code=404,
            detail="پیام پیدا نشد",
        )

    db.delete(message)
    db.flush()

    latest = (
        db.query(SupportMessage)
        .filter(
            SupportMessage.ticket_id == ticket_id
        )
        .order_by(
            SupportMessage.created_at.desc(),
            SupportMessage.id.desc(),
        )
        .first()
    )

    if latest is not None:
        ticket.last_message_at = latest.created_at
    else:
        ticket.last_message_at = ticket.created_at

    ticket.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(ticket)

    return _ticket_out(
        db,
        ticket,
        include_messages=True,
    )


# =========================================================
# TWINPANEL_SUPPORT_DELETE_CONVERSATION_V40
# حذف کامل گفتگو + تمام پیام‌های آن
# =========================================================

@admin_router.delete("/tickets/{ticket_id}")
def admin_delete_support_conversation_v40(
    ticket_id: int,
    db: Session = Depends(get_db),
):
    row = _ticket_or_404(
        db,
        ticket_id,
    )

    deleted_messages = (
        db.query(SupportMessage)
        .filter(
            SupportMessage.ticket_id == ticket_id
        )
        .delete(
            synchronize_session=False
        )
    )

    db.delete(row)
    db.commit()

    return {
        "ok": True,
        "ticket_id": ticket_id,
        "deleted_messages": int(
            deleted_messages or 0
        ),
    }

