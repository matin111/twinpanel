"""Regression: a Mieru/Sudoku install must not mark 11 protocols broken."""
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from app.models import NodeType
from app.protocol_account_registry import MODERN_PROTOCOL_KEYS
from app.protocol_catalog import PROTOCOL_CATALOG
from app.modern_protocol_runtime_v2 import SINGBOX_PROTOCOLS
from app.routers import modern_protocol_admin_v3
from app.services import new_node_modern_bootstrap_v1 as bootstrap


def full_plan():
    keys=sorted(MODERN_PROTOCOL_KEYS)
    return {
        "node_id":18,"protocols":keys,
        "ports":{k:int(PROTOCOL_CATALOG[k]["default_port"]) for k in keys},
        "profiles":{k:{"preset":"recommended","settings":{}} for k in keys},
        "sources":{k:{"mode":"central_catalog"} for k in keys},
        "already_online":[],"skipped_port_conflict":[],"skipped_no_template":[],
    }


class ModernCentralIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_mieru_failure_isolated_from_singbox_and_sudoku(self):
        db=MagicMock()
        groups=[]
        async def fake_install(*,node_id,payload,db):
            group=list(payload.protocols)
            groups.append(group)
            if group==["mieru"]:
                raise HTTPException(status_code=502,detail="SENSITIVE_CREDENTIAL")
            return {"failed_protocols":[],
                    "protocols":{k:{"ok":True,"port":full_plan()["ports"][k]}
                                 for k in group}}
        with (patch.object(bootstrap,"build_modern_bootstrap_plan",
                           return_value=full_plan()),
              patch.object(modern_protocol_admin_v3,"install",
                           side_effect=fake_install),
              patch("builtins.print") as logged):
            result=await bootstrap.bootstrap_new_exit_modern_protocols(db,18)
        self.assertFalse(result["ok"])
        self.assertEqual(result["attempted"],11)
        self.assertEqual(result["failed"],["mieru"])
        self.assertEqual(len(result["installed"]),10)
        self.assertEqual(set(groups[0]),set(SINGBOX_PROTOCOLS))
        self.assertEqual(len(groups),5)
        self.assertIn(["sudoku"],groups)
        self.assertEqual(result["errors"],{"mieru":"install_http_502"})
        db.rollback.assert_called_once()
        self.assertNotIn("SENSITIVE_CREDENTIAL",str(logged.call_args_list))

    async def test_missing_positive_listener_health_is_failure(self):
        db=MagicMock()
        p=full_plan()
        p["protocols"]=["sudoku"]
        async def empty(**kwargs):
            return {"failed_protocols":[],"protocols":{}}
        with (patch.object(bootstrap,"build_modern_bootstrap_plan",
                           return_value=p),
              patch.object(modern_protocol_admin_v3,"install",side_effect=empty)):
            result=await bootstrap.bootstrap_new_exit_modern_protocols(db,18)
        self.assertEqual(result["failed"],["sudoku"])
        self.assertFalse(result["ok"])

    async def test_other_standalones_continue_after_exception(self):
        db=MagicMock()
        p=full_plan()
        p["protocols"]=["amneziawg","mieru","sudoku","trusttunnel"]
        async def installer(*,node_id,payload,db):
            k=payload.protocols[0]
            if k=="amneziawg":
                raise OSError("PASSWORD_NOT_FOR_LOG")
            return {"failed_protocols":[],
                    "protocols":{k:{"ok":True,"port":p["ports"][k]}}}
        with (patch.object(bootstrap,"build_modern_bootstrap_plan",return_value=p),
              patch.object(modern_protocol_admin_v3,"install",side_effect=installer),
              patch("builtins.print") as logged):
            result=await bootstrap.bootstrap_new_exit_modern_protocols(db,18)
        self.assertEqual(result["failed"],["amneziawg"])
        self.assertEqual(set(result["installed"]),{"mieru","sudoku","trusttunnel"})
        self.assertNotIn("PASSWORD_NOT_FOR_LOG",str(logged.call_args_list))

    async def test_retry_same_errored_port_is_allowed(self):
        db=MagicMock()
        db.query.return_value.filter.return_value.first.return_value=(
            SimpleNamespace(id=18,node_type=NodeType.EXIT,retired_at=None))
        db.query.return_value.filter.return_value.all.return_value=[
            SimpleNamespace(protocol="sudoku",port=8453,status="error"),
            SimpleNamespace(protocol="anytls",port=8446,status="error"),
        ]
        p=bootstrap.build_modern_bootstrap_plan(db,18)
        self.assertIn("sudoku",p["protocols"])
        self.assertIn("anytls",p["protocols"])
        self.assertFalse(p["skipped_port_conflict"])

    async def test_other_protocol_port_cannot_be_stolen(self):
        db=MagicMock()
        db.query.return_value.filter.return_value.first.return_value=(
            SimpleNamespace(id=18,node_type=NodeType.EXIT,retired_at=None))
        db.query.return_value.filter.return_value.all.return_value=[
            SimpleNamespace(protocol="cisco",port=8446,status="online")
        ]
        p=bootstrap.build_modern_bootstrap_plan(db,18)
        self.assertNotIn("anytls",p["protocols"])
        self.assertEqual(p["skipped_port_conflict"][0]["protocol"],"anytls")


if __name__=="__main__":
    unittest.main()
