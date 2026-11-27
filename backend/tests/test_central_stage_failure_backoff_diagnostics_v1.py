"""Unit regression for rate-limiting costly failed stages and safe diagnostics."""
from __future__ import annotations

import ast
import importlib.util
import re
import tempfile
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
COOLDOWN_PATH=BASE/"app/services/central_stage_failure_backoff_v1.py"
ENGINE_PATH=BASE/"app/services/central_node_runtime_engine_v1.py"
STAGE_PATH=BASE/"scripts/twinpanel_central_node_stage_v1.py"
LAUNCHER_PATH=BASE/"app/services/central_node_stage_launcher_v1.py"


def isolated_stage():
    spec=importlib.util.spec_from_file_location("tp_central_backoff_isolated",COOLDOWN_PATH)
    assert spec is not None and spec.loader is not None
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def failure_class_parser():
    tree=ast.parse(ENGINE_PATH.read_text())
    fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef)
            and x.name=="_safe_failure_codes")
    namespace={"re":re}
    exec(compile(ast.fix_missing_locations(ast.Module(
        body=[ast.ImportFrom(module="__future__",names=[ast.alias(name="annotations")],level=0),fn],
        type_ignores=[])),str(ENGINE_PATH),"exec"),namespace)
    return namespace["_safe_failure_codes"]


class CentralFailureCooldownTests(TestCase):
    def test_failed_stage_is_backed_off_and_success_clears_marker(self):
        m=isolated_stage()
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(m,"FOLDER",Path(folder)):
                m.record_result(28,2,at=1000.0)
                path=Path(folder)/"node-28.json"
                self.assertTrue(path.is_file())
                self.assertEqual(path.stat().st_mode & 0o777,0o600)
                self.assertTrue(m.recently_failed(28,at=1001))
                self.assertTrue(m.recently_failed(28,at=1599))
                self.assertFalse(m.recently_failed(28,at=1600))
                self.assertFalse(m.recently_failed(29,at=1000))
                m.record_result(28,0,at=1601)
                self.assertFalse(path.exists())
                self.assertFalse(m.recently_failed(28,at=1601))

    def test_invalid_record_or_symlink_does_not_trigger_storm(self):
        m=isolated_stage()
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(m,"FOLDER",Path(folder)):
                m.record_result(1,2,at=1000)
                target=Path(folder)/"node-1.json"
                target.write_text("not-json")
                with self.assertRaisesRegex(RuntimeError,"MARKER_INVALID"):
                    m.recently_failed(1,at=1050)
                target.unlink()
                target.symlink_to("/etc/passwd")
                with self.assertRaisesRegex(RuntimeError,"MARKER_INVALID"):
                    m.recently_failed(1,at=1050)
                with self.assertRaisesRegex(RuntimeError,"MARKER_INVALID"):
                    m.record_result(1,0,at=1060)

    def test_no_implicit_success_or_subscription_write(self):
        stage=STAGE_PATH.read_text()
        launcher=LAUNCHER_PATH.read_text()
        self.assertIn("record_result(args.node_id, outcome)",stage)
        self.assertIn("if not initial_full and recently_failed(node_id):",launcher)
        self.assertIn("CENTRAL_STAGE_RECENT_FAILURE_COOLDOWN",launcher)
        self.assertNotIn("mark_central_applied",COOLDOWN_PATH.read_text())
        self.assertNotIn("QuotaNodeCommand",COOLDOWN_PATH.read_text())


class SafeDiagnosticTests(TestCase):
    def test_json_and_python_literal_safe_stops_are_classified(self):
        fn=failure_class_parser()
        self.assertEqual(
            fn(b'CENTRAL_MIERU_SAFE_STOP {"node_id":28,"error_type":"RuntimeError"}\n',2),
            ["EXCEPTION_RUNTIMEERROR"],
        )
        self.assertEqual(
            fn(b"CENTRAL_XRAY_SAFE_STOP {'node_id': 30, 'error_type': 'HTTPException'}\n",2),
            ["EXCEPTION_HTTPEXCEPTION"],
        )
        self.assertEqual(
            fn(b'CENTRAL_WIREGUARD_SAFE_STOP {"reason":"SAFE_WIREGUARD_PEER_MISSING"}\n',2),
            ["SAFE_WIREGUARD_PEER_MISSING"],
        )

    def test_does_not_print_secrets_or_arbitrary_exception_text(self):
        fn=failure_class_parser()
        payload=b'SECRET customer-password: abc\nTraceback secret=foo\n'
        self.assertEqual(fn(payload,2),["ADAPTER_FAILED_NO_SAFE_STOP"])
        self.assertEqual(
            fn(b'CENTRAL_MIERU_SAFE_STOP {"error_type":"RuntimeError","password":"topsecret"}',2),
            ["EXCEPTION_RUNTIMEERROR"],
        )
        self.assertEqual(fn(payload,0),[])


if __name__=="__main__":
    main()
