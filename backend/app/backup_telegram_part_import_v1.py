"""Authenticated upload of separately downloaded Telegram .tpbak parts.

Each <= 40MiB document is uploaded independently, verified against its
partNNNofNNN filename and stored in a private temporary directory.
Only after every part arrives can a separate systemd worker concatenate,
check optional SHA256 and decrypt/inspect the Fernet archive.
The live database is NEVER restored by these endpoints.
"""
from __future__ import annotations
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime,timezone,timedelta
from pathlib import Path
from fastapi import APIRouter,Depends,File,HTTPException,UploadFile
from pydantic import BaseModel,Field
from .backup_service import BACKUP_ROOT,import_backup_file
from .deps import require_admin

router=APIRouter(prefix="/v1/admin/backups",tags=["admin-backup-multipart-import"],
                 dependencies=[Depends(require_admin)])
STAGING=BACKUP_ROOT/"incoming-telegram-parts-v1"
PART_BYTES=40*1024*1024
MAX_TOTAL=3*1024*1024*1024
MAX_PARTS=75
HEX=re.compile(r"[0-9a-f]{32}\Z")
SHA=re.compile(r"[0-9a-f]{64}\Z")
PART_NAME=re.compile(r"(?P<name>[A-Za-z0-9][A-Za-z0-9._-]{0,163}\.tpbak)\.part(?P<index>\d{3})of(?P<total>\d{3})\Z")


class NewSet(BaseModel):
    part_filename:str=Field(min_length=20,max_length=200)
    sha256:str=Field(default="",max_length=64)


def parse_part(name:str):
    if not name or Path(name).name!=name:
        raise HTTPException(status_code=422,detail="BACKUP_PART_FILENAME_INVALID")
    match=PART_NAME.fullmatch(name)
    if not match:
        raise HTTPException(status_code=422,detail="BACKUP_PART_FILENAME_INVALID")
    index=int(match["index"]);total=int(match["total"])
    if not 1<=index<=total<=MAX_PARTS:
        raise HTTPException(status_code=422,detail="BACKUP_PART_NUMBER_INVALID")
    return match["name"],index,total


def paths(ident:str):
    if not HEX.fullmatch(ident):
        raise HTTPException(status_code=404,detail="BACKUP_PART_SESSION_UNKNOWN")
    folder=STAGING/ident
    return folder,folder/"state.json",folder/"state.lock"


def load(ident:str):
    _,meta,_=paths(ident)
    try:
        result=json.loads(meta.read_text())
        if not isinstance(result,dict):raise ValueError()
        return result
    except (OSError,ValueError):
        raise HTTPException(status_code=404,detail="BACKUP_PART_SESSION_UNKNOWN")


def save(meta:Path,state:dict):
    state["updated_at"]=datetime.now(timezone.utc).isoformat()
    tmp=meta.with_suffix(".tmp")
    with tmp.open("w",encoding="utf-8") as out:
        json.dump(state,out,ensure_ascii=False)
    os.chmod(tmp,0o600)
    os.replace(tmp,meta)


def status(state:dict):
    done=sorted(int(n) for n in state.get("parts",{}))
    return {
        "id":state["id"],"filename":state["filename"],
        "total_parts":state["total_parts"],"received_parts":done,
        "received_count":len(done),"state":state["state"],
        "size_bytes":sum(int(v["size"]) for v in state["parts"].values()),
        "imported_filename":state.get("imported_filename"),
        "error_code":state.get("error_code"),
    }


@router.post("/telegram-parts",status_code=201)
def new_session(payload:NewSet):
    name,index,total=parse_part(payload.part_filename)
    sha=payload.sha256.strip().lower()
    if sha and not SHA.fullmatch(sha):
        raise HTTPException(status_code=422,detail="BACKUP_SHA256_INVALID")
    STAGING.mkdir(mode=0o700,parents=True,exist_ok=True)
    os.chmod(STAGING,0o700)
    ident=uuid.uuid4().hex
    folder,meta,_=paths(ident)
    folder.mkdir(mode=0o700)
    save(meta,{
        "id":ident,"filename":name,"total_parts":total,
        "sha256":sha,"state":"uploading","parts":{},
        "created_at":datetime.now(timezone.utc).isoformat(),
    })
    return {"ok":True,"session":status(load(ident))}


@router.get("/telegram-parts/{ident}")
def show_session(ident:str):
    return {"ok":True,"session":status(load(ident))}


@router.delete("/telegram-parts/{ident}")
def cancel_session(ident:str):
    folder,meta,lock=paths(ident)
    if not folder.is_dir():
        raise HTTPException(status_code=404,detail="BACKUP_PART_SESSION_UNKNOWN")
    with lock.open("a+") as mutex:
        fcntl.flock(mutex,fcntl.LOCK_EX)
        state=load(ident)
        if state["state"]=="verifying":
            raise HTTPException(status_code=409,detail="BACKUP_PART_JOIN_IN_PROGRESS")
        # Only temporary chunks and bookkeeping are deleted here.
        # Never remove the verified imported backup file from BACKUP_ROOT.
        for part in folder.iterdir():
            if part.is_file() and part.name!="state.lock":
                part.unlink(missing_ok=True)
    lock.unlink(missing_ok=True)
    folder.rmdir()
    return {"ok":True,"deleted":True}


