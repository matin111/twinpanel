"""Exercise real short-alias identity functions with temporary local state.

No live license, registration, VPN username, or production file is changed.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
IDENTITY = ROOT / "backend/app/central_app_identity.py"


def identity_functions(alias_file):
    source = IDENTITY.read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {
        "installation_namespace", "app_directory_namespace",
        "save_app_directory_alias", "app_reseller_prefix",
        "reseller_prefix", "app_namespace_from_username",
    }
    funcs = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name in names]
    scope = {
        "hashlib": hashlib, "json": json, "os": os, "re": re,
        "_APP_DIRECTORY_ALIAS_FILE": alias_file,
        "_APP_ALIAS_RE": re.compile(
            r"^TP(?:[A-F0-9]{6}|[A-F0-9]{8}|[A-F0-9]{10}|[A-F0-9]{12}|[A-F0-9]{14}|[A-F0-9]{16})$"
        ),
    }
    exec(compile(ast.Module(body=funcs, type_ignores=[]), str(IDENTITY), "exec"), scope)
    return scope


class ShortAppAliasContract(unittest.TestCase):
    def test_new_accounts_short_while_existing_vpn_prefix_stays_full(self):
        with tempfile.TemporaryDirectory() as temp:
            f = identity_functions(Path(temp) / "alias.json")
            full = f["installation_namespace"]("panel-a-installation")
            self.assertEqual(f["app_directory_namespace"]("panel-a-installation"), full)
            short = full[:8]
            f["save_app_directory_alias"]("panel-a-installation", short)
            self.assertEqual(f["app_directory_namespace"]("panel-a-installation"), short)
            self.assertEqual(f["app_reseller_prefix"]("panel-a-installation", 1), short + "_R1_")
            self.assertEqual(f["app_reseller_prefix"]("panel-a-installation", 2), short + "_R2_")
            self.assertEqual(f["reseller_prefix"]("panel-a-installation", 1), full + "_R1_")
            self.assertEqual(
                f["app_namespace_from_username"](short + "_R1_APP0123456789ABCDEF",
                                                  "panel-a-installation"), short
            )
            self.assertEqual(
                f["app_namespace_from_username"](full + "_R1_APP0123456789ABCDEF",
                                                  "panel-a-installation"), full
            )

    def test_wrong_installation_and_unassigned_alias_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            f = identity_functions(Path(temp) / "alias.json")
            full = f["installation_namespace"]("panel-a-installation")
            with self.assertRaises(ValueError):
                f["save_app_directory_alias"]("panel-a-installation", "TPFFFFFF")
            f["save_app_directory_alias"]("panel-a-installation", full[:8])
            other = f["installation_namespace"]("panel-b-installation")
            self.assertEqual(f["app_directory_namespace"]("panel-b-installation"), other)


if __name__ == "__main__":
    unittest.main()
