"""OpenVPN mobile import regression: never deliver an .ovpn without remote.

Read-only mock data; no SSH, no live customer identities or certificates.
"""
from __future__ import annotations

from copy import deepcopy
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

os.environ.setdefault("APP_SECRET_KEY", "ci-openvpn-import-only")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:////tmp/ci-openvpn-import-only.sqlite")
os.environ.setdefault("NODE_AGENT_SHARED_SECRET", "ci-openvpn-agent-only")

from app.openvpn_profile_delivery_guard_v1 import (
    disambiguate_openvpn_filenames, validate_openvpn_profile,
)
from app.routers import (
    account_delivery as ad,
    public_connection_files_v9 as native,
    public_connection_hub_v5 as hub,
    public_connection_v3 as old,
    public_connection_all_multilink_v34 as bundle,
    public_connection_payload_fast_v1 as fast,
)

VALID = (
    "client\n"
    "dev tun\n"
    "proto udp\n"
    "remote tunel2.example.org 21007\n"
    "resolv-retry infinite\n"
    "nobind\n"
    "<ca>\nCA_DATA\n</ca>\n"
    "<cert>\nCERT_DATA\n</cert>\n"
    "<key>\nKEY_DATA\n</key>\n"
)


def payload():
    return {
        "credentials": [{
            "protocol": "openvpn",
            "items": [
                {
                    "node_id": 7,
                    "filename": "msabt123825-Germany.ovpn",
                    "config": VALID,
                },
                {
                    "node_id": 13,
                    "filename": "msabt123825-Germany.ovpn",
                    "config": VALID.replace("21007", "21013"),
                },
                {
                    "node_id": 6,
                    "filename": "msabt123825-Turkey.ovpn",
                    "config": VALID.replace("21007", "21006"),
                },
            ],
        }],
        "downloads": {},
    }


