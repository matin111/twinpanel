"""Keep existing heavy node stages from being dispatched twice.

Tests isolate the scanner from SQL, systemd, SSH, and VPN daemons.
"""
from __future__ import annotations

import ast
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "app/services/central_runtime_visible_convergence_v1.py"
TREE = ast.parse(SOURCE.read_text())


def isolated(functions: tuple[str,...], globals_: dict) -> dict:
    subset=[n for n in TREE.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))
            and n.name in functions]
    assert len(subset)==len(functions)
    future=ast.ImportFrom(module="__future__",names=[ast.alias(name="annotations")],level=0)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[future,*subset],type_ignores=[])),
                 str(SOURCE),"exec"),globals_)
    return globals_


class Field:
    def __eq__(self,_other): return True
    def is_(self,_other): return True
    def asc(self):return self


class MockNode:
    id=Field()
    retired_at=Field()
    node_type=Field()
    status=Field()
    show_to_users=Field()
    def __init__(self,id):self.id=id


class DB:
    def __init__(self,nodes):self.nodes=nodes;self.rollbacks=0
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def query(self,*args):return self
    def filter(self,*args):return self
    def order_by(self,*args):return self
    def all(self):return self.nodes
    def rollback(self):self.rollbacks+=1


class DispatchDedupTests(TestCase):
    def test_read_active_unit_and_treat_failure_as_unknown(self):
        names=[]
        def run(cmd,**kwargs):
            names.append(cmd[-1])
            return SimpleNamespace(returncode=0,stdout="active\\n")
        ns=isolated(("_stage_unit_running",),{"subprocess":subprocess})
        with patch.object(subprocess,"run",side_effect=run):
            self.assertTrue(ns["_stage_unit_running"]("twinpanel-legacy-sudoku-shared-6.service"))
        self.assertEqual(names,["twinpanel-legacy-sudoku-shared-6.service"])
        with patch.object(subprocess,"run",return_value=SimpleNamespace(returncode=0,stdout="inactive\\n")):
            self.assertFalse(ns["_stage_unit_running"]("twinpanel-central-node-stage-19.service"))
        with patch.object(subprocess,"run",return_value=SimpleNamespace(returncode=1,stdout="")):
            with self.assertRaisesRegex(RuntimeError,"UNIT_STATE_UNAVAILABLE"):
                ns["_stage_unit_running"]("twinpanel-central-node-stage-19.service")
        with self.assertRaisesRegex(ValueError,"UNIT_INVALID"):
            ns["_stage_unit_running"]("unrelated.service")

    def run_scan(self, *, central:bool, running:bool):
        db=DB([MockNode(19 if central else 6)])
        launches=[]
        statuses=[]
        ns=isolated(("run_once",),{
            "SessionLocal":lambda:db,
            "Node":MockNode,
            "NodeType":SimpleNamespace(EXIT="EXIT"),
            "NodeStatus":SimpleNamespace(ONLINE="ONLINE"),
            "is_central_node":lambda _db,nid:central,
            "is_legacy_shared_node":lambda _db,nid:True,
            "sudoku_last_applied":lambda _db,nid:"old",
            "sudoku_desired":lambda _db,nid:"new",
            "last_applied":lambda _db,nid:"old",
            "load_desired_state":lambda _db,nid:SimpleNamespace(fingerprint="new"),
            "require_valid_desired_state":lambda desired,max_users:desired,
            "_stage_unit_running":lambda unit:statuses.append(unit) or running,
            "launch":lambda db,nid:launches.append(("central",nid)),
            "launch_legacy_shared_reconcile":lambda db,nid:launches.append(("legacy",nid)),
            "CentralStageLaunchError":type("CentralStageLaunchError",(RuntimeError,),{}),
            "_log":SimpleNamespace(exception=lambda *args:None),
        })
        result=ns["run_once"]()
        self.assertEqual(db.rollbacks,1)
        self.assertEqual(len(statuses),1)
        return result,launches,statuses[0]

    def test_active_legacy_unit_does_not_duplicate_or_claim_applied(self):
        result,launches,unit=self.run_scan(central=False,running=True)
        self.assertFalse(result["ok"])
        self.assertEqual(result["in_progress"],[6])
        self.assertFalse(result["up_to_date"])
        self.assertFalse(result["dispatched"])
        self.assertFalse(launches)
        self.assertEqual(unit,"twinpanel-legacy-sudoku-shared-6.service")

    def test_active_central_unit_does_not_duplicate_or_claim_applied(self):
        result,launches,unit=self.run_scan(central=True,running=True)
        self.assertEqual(result["in_progress"],[19])
        self.assertFalse(result["up_to_date"])
        self.assertEqual(launches,[])
        self.assertEqual(unit,"twinpanel-central-node-stage-19.service")

    def test_inactive_units_still_dispatch(self):
        for central,expected in ((False,("legacy",6)),(True,("central",19))):
            result,launches,_=self.run_scan(central=central,running=False)
            self.assertEqual(launches,[expected])
            self.assertEqual(result["dispatched"],[expected[1]])
            self.assertEqual(result["in_progress"],[])
            self.assertTrue(result["ok"])


if __name__ == "__main__":
    main()
