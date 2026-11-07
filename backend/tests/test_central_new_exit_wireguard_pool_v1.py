"""New central Exit WireGuard pool remains fail-closed and non-disruptive."""
import ast
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.services import central_new_exit_wireguard_pool_v1 as pool


class NewExitWireguardPoolTests(unittest.IsolatedAsyncioTestCase):
    def test_remote_source_compiles_and_requires_empty_peer_set(self):
        ast.parse(pool._REMOTE)
        self.assertIn("WG_CENTRAL_POOL_EXISTING_PEERS",pool._REMOTE)
        self.assertIn("if peers.strip()",pool._REMOTE)
        self.assertIn("WG_CENTRAL_POOL_ROUTE_CONFLICT",pool._REMOTE)
        self.assertIn("10.96.0.1/21",pool._REMOTE)
        self.assertNotIn("systemctl restart",pool._REMOTE)
        self.assertNotIn("wg-quick down",pool._REMOTE)
        self.assertIn('"wg","show",IFACE,"peers"',pool._REMOTE)
        self.assertIn("central-pool-preinstall.bak",pool._REMOTE)

    async def test_verified_remote_ack_is_required(self):
        conn=MagicMock()
        conn.run=AsyncMock(return_value=SimpleNamespace(
            exit_status=0,
            stdout=json.dumps({
                "ok":True, "pool":"10.96/21",
                "existing_peers":0, "restarted":False,
                "nat_rules":2,
            }),
        ))
        response=await pool.prepare_hidden_exit_wireguard_pool(conn)
        self.assertTrue(response["ok"])
        self.assertFalse(response["restarted"])
        conn.run.assert_awaited_once()

    async def test_remote_failure_fails_closed(self):
        conn=MagicMock()
        conn.run=AsyncMock(return_value=SimpleNamespace(
            exit_status=1,stdout="",stderr="SENSITIVE PRIVATE KEY",
        ))
        with self.assertRaisesRegex(RuntimeError,
                                    "CENTRAL_WG_POOL_PREPARATION_FAILED") as error:
            await pool.prepare_hidden_exit_wireguard_pool(conn)
        self.assertNotIn("SENSITIVE",str(error.exception))

    async def test_malformed_ack_cannot_mark_pool_healthy(self):
        conn=MagicMock()
        conn.run=AsyncMock(return_value=SimpleNamespace(
            exit_status=0,
            stdout=json.dumps({"ok":True,"pool":"10.96/21",
                               "existing_peers":17}),
        ))
        with self.assertRaisesRegex(RuntimeError,
                                    "CENTRAL_WG_POOL_ACK_INVALID"):
            await pool.prepare_hidden_exit_wireguard_pool(conn)


if __name__=="__main__":
    unittest.main()
