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
            returncode = 0
            async def communicate(self):
                nonlocal active
                await asyncio.sleep(0.02)
                active-=1
                return b"", b""
        async def spawn(*cmd,**kwargs):
            nonlocal active,peak
            started.append(cmd)
            active+=1
            peak=max(peak,active)
            return Process()
        with (patch.object(engine.os,"cpu_count",return_value=4),
              patch.object(engine.asyncio,"create_subprocess_exec",
                           side_effect=spawn)):
            result=await asyncio.wait_for(
                engine.reconcile_runtime_families(14,3000,Path("/backend")),2,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["runtime_families"],10)
        self.assertEqual(len(started),10)
        self.assertEqual(len(result["succeeded"]),10)
        self.assertEqual(peak,1)
        self.assertIn("sudoku_shared_v2",str(started[-1]))
        self.assertEqual(active,0)

    async def test_fast_controller_runs_two_independent_bulk_families(self):
        active=0
        peak=0
        spawned=[]
        class Process:
            returncode = 0
            async def communicate(self):
                nonlocal active
                await asyncio.sleep(0.025)
                active-=1
                return b"", b""
        async def spawn(*command,**kwargs):
            nonlocal active,peak
            active+=1
            peak=max(peak,active)
            spawned.append(str(command[1]))
            return Process()
        with (patch.object(engine.os,"cpu_count",return_value=16),
              patch.object(engine.asyncio,"create_subprocess_exec",
                           side_effect=spawn)):
            result=await asyncio.wait_for(
                engine.reconcile_runtime_families(
                    14,3000,Path("/backend")),3,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(peak,2)
        self.assertEqual(active,0)
        self.assertEqual(len(spawned),10)
        self.assertIn("sudoku_shared_v2",spawned[-1])

    async def test_delta_runs_only_selected_wireguard_family(self):
        calls = []
        class Process:
            returncode = 0
            async def communicate(self):
                return b"", b""
        async def spawn(*cmd, **kwargs):
            calls.append(cmd)
            return Process()
        selected = (next(f for f in engine.FAMILIES
                         if f.name == "wireguard"),)
        with patch.object(engine.asyncio, "create_subprocess_exec",
                          side_effect=spawn):
            result = await engine.reconcile_runtime_families(
                14, 3000, Path("/backend"), families=selected)
        self.assertTrue(result["ok"])
        self.assertEqual(result["runtime_families"], 1)
        self.assertEqual(result["succeeded"], ["wireguard"])
        self.assertEqual(len(calls), 1)
        self.assertIn("wireguard", str(calls[0]))

    async def test_delta_rejects_unknown_family_before_process_spawn(self):
        fake = engine.RuntimeFamily("unsafe", "twinpanel_central_fake.py",
                                    frozenset({"wireguard"}))
        with patch.object(engine.asyncio, "create_subprocess_exec") as spawn:
            with self.assertRaisesRegex(RuntimeError,
                                        "UNKNOWN_DELTA_FAMILY"):
                await engine.reconcile_runtime_families(
                    14, 3000, Path("/backend"), families=(fake,))
            spawn.assert_not_called()

    async def test_shared_sudoku_gets_one_isolated_retry_after_nonzero(self):
        calls=[]
        class Process:
            def __init__(self,code):self.returncode=code
            async def communicate(self):return b"", b""
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
            def __init__(self,code):self.returncode=code
            async def communicate(self):return b"", b""
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
            def __init__(self,index):self.returncode=2 if index==3 else 0
            async def communicate(self):return b"", b""
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
