"""Isolated concurrency guard for controller account enforcement. No DB/SSH."""
from __future__ import annotations

import ast
import asyncio
import os
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1] / "app/services/account_enforcement_v2.py"
TREE=ast.parse(SOURCE.read_text())


def isolated(names: tuple[str, ...], namespace: dict) -> dict:
    items=[node for node in TREE.body
           if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in names]
    if len(items)!=len(names):
        raise AssertionError((len(items),names))
    future=ast.ImportFrom(module="__future__",names=[ast.alias(name="annotations")],level=0)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[future,*items],type_ignores=[])),
                 str(SOURCE),"exec"),namespace)
    return namespace


class ParallelEnforcementTests(TestCase):
    def test_ssh_connection_closes_read_txn_before_network(self):
        fn=next(n for n in TREE.body if isinstance(n,ast.AsyncFunctionDef)
                and n.name=="_execute_command")
        code=ast.unparse(fn)
        self.assertIn("ssh_connect_saved(node, db, close_read_transaction_before_ssh=True)",code)

    def test_claim_excludes_nodes_already_under_mutation(self):
        fn=next(n for n in TREE.body if isinstance(n,ast.FunctionDef)
                and n.name=="_claim_next_command")
        self.assertIn("node_id.notin_(sorted(exclude_node_ids))",ast.unparse(fn))
        self.assertIn("with_for_update(skip_locked=True)",ast.unparse(fn))

    def test_bounded_parallel_never_overlaps_same_node(self):
        for parallel in (1,2,4):
            with self.subTest(parallel=parallel):
                queue=[{"node_id":n,"command_id":str(i)} for i,n in
                       enumerate((1,2,1,3,2,4,4,5,6))]
                active=set()
                max_parallel=[0]
                completed=[]
                def claim(*,exclude_node_ids=None):
                    for i,command in enumerate(queue):
                        if command["node_id"] not in (exclude_node_ids or set()):
                            return queue.pop(i)
                    return None
                async def execute(command):
                    nid=command["node_id"]
                    self.assertNotIn(nid,active)
                    active.add(nid)
                    max_parallel[0]=max(len(active),max_parallel[0])
                    await asyncio.sleep(.003)
                    completed.append(command["command_id"])
                    active.remove(nid)
                ns=isolated(
                    ("_parallel_nodes_limit","process_account_enforcement_once"),
                    {"os":os,"asyncio":asyncio,"_claim_next_command":claim,"_execute_command":execute}
                )
                with patch.dict(os.environ,{"TP_ACCOUNT_ENFORCEMENT_PARALLEL_NODES":str(parallel)}):
                    total=asyncio.run(ns["process_account_enforcement_once"](limit=20))
                self.assertEqual(total,9)
                self.assertEqual(len(completed),9)
                self.assertEqual(max_parallel[0],parallel)
                self.assertFalse(active)

    def test_production_default_is_serial_after_canary(self):
        ns = isolated(("_parallel_nodes_limit",), {"os": os})
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(ns["_parallel_nodes_limit"](), 1)

    def test_invalid_parallel_setting_fails_safe(self):
        ns=isolated(("_parallel_nodes_limit",),{"os":os})
        with patch.dict(os.environ,{"TP_ACCOUNT_ENFORCEMENT_PARALLEL_NODES":"invalid"}):
            self.assertEqual(ns["_parallel_nodes_limit"](),1)
        with patch.dict(os.environ,{"TP_ACCOUNT_ENFORCEMENT_PARALLEL_NODES":"40"}):
            self.assertEqual(ns["_parallel_nodes_limit"](),4)
        with patch.dict(os.environ,{"TP_ACCOUNT_ENFORCEMENT_PARALLEL_NODES":"-2"}):
            self.assertEqual(ns["_parallel_nodes_limit"](),1)

    def test_exception_waits_for_other_nodes_to_finish(self):
        jobs=[{"node_id":1},{"node_id":2}]
        active=set()
        def claim(*,exclude_node_ids=None):
            for i,item in enumerate(jobs):
                if item["node_id"] not in (exclude_node_ids or set()):
                    return jobs.pop(i)
            return None
        async def execute(item):
            active.add(item["node_id"])
            try:
                await asyncio.sleep(.003 if item["node_id"]==1 else .008)
                if item["node_id"]==1:
                    raise RuntimeError("node isolated failure")
            finally:
                active.remove(item["node_id"])
        ns=isolated(("_parallel_nodes_limit","process_account_enforcement_once"),
                    {"os":os,"asyncio":asyncio,"_claim_next_command":claim,
                     "_execute_command":execute})
        with patch.dict(os.environ,{"TP_ACCOUNT_ENFORCEMENT_PARALLEL_NODES":"2"}):
            with self.assertRaisesRegex(RuntimeError,"isolated failure"):
                asyncio.run(ns["process_account_enforcement_once"](limit=2))
        self.assertEqual(active,set())


if __name__=="__main__":
    main()
