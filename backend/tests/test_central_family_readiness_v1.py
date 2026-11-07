"""Proof that published central Exits only probe the selected live family."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch

from app.services import central_family_readiness_v1 as readiness


class CentralFamilyReadinessTests(unittest.IsolatedAsyncioTestCase):
    def node(self, *, visible):
        return SimpleNamespace(id=14, show_to_users=visible, retired_at=None)

    async def test_hidden_adapter_probes_only_own_family(self):
        db=MagicMock()
        db.get.return_value=self.node(visible=False)
        row=SimpleNamespace(protocol="wireguard",status="online",port=51820)
        db.query.return_value.filter.return_value.all.return_value=[row]
        conn=MagicMock()
        conn.wait_closed=AsyncMock()
        with (patch.object(readiness,"allow_central_node",return_value=True),
              patch.object(readiness,"connect_protocol_runtime",
                           new_callable=AsyncMock,return_value=conn) as connect,
              patch.object(readiness,"_protocol_live_health",
                           new_callable=AsyncMock,return_value={"ok":True}) as probe):
            result=await readiness.verify_central_family_readiness(
                db,14,{"wireguard"})
            self.assertTrue(result["ok"])
            self.assertEqual(result["required_count"],1)
            connect.assert_awaited_once()
            probe.assert_awaited_once_with(conn,"wireguard",row)
            conn.close.assert_called_once()

    async def test_published_node_checks_only_selected_live_protocol(self):
        db=MagicMock()
        db.get.return_value=self.node(visible=True)
        row=SimpleNamespace(protocol="wireguard",status="online",port=51820)
        db.query.return_value.filter.return_value.all.return_value=[row]
        conn=MagicMock()
        conn.wait_closed=AsyncMock()
        with (patch.object(readiness,"allow_central_node",return_value=True),
              patch.object(readiness,"is_central_node",return_value=True),
              patch.object(readiness,"connect_protocol_runtime",
                           new_callable=AsyncMock,return_value=conn) as connect,
              patch.object(readiness,"_protocol_live_health",
                           new_callable=AsyncMock,return_value={"ok":True}) as probe,
              patch.object(readiness,"is_central_node",
                           return_value=True)):
            report=await readiness.verify_central_family_readiness(
                db,14,{"wireguard"})
            self.assertEqual(report["required_count"],1)
            self.assertTrue(report["ok"])
            probe.assert_awaited_once_with(conn,"wireguard",row)
            connect.assert_awaited_once()
            conn.close.assert_called_once()

    async def test_unregistered_published_node_rejected(self):
        db=MagicMock()
        db.get.return_value=self.node(visible=True)
        with (patch.object(readiness,"allow_central_node",return_value=True),
              patch.object(readiness,"is_central_node",return_value=False),
              patch.object(readiness,"connect_protocol_runtime",
                           new_callable=AsyncMock) as connect):
            report=await readiness.verify_central_family_readiness(
                db,14,{"socks5"})
            self.assertFalse(report["ok"])
            connect.assert_not_awaited()

    async def test_protocol_not_ready_blocks_runtime_mutation(self):
        db=MagicMock()
        db.get.return_value=self.node(visible=True)
        db.query.return_value.filter.return_value.all.return_value=[
            SimpleNamespace(protocol="wireguard",status="offline",port=51820)]
        with (patch.object(readiness,"allow_central_node",return_value=True),
              patch.object(readiness,"is_central_node",return_value=True),
              patch.object(readiness,"connect_protocol_runtime",
                           new_callable=AsyncMock) as connect):
            report=await readiness.verify_central_family_readiness(
                db,14,{"wireguard"})
            self.assertFalse(report["ok"])
            self.assertEqual(report["missing"],["wireguard"])
            connect.assert_not_awaited()


if __name__=="__main__":
    unittest.main()
