"""Live-account safe enforcement regressions: no database or node is contacted."""
from __future__ import annotations

import ast
import asyncio
import base64
import json
import shlex
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, main

SOURCE = (Path(__file__).resolve().parents[1] / "app/services/account_enforcement_v2.py").read_text()
TREE = ast.parse(SOURCE)


def isolated(name: str, supplied: dict) -> dict:
    nodes = [n for n in TREE.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    assert len(nodes) == 1, name
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    compiled = compile(ast.fix_missing_locations(ast.Module(body=[future, nodes[0]], type_ignores=[])), "<isolated_enforcement>", "exec")
    exec(compiled, supplied)
    return supplied


class ControllerEnforcementTests(TestCase):
    def test_revokes_are_claimed_before_earlier_restores(self):
        src = ast.unparse(next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "_claim_next_command"))
        self.assertIn("case((QuotaNodeCommand.command_type == 'revoke_subscription', 0)", src)
        self.assertIn("QuotaNodeCommand.issued_at.asc()", src)
        self.assertIn(".with_for_update(skip_locked=True)", src)
        self.assertIn("QuotaNodeCommand.expires_at > now", src)

    def test_wireguard_revoke_exact_remote_command_signature(self):
        commands = []
        persistence = []
        async def remote(conn, command, **kw):
            self.assertIs(conn, connector)
            self.assertIsInstance(command, str)
            commands.append(command)
        async def public_key(conn, private):
            return "public-wireguard-peer="
        async def persist(conn, **kw):
            persistence.append(kw)
        connector = object()
        namespace = isolated("_classic_wireguard", {
            "shlex": shlex,
            "_classic_item_for_node": lambda credential, node_id: {"node_id": node_id},
            "_wireguard_identity": lambda item: ("secret-do-not-expose", "10.50.0.2/32"),
            "_wireguard_public_key": public_key,
            "_remote_run": remote,
            "_persist_wireguard_peer": persist,
        })
        result = asyncio.run(namespace["_classic_wireguard"](
            connector, SimpleNamespace(), 7, "revoke_subscription"
        ))
        self.assertEqual(result, "controller_classic_revoked")
        self.assertEqual(len(commands), 1)
        self.assertIn("wg set wg-access0 peer", commands[0])
        self.assertIn("remove", commands[0])
        self.assertEqual(len(persistence), 1)
        self.assertFalse(persistence[0]["enabled"])

    def test_xray_restore_applies_to_every_vless_inbound_without_touching_others(self):
        commands = []
        uuid = "11223344-5566-7788-99aa-bbccddeeff00"
        async def remote(conn, command, **kw):
            commands.append(command)
        namespace = isolated("_classic_v2ray", {
            "base64": base64,
            "shlex": shlex,
            "_stored_v2ray_uuid": lambda credential, node_id: uuid,
            "_remote_run": remote,
        })
        connector = object()
        self.assertEqual(
            asyncio.run(namespace["_classic_v2ray"](
                connector, SimpleNamespace(), 42, 7, "restore_subscription"
            )),
            "controller_classic_restored",
        )
        self.assertEqual(len(commands), 1)
        encoded = shlex.split(commands[0].split(" | base64 -d", 1)[0])[-1]
        script = base64.b64decode(encoded).decode("utf-8")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            doc = {"inbounds": [
                {"protocol": "vless", "settings": {"clients": [
                    {"email": "mv-42@twinpanel", "id": "old"},
                    {"email": "mv-9@twinpanel", "id": "other"}]}},
                {"protocol": "vless", "settings": {"clients": [
                    {"email": "mv-42@twinpanel", "id": "old2"}]}},
                {"protocol": "vless", "settings": {"clients": []}},
                {"protocol": "trojan", "settings": {"clients": [
                    {"email": "mv-42@twinpanel", "id": "trojan"}]}}
            ]}
            path.write_text(json.dumps(doc), encoding="utf-8")
            script = script.replace('p="/usr/local/etc/xray/config.json"', f"p={str(path)!r}")
            for _ in (1, 2):
                exec(compile(script, str(path), "exec"), {})
                loaded = json.loads(path.read_text())
                for inbound in loaded["inbounds"][:3]:
                    matches = [c for c in inbound["settings"]["clients"]
                               if c.get("email") == "mv-42@twinpanel"]
                    self.assertEqual(matches, [{"id": uuid, "email": "mv-42@twinpanel"}])
                self.assertEqual(
                    loaded["inbounds"][0]["settings"]["clients"][0],
                    {"email": "mv-9@twinpanel", "id": "other"},
                )
                self.assertEqual(
                    loaded["inbounds"][3]["settings"]["clients"],
                    doc["inbounds"][3]["settings"]["clients"],
                )


if __name__ == "__main__":
    main()