@router.post("/telegram-parts/{ident}/part")
async def upload_part(ident:str,file:UploadFile=File(...)):
    folder,meta,lock=paths(ident)
    name,index,total=parse_part(str(file.filename or ""))
    with lock.open("a+") as mutex:
        fcntl.flock(mutex,fcntl.LOCK_EX)
        state=load(ident)
        if state["state"]!="uploading":
            raise HTTPException(status_code=409,detail="BACKUP_PART_UPLOAD_NOT_ACTIVE")
        if state["filename"]!=name or state["total_parts"]!=total:
            raise HTTPException(status_code=422,detail="BACKUP_PART_SET_MISMATCH")
        key=str(index)
        part=folder/f"part{index:03d}"
        tmp=folder/f".part{index:03d}.{uuid.uuid4().hex}.tmp"
        digest=hashlib.sha256()
        size=0
        try:
            with tmp.open("xb") as out:
                os.chmod(tmp,0o600)
                while True:
                    chunk=await file.read(1024*1024)
                    if not chunk:break
                    size+=len(chunk)
                    if size>PART_BYTES:
                        raise HTTPException(status_code=413,detail="BACKUP_PART_TOO_LARGE")
                    out.write(chunk)
                    digest.update(chunk)
                out.flush()
                os.fsync(out.fileno())
            if size==0:
                raise HTTPException(status_code=422,detail="BACKUP_PART_EMPTY")
            existing=state["parts"].get(key)
            if existing:
                if existing["size"]!=size or existing["sha256"]!=digest.hexdigest():
                    raise HTTPException(status_code=409,detail="BACKUP_PART_ALREADY_UPLOADED_DIFFERENT")
                return {"ok":True,"session":status(state),"duplicate":True}
            if sum(v["size"] for v in state["parts"].values())+size>MAX_TOTAL:
                raise HTTPException(status_code=413,detail="BACKUP_SET_TOO_LARGE")
            os.replace(tmp,part)
            state["parts"][key]={"size":size,"sha256":digest.hexdigest()}
            save(meta,state)
            return {"ok":True,"session":status(state)}
        finally:
            tmp.unlink(missing_ok=True)


@router.post("/telegram-parts/{ident}/finish",status_code=202)
def finish(ident:str):
    folder,meta,lock=paths(ident)
    with lock.open("a+") as mutex:
        fcntl.flock(mutex,fcntl.LOCK_EX)
        state=load(ident)
        if state["state"] in ("verifying","imported"):
            return {"ok":True,"session":status(state)}
        if state["state"]!="uploading":
            raise HTTPException(status_code=409,detail="BACKUP_PART_SET_FAILED")
        count=state["total_parts"]
        if sorted(map(int,state["parts"]))!=list(range(1,count+1)):
            raise HTTPException(status_code=409,detail="BACKUP_PART_SET_INCOMPLETE")
        for i in range(1,count+1):
            part=folder/f"part{i:03d}"
            if not part.is_file() or part.stat().st_size!=state["parts"][str(i)]["size"]:
                raise HTTPException(status_code=409,detail="BACKUP_PART_SET_INCOMPLETE")
        state["state"]="verifying"
        save(meta,state)
        args=["/usr/bin/systemd-run","--quiet","--collect",
              "--unit=twinpanel-backup-telegram-join-"+ident,
              "--property=Type=exec","--property=RuntimeMaxSec=3600",
              "--property=WorkingDirectory=/opt/twinpanel/current/backend",
              "--property=EnvironmentFile=/etc/twinpanel/backend.env",
              "/opt/twinpanel/venv/bin/python",
              "/opt/twinpanel/current/backend/scripts/twinpanel_backup_telegram_join_job_v1.py",
              ident]
        try:
            proc=subprocess.run(args,capture_output=True,timeout=15,check=False)
            if proc.returncode:raise RuntimeError()
        except Exception:
            state["state"]="failed"
            state["error_code"]="BACKUP_JOIN_WORKER_START_FAILED"
            save(meta,state)
            raise HTTPException(status_code=503,detail="BACKUP_JOIN_WORKER_START_FAILED")
        return {"ok":True,"session":status(state)}


def join_job(ident:str):
    folder,meta,lock=paths(ident)
    with lock.open("a+") as mutex:
        fcntl.flock(mutex,fcntl.LOCK_EX)
        state=load(ident)
        if state["state"]!="verifying":return
    combined=folder/"joined.tpbak"
    try:
        digest=hashlib.sha256()
        with combined.open("xb") as output:
            os.chmod(combined,0o600)
            for index in range(1,state["total_parts"]+1):
                part=folder/f"part{index:03d}"
                local_sha=hashlib.sha256()
                local_size=0
                with part.open("rb") as source:
                    while True:
                        block=source.read(1024*1024)
                        if not block:break
                        output.write(block)
                        digest.update(block)
                        local_sha.update(block)
                        local_size+=len(block)
                info=state["parts"][str(index)]
                if local_size!=info["size"] or local_sha.hexdigest()!=info["sha256"]:
                    raise ValueError("BACKUP_PART_INTEGRITY_FAILED")
            output.flush()
            os.fsync(output.fileno())
        if state.get("sha256") and digest.hexdigest()!=state["sha256"]:
            raise ValueError("BACKUP_JOIN_SHA256_MISMATCH")
        result=import_backup_file(combined,state["filename"])
        state["state"]="imported"
        state["verified_sha256"]=digest.hexdigest()
        state["imported_filename"]=result["filename"]
        state["finished_at"]=datetime.now(timezone.utc).isoformat()
        save(meta,state)
        # Delete temporary part archives only after complete authenticated import.
        for index in range(1,state["total_parts"]+1):
            (folder/f"part{index:03d}").unlink(missing_ok=True)
    except Exception as exc:
        state["state"]="failed"
        state["error_code"]=(
            str(exc) if isinstance(exc,ValueError) and
            re.fullmatch(r"[A-Z0-9_]{5,80}",str(exc))
            else "BACKUP_JOIN_OR_IMPORT_FAILED"
        )
        save(meta,state)
        raise
    finally:
        combined.unlink(missing_ok=True)
