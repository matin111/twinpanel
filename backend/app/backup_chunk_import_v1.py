"""Authenticated, chunked import of large encrypted TwinPanel backups.

Max one upload chunk per HTTP request (8 MiB) to stay below proxy limits.
Archive verification and decryption are performed by a standalone systemd job.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .backup_service import BACKUP_ROOT, import_backup_file
from .deps import require_admin
from fastapi import Depends

router=APIRouter(prefix="/v1/admin/backups",tags=["admin-backup-chunked-import"],
                 dependencies=[Depends(require_admin)])
STAGING=BACKUP_ROOT/"incoming-upload-v1"
PART_BYTES=8*1024*1024
MAX_BYTES=3*1024*1024*1024
HEX=re.compile(r"[0-9a-f]{32}\Z")
SHA=re.compile(r"[0-9a-f]{64}\Z")


class InitUpload(BaseModel):
    filename: str=Field(min_length=6,max_length=180)
    size_bytes: int=Field(ge=1,le=MAX_BYTES)
    sha256: str=Field(min_length=64,max_length=64)


def _files(ident: str) -> tuple[Path,Path,Path]:
    if not HEX.fullmatch(ident):
        raise HTTPException(status_code=404,detail="UPLOAD_SESSION_NOT_FOUND")
    return (
        STAGING/(ident+".json"),
        STAGING/(ident+".tpbak.part"),
        STAGING/(ident+".lock"),
    )


def _save(meta:Path,obj:dict) -> None:
    obj["updated_at"]=datetime.now(timezone.utc).isoformat()
    temp=meta.with_suffix(".tmp")
    temp.write_text(json.dumps(obj,ensure_ascii=False),encoding="utf-8")
    os.chmod(temp,0o600)
    temp.replace(meta)


def _load(ident:str) -> dict:
    meta,_,_=_files(ident)
    try:
        return json.loads(meta.read_text())
    except (OSError,ValueError):
        raise HTTPException(status_code=404,detail="UPLOAD_SESSION_NOT_FOUND")


@router.post("/upload-session",status_code=201)
def create_upload_session(payload:InitUpload):
    safe=Path(payload.filename).name
    if safe!=payload.filename or not safe.endswith(".tpbak"):
        raise HTTPException(status_code=422,detail="INVALID_BACKUP_FILENAME")
    if not SHA.fullmatch(payload.sha256.lower()):
        raise HTTPException(status_code=422,detail="INVALID_SHA256")
    STAGING.mkdir(mode=0o700,parents=True,exist_ok=True)
    os.chmod(STAGING,0o700)
    ident=uuid.uuid4().hex
    meta,part,_=_files(ident)
    part.touch(mode=0o600,exist_ok=False)
    _save(meta,{
        "id":ident,"filename":safe,"size_bytes":payload.size_bytes,
        "sha256":payload.sha256.lower(),"state":"uploading",
        "created_at":datetime.now(timezone.utc).isoformat(),
        "uploaded_bytes":0,
    })
    return {"ok":True,"id":ident,"chunk_bytes":PART_BYTES,"uploaded_bytes":0}


@router.get("/upload-session/{ident}")
def get_upload_session(ident:str):
    row=_load(ident)
    # Never expose a filesystem path.
    return {"ok":True,"session":row}


@router.post("/upload-session/{ident}/chunk")
async def upload_chunk(ident:str,offset:int,file:UploadFile=File(...)):
    if offset<0:
        raise HTTPException(status_code=422,detail="INVALID_UPLOAD_OFFSET")
    meta,path,lock=_files(ident)
    data=await file.read(PART_BYTES+1)
    if not data or len(data)>PART_BYTES:
        raise HTTPException(status_code=413,detail="BACKUP_CHUNK_SIZE_INVALID")
    with lock.open("a+") as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        row=_load(ident)
        if row["state"]!="uploading":
            raise HTTPException(status_code=409,detail="UPLOAD_NOT_ACTIVE")
        total=int(row["size_bytes"])
        existing=path.stat().st_size
        if offset+len(data)>total:
            raise HTTPException(status_code=413,detail="BACKUP_EXCEEDS_DECLARED_SIZE")
        if offset<existing and offset+len(data)<=existing:
            with path.open("rb") as inp:
                inp.seek(offset)
                if inp.read(len(data))==data:
                    return {"ok":True,"uploaded_bytes":existing,"duplicate":True}
        if offset!=existing:
            raise HTTPException(status_code=409,detail={
                "message":"UPLOAD_OFFSET_MISMATCH","uploaded_bytes":existing,
            })
        with path.open("ab") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        row["uploaded_bytes"]=path.stat().st_size
        _save(meta,row)
        return {"ok":True,"uploaded_bytes":row["uploaded_bytes"]}


@router.post("/upload-session/{ident}/finish",status_code=202)
def finalize_upload(ident:str):
    meta,path,lock=_files(ident)
    with lock.open("a+") as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        row=_load(ident)
        if row["state"] in ("verifying","imported"):
            return {"ok":True,"session":row}
        if row["state"]!="uploading":
            raise HTTPException(status_code=409,detail="UPLOAD_SESSION_FAILED")
        if not path.is_file() or path.stat().st_size!=int(row["size_bytes"]):
            raise HTTPException(status_code=409,detail="UPLOAD_INCOMPLETE")
        row["state"]="verifying"
        _save(meta,row)
        args=[
            "/usr/bin/systemd-run","--quiet","--collect",
            "--unit=twinpanel-backup-import-"+ident,
            "--property=Type=exec","--property=RuntimeMaxSec=3600",
            "--property=WorkingDirectory=/opt/twinpanel/current/backend",
            "--property=EnvironmentFile=/etc/twinpanel/backend.env",
            "/opt/twinpanel/venv/bin/python",
            "/opt/twinpanel/current/backend/scripts/twinpanel_backup_import_job_v1.py",
            ident,
        ]
        try:
            proc=subprocess.run(args,capture_output=True,timeout=12,check=False)
            if proc.returncode:
                raise RuntimeError("IMPORT_WORKER_DISPATCH_FAILED")
        except Exception:
            row["state"]="failed"
            row["error_code"]="IMPORT_WORKER_DISPATCH_FAILED"
            _save(meta,row)
            raise HTTPException(status_code=503,detail="IMPORT_WORKER_DISPATCH_FAILED")
        return {"ok":True,"session":row}


def run_import_job(ident:str) -> None:
    meta,path,_=_files(ident)
    row=_load(ident)
    if row["state"]!="verifying":
        return
    try:
        with path.open("rb") as inp:
            digest=hashlib.file_digest(inp,"sha256").hexdigest()
        if digest!=row["sha256"]:
            raise ValueError("BACKUP_SHA256_MISMATCH")
        # This checks Fernet authentication and the expected backup format;
        # importing to backup storage does not alter the live database.
        result=import_backup_file(path,row["filename"])
        path.unlink(missing_ok=True)
        row["state"]="imported"
        row["imported_filename"]=result["filename"]
        row["finished_at"]=datetime.now(timezone.utc).isoformat()
        _save(meta,row)
    except Exception as exc:
        row["state"]="failed"
        row["error_code"]=(
            str(exc) if isinstance(exc,ValueError) and
            re.fullmatch(r"[A-Z0-9_]{5,80}",str(exc))
            else type(exc).__name__
        )
        _save(meta,row)
        # Never retain an invalid or unverifiable uploaded backup.
        path.unlink(missing_ok=True)
        raise
