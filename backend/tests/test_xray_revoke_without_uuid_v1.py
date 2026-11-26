"""Xray revocation works without a per-node UUID and never restarts the server."""
from __future__ import annotations

import asyncio
import base64
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch

from app.services import account_enforcement_v2 as enforce


class XrayRevokeTests(TestCase):
    def test_revoke_does_not_read_lost_node_uuid_and_never_restarts(self):
        commands=[]
        async def fake_run(_conn,command,**kwargs):
            commands.append(command)
        with patch.object(enforce,"_stored_v2ray_uuid",side_effect=AssertionError("revoke read UUID")), \
             patch.object(enforce,"_remote_run",side_effect=fake_run):
            result=asyncio.run(enforce._classic_v2ray(
                object(),SimpleNamespace(),42,29,"revoke_subscription"))
        self.assertEqual(result,"controller_classic_revoked")
        self.assertEqual(len(commands),1)
        self.assertNotIn("systemctl restart",commands[0])
        encoded=commands[0].split(" | base64 -d",1)[0].split()[-1]
        script=base64.b64decode(encoded).decode("utf-8")
        self.assertIn("mv-42@twinpanel",script)
        self.assertIn("api"," ".join(script.split()))
        self.assertIn("HOT_REVOKE",script)
        self.assertNotIn("systemctl restart",script)
        compile(script,"<xray-hot-revoke>","exec")

    def test_restore_still_requires_node_uuid(self):
        with patch.object(enforce,"_stored_v2ray_uuid",side_effect=RuntimeError("missing UUID")):
            with self.assertRaisesRegex(RuntimeError,"missing UUID"):
                asyncio.run(enforce._classic_v2ray(
                    object(),SimpleNamespace(),42,29,"restore_subscription"))


if __name__=="__main__":
    main()
