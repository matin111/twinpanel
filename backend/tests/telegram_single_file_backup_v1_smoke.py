"""Offline test: local Telegram Bot API receives one full backup document."""
from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import backup_telegram_single_file_v1 as single


def main():
    with tempfile.TemporaryDirectory(prefix="tp-one-file-test-") as temp:
        backup=Path(temp)/"test-backup.tpbak"
        backup.write_bytes(b"encrypted-test-only" * 600)
        meta={
            "kind":"auto","created_at":"test","sha256":"example-sha",
            "telegram_sent":False
        }
        recorded=[]
        def save(_, value):
            recorded.append(dict(value))
        requests=[]
        def fake_api(_, token, method, *, data=None, files=None, timeout=30):
            requests.append(method)
            assert token=="fake-token"
            if method=="getMe":
                return {"ok":True,"result":{"id":12345}}
            if method=="sendDocument":
                assert "document" in files
                filename,handle,mimetype=files["document"]
                assert filename==backup.name
                assert handle.read()==backup.read_bytes()
                return {"ok":True,"result":{"message_id":11,
                    "document":{"file_size":backup.stat().st_size}}}
            if method=="sendMessage":
                assert "SHA256" in data["text"]
                return {"ok":True,"result":{"message_id":12}}
            raise AssertionError(method)

        with patch.object(single, "local_api_url",return_value="http://127.0.0.1:8081"), \
             patch.object(single, "_call",side_effect=fake_api):
            first=single.send_single_backup(
                backup,"9876",token="fake-token",meta=meta,write_meta=save
            )
            assert first["parts"]==1 and first["delivery_mode"]=="single"
            assert meta["telegram_sent"] is True
            assert recorded[-1]["telegram_parts_sent"]==[1]
            second=single.send_single_backup(
                backup,"9876",token="fake-token",meta=meta,write_meta=save
            )
            assert second["parts"]==1
            assert requests.count("sendDocument")==1
            assert requests.count("sendMessage")==2
        print("SINGLE_DOCUMENT_UPLOAD_RESUME_TEST_PASS")

        # No local Bot API configured -> caller must retain existing behavior.
        with patch.object(single,"local_api_url",return_value=None):
            assert single.send_single_backup(
                backup,"9876",token="fake-token",meta=meta,write_meta=save
            ) is None
        print("NO_LOCAL_API_NON_DESTRUCTIVE_FALLBACK_PASS")


if __name__=="__main__":
    main()
