"""One daemon-wide reconciliation, not N-per-user SSH invocations."""
from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.protocol_account_registry import ALL_PROTOCOL_SET
from app.services import central_node_runtime_engine_v1 as engine


class RuntimeFamilyContracts(unittest.TestCase):
    def test_every_protocol_belongs_to_exactly_one_runtime_family(self):
        families=engine.validate_runtime_families()
        owners=[p for family in families for p in family.protocols]
        self.assertEqual(set(owners), ALL_PROTOCOL_SET)
        self.assertEqual(len(owners),len(set(owners)))
        self.assertEqual(len(families),10)
        self.assertFalse(any("backfill" in x.adapter for x in families))

    def test_one_command_per_family_not_per_subscription(self):
        for family in engine.FAMILIES:
            command=engine.adapter_command(family,14,3000,Path("/backend"))
            self.assertEqual(command.count("--node-id"),1)
            self.assertEqual(command[-2:],["--confirm-node-id","14"])
            self.assertNotIn("--subscription-id",command)


class RuntimeReconciliationTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_families_are_dispatched_without_serial_waiting(self):
        started=[]
        gate=asyncio.Event()
        class Process:
            async def wait(self):
                await gate.wait()
                return 0
        async def spawn(*cmd,**kwargs):
            started.append(cmd)
            if len(started)==len(engine.FAMILIES):
                gate.set()
            return Process()
        with patch.object(engine.asyncio,"create_subprocess_exec",side_effect=spawn):
            result=await asyncio.wait_for(
                engine.reconcile_runtime_families(14,3000,Path("/backend")),2,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["runtime_families"],10)
        self.assertEqual(len(started),10)
        self.assertEqual(len(result["succeeded"]),10)

    async def test_single_family_failure_makes_whole_node_unpublishable(self):
        class Process:
            def __init__(self,index):self.index=index
            async def wait(self):return 2 if self.index==3 else 0
        index=0
        async def spawn(*cmd,**kw):
            nonlocal index
            index+=1
            return Process(index)
        with patch.object(engine.asyncio,"create_subprocess_exec",side_effect=spawn):
            result=await engine.reconcile_runtime_families(14,3000,Path("/backend"))
        self.assertFalse(result["ok"])
        self.assertEqual(len(result["failed"]),1)
        self.assertEqual(len(result["succeeded"]),9)


if __name__=="__main__":
    unittest.main()