class OpenVPNDeliveryGuards(unittest.TestCase):
    def test_valid_profiles_preserved_byte_for_byte(self):
        validate_openvpn_profile(VALID)
        validate_openvpn_profile(VALID.replace("proto udp", "proto tcp-client"))
        validate_openvpn_profile(VALID.replace("remote tunel2.example.org 21007", "remote tunel2.example.org 21007 tcp-client"))

    def test_missing_or_invalid_remote_is_rejected(self):
        for bad in [
            VALID.replace("remote tunel2.example.org 21007\n", ""),
            VALID.replace("remote tunel2.example.org 21007", "# remote tunel2.example.org 21007"),
            VALID.replace("remote tunel2.example.org 21007", "remote "),
            VALID.replace("remote tunel2.example.org 21007", "remote undefined 21007"),
            VALID.replace("remote tunel2.example.org 21007", "remote tunel2.example.org 0"),
            VALID.replace("remote tunel2.example.org 21007", "remote tunel2.example.org 70000"),
            VALID.replace("remote tunel2.example.org 21007", "remote <bad> 21007"),
            "<html><body>not an OpenVPN file</body></html>",
            "",
        ]:
            with self.subTest(bad=bad[:35]),self.assertRaises(ValueError):
                validate_openvpn_profile(bad)

    def test_duplicate_germany_files_are_unique_without_mutating_certificate(self):
        p=payload()
        before=deepcopy(p)
        disambiguate_openvpn_filenames(p)
        entries=p["credentials"][0]["items"]
        self.assertEqual(
            [x["filename"] for x in entries],
            ["msabt123825-Germany-n7.ovpn",
             "msabt123825-Germany-n13.ovpn",
             "msabt123825-Turkey.ovpn"],
        )
        self.assertEqual([x["config"] for x in entries],
                         [x["config"] for x in before["credentials"][0]["items"]])
        disambiguate_openvpn_filenames(p)
        self.assertEqual(len({x["filename"] for x in entries}),3)

    def test_download_endpoint_returns_actual_valid_ovpn_and_unique_name(self):
        p=disambiguate_openvpn_filenames(payload())
        with patch.object(native, "_active_payload",return_value=p):
            response=native.public_connection_file_v9("token","openvpn",0,MagicMock())
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.body.decode(),VALID)
        self.assertIn("Germany-n7.ovpn",response.headers["content-disposition"])
        self.assertEqual(response.headers["cache-control"],"private, no-store")
        validate_openvpn_profile(response.body.decode())

    def test_download_endpoint_blocks_missing_remote_before_attachment(self):
        p=payload()
        p["credentials"][0]["items"][0]["config"]=VALID.replace(
            "remote tunel2.example.org 21007\n",""
        )
        with patch.object(native,"_active_payload",return_value=p):
            with self.assertRaises(HTTPException) as ctx:
                native.public_connection_file_v9("token","openvpn",0,MagicMock())
        self.assertEqual(ctx.exception.status_code,409)
        self.assertEqual(ctx.exception.detail,"OPENVPN_PROFILE_REMOTE_MISSING")

    def test_legacy_download_blocks_missing_remote_and_uses_unique_name(self):
        sub=SimpleNamespace(id=3825,user_id=1,account_username="msabt123825")
        db=MagicMock()
        db.query.return_value.filter.return_value.first.return_value=None
        db.get.return_value=None
        p=disambiguate_openvpn_filenames(payload())
        with (patch.object(ad,"_subscription_from_share_token",return_value=sub),
              patch.object(ad,"_public_payload",return_value=p)):
            result=ad.public_config_file("token","openvpn",7,db)
            self.assertEqual(result.status_code,200)
            self.assertIn("Germany-n7.ovpn",result.headers["content-disposition"])
            p["credentials"][0]["items"][0]["config"]="client\nproto udp\n"
            with self.assertRaises(HTTPException) as ctx:
                ad.public_config_file("token","openvpn",7,db)
            self.assertEqual(ctx.exception.status_code,409)

    def test_hub_and_legacy_page_do_not_offer_corrupt_file(self):
        valid_item={"filename":"germany.ovpn","config":VALID}
        invalid_item={"filename":"germany.ovpn","config":"client\nproto udp\n"}
        for item in (valid_item,invalid_item):
            page=hub._file_action("openvpn",item,1,"hub-protocol-5")
            old_page=old.file_download_card("openvpn",1,"Germany",item)
            if item is valid_item:
                self.assertIn("download-config",page)
                self.assertIn("download-config",old_page)
            else:
                self.assertNotIn("download-config",page)
                self.assertNotIn("download-config",old_page)
                self.assertIn("نامعتبر",page)

    def test_multi_download_zip_refuses_malformed_ovpn(self):
        sub=SimpleNamespace(account_username="user")
        bad={"node_id":7,"filename":"bad.ovpn","config":"client\nproto udp\n"}
        with self.assertRaises(HTTPException) as error:
            bundle._bundle_item("openvpn",sub,bad,0)
        self.assertEqual(error.exception.status_code,409)

    def test_public_and_fast_payloads_resolve_duplicate_filename(self):
        sub=SimpleNamespace(id=3825,expires_at=None,traffic_limit_bytes=0)
        db=MagicMock()
        db.info={}
        db.query.return_value.all.return_value=[]
        with (patch.object(ad,"_stored_info",return_value=payload()),
              patch.object(ad,"_share_url",return_value="https://example.invalid/test")):
            result=ad._public_payload(db,sub)
        names=[x["filename"] for x in result["credentials"][0]["items"]]
        self.assertEqual(names[:2],[
            "msabt123825-Germany-n7.ovpn","msabt123825-Germany-n13.ovpn",
        ])
        with (patch.object(fast,"_stored_info",return_value=payload()),
              patch.object(fast,"_share_url",return_value="https://example.invalid/test")):
            result=fast.public_connection_payload_fast_v1(db,sub)
        names=[x["filename"] for x in result["credentials"][0]["items"]]
        self.assertEqual(names[:2],[
            "msabt123825-Germany-n7.ovpn","msabt123825-Germany-n13.ovpn",
        ])


if __name__=="__main__":
    unittest.main()
