from __future__ import annotations

# TWINPANEL_ADMIN_BACKUP_ROUTER_V1

import json
import tempfile
import zipfile
import os
from pathlib import Path
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    BackgroundTasks,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..backup_service import (
    BACKUP_TABLES,
    EXCLUDED_RUNTIME_TABLES,
    create_backup,
    delete_backup,
    get_backup_path,
    import_backup_file,
    inspect_backup,
    list_backups,
    load_settings,
    restore_backup,
    save_settings,
    send_backup_to_telegram,
    test_telegram,
    verify_telegram_chat,
)
from ..backup_telegram_credentials import (
    backup_telegram_bot_status,
    delete_backup_telegram_bot_token,
    save_backup_telegram_bot_token,
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


class BackupTelegramBotTokenIn(BaseModel):

    token: str = Field(
        min_length=20,
        max_length=300,
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
        "telegram_bot":
            backup_telegram_bot_status(),
        "included_tables":
            BACKUP_TABLES,
        "excluded_runtime_tables":
            EXCLUDED_RUNTIME_TABLES,
    }


@router.get("/telegram-bot")
def backup_telegram_bot():
    return backup_telegram_bot_status()


@router.put("/telegram-bot")
def update_backup_telegram_bot(
    payload: BackupTelegramBotTokenIn,
):
    try:
        return save_backup_telegram_bot_token(
            payload.token
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


@router.delete("/telegram-bot")
def remove_backup_telegram_bot():
    try:
        return delete_backup_telegram_bot_token()
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "حذف تنظیمات ربات اختصاصی بکاپ ناموفق بود"
            ),
        ) from exc


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


# Manual backups must not run for minutes in an HTTP request and may
# not leave encrypted archives on the server after successful delivery.
@router.post("/create",status_code=202)
def manual_backup(payload: BackupCreateIn):
    from ..manual_telegram_backup_v1 import enqueue_manual_telegram_backup
    try:
        return {"ok": True, "job": enqueue_manual_telegram_backup(send_telegram=payload.send_telegram)}
    except ValueError as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503,detail="BACKUP_JOB_DISPATCH_FAILED") from exc


@router.get("/manual-jobs/{job_id}")
def manual_backup_job_status(job_id: str):
    from ..manual_telegram_backup_v1 import read_job
    try:
        return {"ok": True, "job": read_job(job_id)}
    except (OSError,ValueError,json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=404,detail="BACKUP_JOB_NOT_FOUND"
        ) from exc


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


@router.post("/upload")
async def upload_backup(
    file: UploadFile = File(...),
):

    original = Path(
        file.filename
        or "backup.zip"
    ).name

    if not original.lower().endswith((".zip", ".tpbak")):
        raise HTTPException(
            status_code=400,
            detail=(
                "فقط فایل ZIP یا .tpbak "
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
    background_tasks: BackgroundTasks,
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

    # The internal .tpbak is already gzip compressed.
    # Wrap it in one standard ZIP without redundant compression.
    with tempfile.NamedTemporaryFile(
        suffix=".zip", prefix="tp-download-",
        dir=path.parent, delete=False,
    ) as handle:
        zipped = Path(handle.name)
    os.chmod(zipped, 0o600)
    try:
        with zipfile.ZipFile(zipped, "w", allowZip64=True) as archive:
            archive.write(path, arcname=path.name, compress_type=zipfile.ZIP_STORED)
    except BaseException:
        zipped.unlink(missing_ok=True)
        raise
    background_tasks.add_task(zipped.unlink, missing_ok=True)
    return FileResponse(
        path=str(zipped),
        media_type="application/zip",
        filename=path.name.removesuffix(".tpbak") + ".zip",
        background=background_tasks,
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
