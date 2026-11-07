"""Prevent XHTTP REALITY target fixes from invalidating old subscriber SNIs."""
from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "backend/app/xray_modern_runtime.py"
ADMIN = ROOT / "backend/app/xray_modern_admin.py"


def isolated_reality_names():
    source = RUNTIME.read_text(encoding="utf-8")
    tree = ast.parse(source)
    funcs = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"_clean_domain", "_reality_server_names"}
    ]
    namespace = {"re": re, "Any": Any, "XRAY_REALITY_SERVER_NAME": "www.microsoft.com"}
    exec(compile(ast.Module(body=funcs, type_ignores=[]), str(RUNTIME), "exec"), namespace)
    return namespace["_reality_server_names"]


class RealityNameAliasTests(unittest.TestCase):
    def test_new_sni_first_legacy_old_link_is_kept(self):
        fn = isolated_reality_names()
        state = {
            "reality_server_name": "www.microsoft.com",
            "reality_legacy_server_names": [
                "www.varzesh3.com", "www.microsoft.com", "www.varzesh3.com",
                "broken..domain.com", "bad value", "varzesh3.com",
            ],
        }
        self.assertEqual(fn(state), [
            "www.microsoft.com", "www.varzesh3.com", "varzesh3.com"
        ])
        self.assertEqual(fn({"reality_server_name": "www.microsoft.com"}), [
            "www.microsoft.com"
        ])
        with self.assertRaises(RuntimeError):
            fn({"reality_server_name": "bad..name", "reality_legacy_server_names": []})

    def test_generator_keeps_aliases_and_never_rotates_credentials(self):
        source = RUNTIME.read_text(encoding="utf-8")
        self.assertIn('"reality_legacy_server_names": legacy_reality_names', source)
        self.assertIn('"serverNames": _reality_server_names(state)', source)
        self.assertIn('"reality_private_key": private_key', source)
        self.assertIn('"short_id_xhttp": short_id_xhttp', source)
        self.assertIn('"xhttp_path": xhttp_path', source)
        self.assertIn('("mode", "stream-one")', source)

    def test_administration_apply_keeps_old_sni_and_checks_tls13_target(self):
        tree = ast.parse(ADMIN.read_text(encoding="utf-8"))
        apply_script = next(
            node.value.value for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "_XRAY_REALITY_APPLY_SCRIPT" for target in node.targets)
            and isinstance(node.value, ast.Constant)
        )
        compile(apply_script, "<xray-reality-apply>", "exec")
        self.assertIn('reality["serverNames"] = [name, *aliases]', apply_script)
        self.assertIn('state["reality_legacy_server_names"] = aliases', apply_script)
        self.assertIn('if tls.version() != "TLSv1.3"', apply_script)
        self.assertIn('reality["target"] = target', apply_script)
        # Old URI identity must never be rewritten or deleted by the target apply.
        self.assertNotIn('"clients" =', apply_script)


if __name__ == "__main__":
    unittest.main()
