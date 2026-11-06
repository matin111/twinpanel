"""Regression guard: gRPC is neither provisioned nor delivered by V2Ray."""
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlsplit
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "backend/app/xray_modern_runtime.py"
ADAPTIVE = ROOT / "backend/app/xray_adaptive_three_profiles_v47.py"
ADMIN = ROOT / "backend/app/xray_modern_admin.py"
PUBLIC = ROOT / "backend/app/routers/public_connection_multilink_v7.py"
MIGRATION = ROOT / "backend/scripts/remove_v2ray_grpc_inbound.py"


def _function(path, name):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == name)


class V2RayNoGrpcTests(unittest.TestCase):
    def test_new_xray_config_has_no_grpc_listener_or_route(self):
        source = RUNTIME.read_text(encoding="utf-8")
        ensure = source[source.index("async def _ensure_modern_xray("):source.index("async def _install_xray_modern(")]
        routes = source[source.index("def _service_routes_modern("):source.index("def _modern_item_present(")]
        self.assertNotIn('"tag": "vless-grpc-reality"', ensure)
        self.assertNotIn("PROFILE_GRPC", ensure)
        self.assertNotIn("PROFILE_GRPC", routes)
        self.assertIn('"tag": "vless-xhttp-reality"', ensure)
        self.assertIn('PROFILE_WS', ensure)

    def test_new_xray_state_and_provisioning_dont_create_grpc(self):
        source = RUNTIME.read_text(encoding="utf-8")
        generator = source[source.index("def _state_generator_script("):source.index("def _merge_clients_script(")]
        provision = source[source.index("async def _xray_account_modern("):source.index("def _modern_item_present(")]
        self.assertNotIn('"short_id_grpc":', generator)
        self.assertNotIn('"grpc_service":', generator)
        self.assertNotIn('order.append(PROFILE_GRPC)', provision)

    def test_no_domain_profile_policy_uses_xhttp_and_tcp_reality(self):
        source = ADAPTIVE.read_text(encoding="utf-8")
        self.assertNotIn("PROFILE_GRPC", source)
        self.assertIn("PROFILE_TCP_REALITY", source)
        self.assertIn("PROFILE_XHTTP", source)

    def test_inbound_editor_only_allows_supported_transports(self):
        source = ADMIN.read_text(encoding="utf-8")
        self.assertNotIn("grpc", source.lower())
        self.assertIn('if len(inbounds) != 1:', source)

    def test_old_stored_grpc_uri_does_not_escape_subscription(self):
        tree = ast.parse(PUBLIC.read_text(encoding="utf-8"))
        funcs = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name in {"_is_deprecated_grpc_uri", "_item_v2ray_uris"}
        ]
        ns = {
            "Any": Any,
            "parse_qsl": parse_qsl,
            "urlsplit": urlsplit,
            "xray_delivery": SimpleNamespace(
                _customer_profiles=lambda item: item.get("profiles", [])
            )
        }
        exec(compile(ast.Module(body=funcs, type_ignores=[]), str(PUBLIC), "exec"), ns)
        item = {"profiles": [
            {"uri": "vless://user@host:443?type=grpc&security=reality"},
            {"uri": "vless://user@host:443?type=ws&security=tls"},
            {"uri": "vless://user@host:443?type=xhttp&security=reality"},
        ]}
        links = ns["_item_v2ray_uris"](item)
        self.assertEqual(len(links), 2)
        self.assertTrue(all("type=grpc" not in link for link in links))
        self.assertEqual(
            ns["_item_v2ray_uris"]({"uri": "vless://user@host:443?type=grpc"}),
            [],
        )

    def test_inbound_editor_preserves_live_file_mode_and_owner(self):
        source = ADMIN.read_text(encoding="utf-8")
        self.assertIn("original_modes[path] = metadata", source)
        self.assertIn("os.chown(stage, metadata.st_uid, metadata.st_gid)", source)
        self.assertIn("os.chmod(stage, stat.S_IMODE(metadata.st_mode))", source)
        self.assertIn("os.chown(path, metadata.st_uid, metadata.st_gid)", source)
        self.assertIn("os.chmod(path, stat.S_IMODE(metadata.st_mode))", source)
        self.assertIn("Xray must be active before applying an inbound edit", source)

    def test_cleanup_preserves_xray_file_ownership_and_mode(self):
        source = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("def _clone_permissions(", source)
        self.assertIn("stat.S_IMODE(metadata.st_mode)", source)
        self.assertIn("_clone_permissions(stage_config, config_stat)", source)
        self.assertIn("_clone_permissions(stage_state, state_stat)", source)
        self.assertIn("_clone_permissions(CONFIG, config_stat)", source)
        self.assertIn("_clone_permissions(STATE, state_stat)", source)
        self.assertIn('raise RuntimeError("Xray is not active;', source)
        self.assertIn('raise RuntimeError("Xray config changed during cleanup staging")', source)

    def test_xray_client_sync_skips_unchanged_credentials_without_file_write(self):
        source = RUNTIME.read_text(encoding="utf-8")
        sync_function = _function(RUNTIME, "_client_sync_script")
        ns = {}
        exec(compile(ast.Module(body=[sync_function], type_ignores=[]), str(RUNTIME), "exec"), ns)
        make_script = ns["_client_sync_script"]
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.json"
            template = {
                "inbounds": [
                    {
                        "tag": f"vless-{index}",
                        "protocol": "vless",
                        "settings": {
                            "clients": [{"id": "other", "email": "other@example", "level": 0}]
                        },
                    }
                    for index in range(3)
                ] + [{"tag": "api", "protocol": "dokodemo-door"}],
            }
            config.write_text(json.dumps(template), encoding="utf-8")
            os.chmod(config, 0o640)
            path_to_patch = 'path = Path("/usr/local/etc/xray/config.json")'

            def run_sync(uuid):
                script = make_script(uuid, "mv-3594@twinpanel")
                self.assertIn(path_to_patch, script)
                script = script.replace(path_to_patch, f"path = Path({str(config)!r})", 1)
                result = subprocess.run(
                    [sys.executable, "-c", script],
                    check=True, capture_output=True, text=True, timeout=10,
                )
                return json.loads(result.stdout.strip().splitlines()[-1])

            self.assertTrue(run_sync("first-uuid")["changed"])
            first_data = config.read_bytes()
            first_mtime = config.stat().st_mtime_ns
            self.assertFalse(run_sync("first-uuid")["changed"])
            self.assertEqual(config.read_bytes(), first_data)
            self.assertEqual(config.stat().st_mtime_ns, first_mtime)
            self.assertEqual(config.stat().st_mode & 0o777, 0o640)

            self.assertTrue(run_sync("new-uuid")["changed"])
            new_config = json.loads(config.read_text(encoding="utf-8"))
            for inbound in new_config["inbounds"][:3]:
                matches = [
                    x for x in inbound["settings"]["clients"]
                    if x["email"] == "mv-3594@twinpanel"
                ]
                self.assertEqual(len(matches), 1)
                self.assertEqual(matches[0]["id"], "new-uuid")
            self.assertEqual(new_config["inbounds"][-1], template["inbounds"][-1])
            self.assertIn('if bool(sync_result.get("changed")):', source)

    def test_migration_validates_config_and_preserves_other_inbounds(self):
        source = MIGRATION.read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn("vless-grpc-reality", source)
        self.assertIn("_validate_file(stage_config)", source)
        self.assertIn('subprocess.run(["systemctl", "restart", "xray"]', source)
        self.assertIn('shutil.copy2(backup_config, CONFIG)', source)


if __name__ == "__main__":
    unittest.main()
