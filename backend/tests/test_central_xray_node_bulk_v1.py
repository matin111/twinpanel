"""Xray central identity safety: never rotate UUIDs on existing Exit items."""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from uuid import uuid4

tmp=tempfile.TemporaryDirectory(prefix="tp-central-xray-test-")
os.environ.setdefault("APP_SECRET_KEY","ci-only-xray-stage")
os.environ.setdefault("DATABASE_URL",f"sqlite+pysqlite:///{Path(tmp.name)/'bootstrap.db'}")
os.environ.setdefault("NODE_AGENT_SHARED_SECRET","ci-only-xray-node")

src=Path(__file__).resolve().parents[1]/"scripts"/"twinpanel_central_xray_node_bulk_v1.py"
spec=importlib.util.spec_from_file_location("central_xray_stage_test_target",src)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class CentralXrayTests(unittest.TestCase):
    def test_explicit_apply_requires_matching_target(self):
        self.assertFalse(mod.parser(["--node-id","14"]).apply)
        with self.assertRaises(SystemExit):
            mod.parser(["--node-id","14","--apply"])
        with self.assertRaises(SystemExit):
            mod.parser(["--node-id","14","--apply","--confirm-node-id","13"])

    def test_published_xray_runs_without_repeated_sixteen_protocol_audit(self):
        db=MagicMock()
        node=MagicMock(show_to_users=True)
        db.get.return_value=node
        with (patch.object(mod,"SessionLocal") as session,
              patch.object(mod,"allow_central_node",return_value=True),
              # This unit test covers central readiness dispatch, NOT the
              # PostgreSQL-only ORM mapper installer. Its real integration
              # path is tested separately against PostgreSQL.
              patch("scripts.twinpanel_hidden_node_install_finish_v1._activate_xray_install_runtime"),
              patch.object(mod,"verify_new_exit_readiness",
                           new_callable=AsyncMock) as health,
              patch.object(mod,"run_one",new_callable=AsyncMock,
                           return_value=0) as run_one):
            session.return_value.__enter__.return_value=db
            import asyncio
            asyncio.run(mod.run(14,100,True,True))
            health.assert_not_awaited()
            run_one.assert_awaited_once()

    def test_hidden_xray_preserves_initial_protocol_readiness_guard(self):
        db=MagicMock()
        node=MagicMock(show_to_users=False)
        db.get.return_value=node
        with (patch.object(mod,"SessionLocal") as session,
              patch.object(mod,"allow_central_node",return_value=True),
              # This unit test covers central readiness dispatch, NOT the
              # PostgreSQL-only ORM mapper installer. Its real integration
              # path is tested separately against PostgreSQL.
              patch("scripts.twinpanel_hidden_node_install_finish_v1._activate_xray_install_runtime"),
              patch.object(mod,"verify_new_exit_readiness",
                           new_callable=AsyncMock,return_value={"ok":False}) as health,
              patch.object(mod,"run_one",new_callable=AsyncMock) as run_one):
            session.return_value.__enter__.return_value=db
            import asyncio
            with self.assertRaisesRegex(RuntimeError,
                                        "XRAY_LISTENER_NOT_VERIFIED"):
                asyncio.run(mod.run(14,100,True,True))
            health.assert_awaited_once()
            run_one.assert_not_awaited()

    def test_published_xray_is_not_starved_by_legacy_priority_flag(self):
        import asyncio
        db=MagicMock()
        live=MagicMock(show_to_users=True)
        selection=[(1,str(uuid4()),{"node_id":14})]
        with (patch.object(mod,"plan",return_value=(live,1,selection,{"tcp_reality"})),
              patch.object(mod,"new_account_work_has_priority",
                           return_value=True),
              patch.object(mod.ad,"ssh_connect_saved",
                           new_callable=AsyncMock,
                           side_effect=RuntimeError("XRAY_HOT_APPLY_REACHED"))):
            with self.assertRaisesRegex(RuntimeError,"XRAY_HOT_APPLY_REACHED"):
                asyncio.run(mod.run_one(db,14,100,True))

    def test_hidden_initial_xray_import_keeps_customer_priority(self):
        import asyncio
        db=MagicMock()
        hidden=MagicMock(show_to_users=False)
        selection=[(1,str(uuid4()),{"node_id":14})]
        with (patch.object(mod,"plan",return_value=(hidden,1,selection,{"tcp_reality"})),
              patch.object(mod,"new_account_work_has_priority",
                           return_value=True),
              patch.object(mod.ad,"ssh_connect_saved",
                           new_callable=AsyncMock) as connect):
            with self.assertRaisesRegex(RuntimeError,
                                        "PAID_ACCOUNT_PROVISIONING_HAS_PRIORITY"):
                asyncio.run(mod.run_one(db,14,100,True))
            connect.assert_not_awaited()

    def test_prefer_node_owned_uuid_when_repairing_partial(self):
        uuids=[str(uuid4()) for _ in range(3)]
        items=[
            {"node_id":1,"uuid":uuids[0],"server":"existing"},
            {"node_id":6,"uuid":uuids[1],"server":"existing"},
            {"node_id":14,"uuid":uuids[2],"profiles":[]},
        ]
        snapshot=[dict(x) for x in items]
        self.assertEqual(mod.choose_existing_uuid(items,14),uuids[2])
        self.assertEqual(items,snapshot)

    def test_deterministic_uuid_selection_without_creating_new_identity(self):
        a,b=str(uuid4()),str(uuid4())
        items=[{"node_id":9,"uuid":a},{"node_id":6,"uuid":b}]
        self.assertEqual(mod.choose_existing_uuid(items,14),b)
        self.assertEqual(mod.choose_existing_uuid(list(reversed(items)),14),b)
        with self.assertRaisesRegex(RuntimeError,"NO_REUSABLE"):
            mod.choose_existing_uuid([],14)

    def test_refuse_conflicting_uuid_already_on_same_node(self):
        a,b=str(uuid4()),str(uuid4())
        items=[{"node_id":14,"uuid":a},{"node_id":14,"uuid":b}]
        with self.assertRaisesRegex(RuntimeError,"CONFLICTING_UUIDS"):
            mod.choose_existing_uuid(items,14)

    def test_hot_batch_has_no_xray_restart_and_is_bounded(self):
        batch=[(str(uuid4()),f"mv-{i}@twinpanel") for i in range(1,101)]
        script=mod.staged_hot_script(batch)
        compile(script,"<xray-remote>","exec")
        self.assertIn("len(CLIENTS) > 100",script)
        self.assertNotIn('["systemctl", "restart", "xray"]',script)
        with self.assertRaises(ValueError):
            mod.staged_hot_script(batch+[(str(uuid4()),"mv-101@twinpanel")])
        with self.assertRaises(ValueError):
            mod.staged_hot_script([(batch[0][0],batch[0][1]),batch[0]])
        with self.assertRaises(ValueError):
            mod.staged_hot_script([(str(uuid4()),"invalid-email")])


if __name__=="__main__":
    unittest.main()
