"""Regression smoke: separate Telegram .tpbak part upload and fail-closed import.

All files stay inside a temporary test directory, no production database writes.
"""
from __future__ import annotations
import asyncio
import hashlib
import io
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from starlette.datastructures import UploadFile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import backup_telegram_part_import_v1 as m


async def run():
    with tempfile.TemporaryDirectory(prefix="tp-telegram-parts-ci-") as temp:
        one=b"one encrypted part";two=b"second encrypted part"
        full=hashlib.sha256(one+two).hexdigest()
        with patch.object(m,"STAGING",Path(temp)), \
             patch.object(m,"import_backup_file",return_value={"filename":"safe-import.tpbak"}) as importer:
            started=m.new_session(m.NewSet(
                part_filename="twinpanel-20261109-test.tpbak.part002of002",
                sha256=full,
            ))
            ident=started["session"]["id"]
            try:
                m.finish(ident)
            except HTTPException as exc:
                assert exc.status_code==409
                assert exc.detail=="BACKUP_PART_SET_INCOMPLETE"
            else:
                raise AssertionError("Allowed finishing an empty backup set")
            for number,data in ((2,two),(1,one)):
                filename=f"twinpanel-20261109-test.tpbak.part{number:03d}of002"
                uploaded=await m.upload_part(
                    ident,UploadFile(io.BytesIO(data),filename=filename)
                )
                assert uploaded["session"]["received_count"]>0
            with patch.object(m.subprocess,"run",return_value=SimpleNamespace(returncode=0)):
                m.finish(ident)
            m.join_job(ident)
            state=m.show_session(ident)["session"]
            assert state["state"]=="imported"
            assert state["received_count"]==2
            assert importer.call_count==1
            assert not (Path(temp)/ident/"part001").exists()
            assert not (Path(temp)/ident/"part002").exists()
            print("TELEGRAM_PART_SEPARATE_OUT_OF_ORDER_JOIN_PASS")

            bad=m.new_session(m.NewSet(
                part_filename="twinpanel-20261109-other.tpbak.part001of001",
                sha256="0"*64,
            ))["session"]["id"]
            await m.upload_part(
                bad,UploadFile(io.BytesIO(b"not-the-expected-bytes"),
                               filename="twinpanel-20261109-other.tpbak.part001of001"),
            )
            with patch.object(m.subprocess,"run",return_value=SimpleNamespace(returncode=0)):
                m.finish(bad)
            try:
                m.join_job(bad)
            except ValueError as exc:
                assert str(exc)=="BACKUP_JOIN_SHA256_MISMATCH"
            else:
                raise AssertionError("Invalid SHA256 imported")
            assert m.show_session(bad)["session"]["state"]=="failed"
            assert importer.call_count==1
            print("TELEGRAM_PART_SHA256_MISMATCH_REFUSED_PASS")


if __name__=="__main__":
    asyncio.run(run())
