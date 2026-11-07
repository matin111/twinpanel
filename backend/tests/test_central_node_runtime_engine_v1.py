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
    async def test_all_families_apply_with_bounded_daemon_concurrency(self):
        started=[]
        active=0
        peak=0
        class Process:
            async def wait(self):
                nonlocal active
                await asyncio.sleep(0.02)
                active-=1
                return 0
        async def spawn(*cmd,**kwargs):
            nonlocal active,peak
            started.append(cmd)
            active+=1
            peak=max(peak,active)
            return Process()
        with patch.object(engine.asyncio,"create_subprocess_exec",side_effect=spawn):
            result=await asyncio.wait_for(
                engine.reconcile_runtime_families(14,3000,Path("/backend")),2,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["runtime_families"],10)
        self.assertEqual(len(started),10)
        self.assertEqual(len(result["succeeded"]),10)
        self.assertEqual(peak,3)
        self.assertIn("sudoku_shared_v2",str(started[-1]))
        self.assertEqual(active,0)

    async def test_shared_sudoku_gets_one_isolated_retry_after_nonzero(self):
        calls=[]
        class Process:
            def __init__(self,code):self.code=code
            async def wait(self):return self.code
        async def spawn(*cmd,**kw):
            name=str(cmd[1])
            calls.append(name)
            if "sudoku_shared" in name and sum("sudoku_shared" in c for c in calls)==1:
                return Process(2)
            return Process(0)
        with patch.object(engine.asyncio,"create_subprocess_exec",side_effect=spawn):
            result=await engine.reconcile_runtime_families(
                14,3000,Path("/backend"))
        self.assertTrue(result["ok"])
        self.assertEqual(len(calls),11)
        self.assertTrue("sudoku_shared" in calls[-2])
        self.assertTrue("sudoku_shared" in calls[-1])

    async def test_shared_sudoku_second_failure_blocks_publication(self):
        calls=[]
        class Process:
            def __init__(self,code):self.code=code
            async def wait(self):return self.code
        async def spawn(*cmd,**kw):
            name=str(cmd[1])
            calls.append(name)
            return Process(2 if "sudoku_shared" in name else 0)
        with patch.object(engine.asyncio,"create_subprocess_exec",side_effect=spawn):
            result=await engine.reconcile_runtime_families(
                14,3000,Path("/backend"))
        self.assertFalse(result["ok"])
        self.assertEqual(result["failed"],["sudoku"])
        self.assertEqual(len(calls),11)

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
