"""Xray central identity safety: never rotate UUIDs on existing Exit items."""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
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
