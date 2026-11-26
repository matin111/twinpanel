"""Revoke Xray accounts even when legacy node-specific UUID delivery is absent."""
from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch

from app.services import account_enforcement_v2 as enforce


class XrayRevokeTests(TestCase):
    def test_revoke_does_not_read_lost_node_uuid_and_removes_all_vless_profiles(self):
        commands = []

        async def fake_run(_conn, command, **_kwargs):
            commands.append(command)

        with patch.object(enforce, "_stored_v2ray_uuid", side_effect=AssertionError("UUID read on revoke")), \
             patch.object(enforce, "_remote_run", side_effect=fake_run):
            result = asyncio.run(enforce._classic_v2ray(
                object(), SimpleNamespace(), 42, 29, "revoke_subscription"))
        self.assertEqual(result, "controller_classic_revoked")
        self.assertEqual(len(commands), 1)
        # Decode the exact script sent to SSH, but execute it ONLY against a
        # temporary JSON fixture and never start or restart an actual daemon.
        encoded = commands[0].split(" | base64 -d", 1)[0].split()[-1]
        script = base64.b64decode(encoded).decode()
        with TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            original = {"inbounds":[
                {"protocol":"vless","settings":{"clients":[
                    {"id":"a","email":"mv-42@twinpanel"},
                    {"id":"other","email":"mv-43@twinpanel"}]}},
                {"protocol":"vless","settings":{"clients":[
                    {"id":"b","email":"mv-42@twinpanel"}]}},
                {"protocol":"trojan","settings":{"clients":[
                    {"id":"c","email":"mv-42@twinpanel"}]}}
            ]}
            path.write_text(json.dumps(original))
            script = script.replace(
                'p="/usr/local/etc/xray/config.json"',
                "p=" + repr(str(path)),
            )
            exec(compile(script, "xray_revoke_fixture", "exec"), {})
            doc = json.loads(path.read_text())
            self.assertEqual(
                doc["inbounds"][0]["settings"]["clients"],
                [{"id":"other","email":"mv-43@twinpanel"}])
            self.assertEqual(doc["inbounds"][1]["settings"]["clients"], [])
            self.assertEqual(
                doc["inbounds"][2]["settings"]["clients"],
                original["inbounds"][2]["settings"]["clients"])

    def test_restore_still_requires_node_uuid(self):
        with patch.object(enforce, "_stored_v2ray_uuid", side_effect=RuntimeError("missing UUID")):
            with self.assertRaisesRegex(RuntimeError, "missing UUID"):
                asyncio.run(enforce._classic_v2ray(
                    object(), SimpleNamespace(), 42, 29, "restore_subscription"))


if __name__ == "__main__":
    main()
