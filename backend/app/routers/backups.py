from __future__ import annotations

# TWINPANEL_ADMIN_BACKUP_ROUTER_V1

import json
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..backup_service import (
    BACKUP_KEY,
    BACKUP_TABLES,
    EXCLUDED_RUNTIME_TABLES,
    create_backup,
    delete_backup,
    get_backup_path,
    import_backup_file,
    inspect_backup,
    list_backups,
    load_settings,
    recovery_key_fingerprint,
    restore_backup,
    save_settings,
    send_backup_to_telegram,
    test_telegram,
    verify_telegram_chat,
)
from ..deps import require_admin


router = APIRouter(
    prefix="/v1/admin/backups",
    tags=["admin-backups"],
    dependencies=[
        Depends(require_admin)
    ],
)


class BackupCreateIn(BaseModel):
    send_telegram: bool = False


class BackupSettingsIn(BaseModel):
    enabled: bool = False

    frequency: Literal[
        "hourly",
        "daily",
        "weekly",
    ] = "daily"

    hour: int = Field(
        default=3,
        ge=0,
        le=23,
    )

    minute: int = Field(
        default=0,
        ge=0,
        le=59,
    )

    weekday: int = Field(
        default=0,
        ge=0,
        le=6,
    )

    timezone: str = Field(
        default="Asia/Tehran",
        min_length=2,
        max_length=80,
    )

    send_telegram: bool = True

    telegram_chat_id: str = Field(
        default="",
        max_length=80,
    )

    retention: int = Field(
        default=14,
        ge=1,
        le=100,
    )



class TelegramVerifyIn(BaseModel):

    chat_id: str = Field(
        min_length=1,
        max_length=80,
    )


class RestoreIn(BaseModel):
    confirm: str


@router.get("")
def backup_home():

    return {
        "ok": True,
        "backups":
            list_backups(),
        "settings":
            load_settings(),
        "key_fingerprint":
            recovery_key_fingerprint(),
        "included_tables":
            BACKUP_TABLES,
        "excluded_runtime_tables":
            EXCLUDED_RUNTIME_TABLES,
    }


@router.put("/settings")

def update_backup_settings(
    payload: BackupSettingsIn,
):

    data = (
        payload.model_dump()
    )

    telegram_verification = None

    if data.get(
        "send_telegram"
    ):

        chat_id = str(
            data.get(
                "telegram_chat_id"
            ) or ""
        ).strip()

        if not chat_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "برای ارسال خودکار تلگرام، "
                    "Chat ID را وارد کنید."
                ),
            )

        try:
            telegram_verification = (
                verify_telegram_chat(
                    chat_id,
                    send_probe=False,
                )
            )

        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=str(exc),
            ) from exc

    saved = save_settings(
        data
    )

    return {
        "ok": True,
        "settings": saved,
        "telegram_verification":
            telegram_verification,
    }

def manual_backup(
    payload: BackupCreateIn,
):

    try:
        result = create_backup(
            kind="manual",
            send_telegram=(
                payload.send_telegram
            ),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

    return {
        "ok": True,
        "backup": result,
    }



# TWINPANEL_BACKUP_TELEGRAM_VERIFY_ROUTE_V3
@router.post("/verify-telegram")
def backup_verify_telegram(
    payload: TelegramVerifyIn,
):

    chat_id = str(
        payload.chat_id
        or ""
    ).strip()

    try:
        return verify_telegram_chat(
            chat_id,
            send_probe=True,
        )

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc



# TWINPANEL_MANUAL_BACKUP_CREATE_ROUTE_V146

@router.post("/create")
def manual_backup(
    payload: BackupCreateIn,
):

    try:
        result = create_backup(
            kind="manual",
            send_telegram=(
                payload.send_telegram
            ),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

    return {
        "ok": True,
        "backup": result,
    }


@router.post("/test-telegram")
def backup_test_telegram():

    settings = load_settings()

    chat_id = str(
        settings.get(
            "telegram_chat_id"
        ) or ""
    ).strip()

    if not chat_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Telegram Chat ID "
                "تنظیم نشده است"
            ),
        )

    try:
        return test_telegram(
            chat_id
        )

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


@router.get("/recovery-key")
def download_recovery_key():

    if not BACKUP_KEY.is_file():
        raise HTTPException(
            status_code=404,
            detail=(
                "Recovery key "
                "not found"
            ),
        )

    return FileResponse(
        path=str(BACKUP_KEY),
        media_type=(
            "application/octet-stream"
        ),
        filename=(
            "twinpanel-backup-"
            "recovery.key"
        ),
    )


@router.post("/upload")
async def upload_backup(
    file: UploadFile = File(...),
):

    original = Path(
        file.filename
        or "backup.tpbak"
    ).name

    if not original.endswith(
        ".tpbak"
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "فقط فایل .tpbak "
                "مجاز است"
            ),
        )

    content = await file.read(
        200 * 1024 * 1024
        + 1
    )

    if len(content) > (
        200 * 1024 * 1024
    ):
        raise HTTPException(
            status_code=413,
            detail=(
                "حجم فایل بیشتر "
                "از 200MB است"
            ),
        )

    with tempfile.NamedTemporaryFile(
        suffix=".tpbak",
        delete=False,
    ) as handle:

        handle.write(
            content
        )

        temp_path = Path(
            handle.name
        )

    try:
        result = (
            import_backup_file(
                temp_path,
                original,
            )
        )

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    finally:
        temp_path.unlink(
            missing_ok=True
        )

    return {
        "ok": True,
        "backup": result,
    }


@router.get("/{filename}/info")
def backup_info(
    filename: str,
):

    try:
        path = get_backup_path(
            filename
        )

        return {
            "ok": True,
            "backup":
                inspect_backup(
                    path
                ),
        }

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.get("/{filename}/download")
def download_backup(
    filename: str,
):

    try:
        path = get_backup_path(
            filename
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=(
                "بکاپ پیدا نشد"
            ),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return FileResponse(
        path=str(path),
        media_type=(
            "application/octet-stream"
        ),
        filename=path.name,
    )


@router.post("/{filename}/telegram")
def telegram_backup(
    filename: str,
):

    settings = load_settings()

    chat_id = str(
        settings.get(
            "telegram_chat_id"
        ) or ""
    ).strip()

    if not chat_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Telegram Chat ID "
                "تنظیم نشده است"
            ),
        )

    try:
        path = get_backup_path(
            filename
        )

        result = (
            send_backup_to_telegram(
                path,
                chat_id,
            )
        )

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    return {
        "ok": True,
        "backup": result,
    }


@router.post("/{filename}/restore")
def restore(
    filename: str,
    payload: RestoreIn,
):

    if payload.confirm != "RESTORE":
        raise HTTPException(
            status_code=400,
            detail=(
                "برای Restore باید "
                "عبارت RESTORE "
                "تأیید شود"
            ),
        )

    try:
        result = restore_backup(
            filename
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=(
                "بکاپ پیدا نشد"
            ),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=str(exc),
        ) from exc

    return result


@router.delete("/{filename}")
def remove_backup(
    filename: str,
):

    try:
        delete_backup(
            filename
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=(
                "بکاپ پیدا نشد"
            ),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return {
        "ok": True,
    }
