"""New central Xray Exit: profile authority comes from the node, never a customer."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

tmp=tempfile.TemporaryDirectory(prefix="twinpanel-xray-authority-")
os.environ.setdefault("APP_SECRET_KEY","ci-xray-authority-only")
os.environ.setdefault("DATABASE_URL",f"sqlite+pysqlite:///{Path(tmp.name)/'db.sqlite'}")
os.environ.setdefault("NODE_AGENT_SHARED_SECRET","ci-xray-authority-agent-only")

from app import central_xray_node_authority_v1 as auth

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts"/"twinpanel_central_xray_node_bulk_v1.py"


def reality_authority():
    return {
        "profiles":["xhttp_reality","tcp_reality"],
        "reality_server_name":"www.example.org",
        "reality_password":"Q"*43,
        "short_id_xhttp":"1234567890abcdef",
        "xhttp_path":"/xh-example",
        "tls_enabled":False,"tls_domain":"",
        "tls_sni_ws":"","tls_sni_tcp":"","ws_path":"",
    }


def tls_authority():
    value=reality_authority()
    value.update(
        profiles=["websocket_tls","xhttp_reality","tcp_tls"],
        tls_enabled=True,tls_domain="xray.example.org",
        tls_sni_ws="xray.example.org",
        tls_sni_tcp="xray.example.org",
        ws_path="/ws-example",
    )
    return value


class CentralXrayAuthorityTests(unittest.TestCase):
    def test_node_authority_has_no_private_credentials(self):
        script=auth._PUBLIC_PROBE
        compile(script,"<node-xray-authority-probe>","exec")
        self.assertIn("reality_password",script)
        self.assertIn("reality.get",script)
        self.assertNotIn("print(state)",script)
        self.assertNotIn('"privateKey":',script)
        self.assertNotIn('"clients":',script)

    def test_reality_first_user_requires_no_existing_template(self):
        item_id=str(uuid4())
        node=SimpleNamespace(id=19,name="New Exit")
        with patch.object(auth,"_endpoint",side_effect=lambda db,n,p:
                          ("203.0.113.19",24019 if p=="xhttp_reality" else 38019)):
            item=auth.build_item_from_node_authority(
                MagicMock(),node,client_uuid=item_id,
                account_label="account-19",authority=reality_authority(),
            )
        self.assertEqual(item["uuid"],item_id)
        self.assertEqual(len(item["profiles"]),2)
        for p in item["profiles"]:
            uri=urlsplit(p["uri"])
            self.assertEqual(uri.username,item_id)
            self.assertEqual(uri.hostname,"203.0.113.19")
            self.assertEqual(parse_qs(uri.query)["pbk"],["Q"*43])
            self.assertEqual(parse_qs(uri.query)["sni"],["www.example.org"])
        self.assertNotIn("source_template",json.dumps(item))

    def test_tls_profiles_use_node_certificate_identity_not_user_template(self):
        node=SimpleNamespace(id=19,name="TLS Exit")
        item_id=str(uuid4())
        ports={"websocket_tls":23319,"xhttp_reality":23119,"tcp_tls":28019}
        with patch.object(auth,"_endpoint",side_effect=lambda db,n,p:("tls.example.org",ports[p])):
            item=auth.build_item_from_node_authority(
                MagicMock(),node,client_uuid=item_id,
                account_label="first-client",authority=tls_authority(),
            )
        self.assertEqual({x["id"] for x in item["profiles"]},set(ports))
        for p in item["profiles"]:
            self.assertEqual(urlsplit(p["uri"]).username,item_id)
        self.assertEqual(parse_qs(urlsplit(item["profiles"][-1]["uri"]).query)["sni"],
                         ["xray.example.org"])

    def test_fail_closed_on_wrong_profiles_and_missing_public_key(self):
        x=reality_authority()
        x["profiles"]=["xhttp_reality"]
        with self.assertRaisesRegex(RuntimeError,"PROFILE_SET_INVALID"):
            auth.validate_public_authority(x)
        x=reality_authority()
        x["reality_password"]=""
        with self.assertRaisesRegex(RuntimeError,"PUBLIC_AUTHORITY_INVALID"):
            auth.validate_public_authority(x)
        x=reality_authority()
        x["reality_password"]="not-a-real-public-key"
        with self.assertRaisesRegex(RuntimeError,"PUBLIC_KEY_INVALID"):
            auth.validate_public_authority(x)

    def test_remote_probe_only_accepts_public_verified_values(self):
        class Connection:
            run=AsyncMock(return_value=SimpleNamespace(
                exit_status=0,stdout=json.dumps(reality_authority())))
        result=asyncio.run(auth.read_node_public_authority(Connection()))
        self.assertEqual(result["profiles"],["xhttp_reality","tcp_reality"])
        command=Connection.run.call_args.args[0]
        self.assertIn("base64 -d | python3",command)
        self.assertNotIn("PRIVATE_KEY",json.dumps(result))
        with patch.object(Connection,"run",new=AsyncMock(return_value=SimpleNamespace(
            exit_status=1,stdout="invalid"))):
            with self.assertRaisesRegex(RuntimeError,"PROBE_FAILED"):
                asyncio.run(auth.read_node_public_authority(Connection()))

    def test_central_bulk_script_does_not_depend_on_another_user(self):
        text=SCRIPT.read_text(encoding="utf-8")
        compile(text,str(SCRIPT),"exec")
        self.assertNotIn("XRAY_SAME_NODE_COMPLETE_TEMPLATE_MISSING",text)
        self.assertNotIn("same_node_template",text)
        self.assertIn("read_node_public_authority(conn)",text)
        self.assertIn("build_item_from_node_authority(",text)
        self.assertIn("choose_existing_uuid(",text)
        self.assertIn("staged_hot_script(entries)",text)
        self.assertIn("XRAY_ENTITLEMENT_CHANGED_DURING_STAGE",text)
        self.assertIn("XRAY_STAGE_NOT_APPLIED_TO_RUNTIME",text)


if __name__=="__main__":
    unittest.main()
