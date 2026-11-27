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
        self.assertIn(".with_for_update(of=QuotaNodeCommand, skip_locked=True)", src)
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

    def test_xray_restore_uses_existing_live_hot_sync_without_restart(self):
        source = ast.unparse(next(
            node for node in TREE.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "_classic_v2ray"
        ))
        self.assertIn("hot_client_sync_script(client_id, email)", source)
        self.assertIn("_stored_v2ray_uuid(credential, node_id)", source)
        self.assertIn("hot_revoke_script(subscription_id)", source)
        self.assertNotIn("systemctl restart xray", source)
        self.assertIn("| base64 -d | python3", source)


if __name__ == "__main__":
    main()
