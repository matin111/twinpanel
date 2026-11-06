"""Regression guard: gRPC is neither provisioned nor delivered by V2Ray."""
import ast
import re
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

    def test_live_stored_vless_profiles_use_real_ingress_ports(self):
        helper = _function(ADAPTIVE, "_verified_stored_tunnel_endpoint_v47")
        ns = {
            "Any": Any,
            "urlsplit": urlsplit,
            "xray_modern_runtime": SimpleNamespace(
                PROFILE_WS="websocket_tls", PROFILE_XHTTP="xhttp_reality"
            ),
            "PROFILE_TCP_TLS": "tcp_tls",
        }
        exec(compile(ast.Module(body=[helper], type_ignores=[]), str(ADAPTIVE), "exec"), ns)
        resolve = ns["_verified_stored_tunnel_endpoint_v47"]
        live = {"server": "vtray.in88.sbs"}
        for profile, base in (
            ("websocket_tls", 26000),
            ("xhttp_reality", 24000),
            ("tcp_tls", 28000),
        ):
            saved = {"uri": f"vless://customer@vtray.in88.sbs:{base + 6}?type=ws"}
            self.assertEqual(resolve(live, saved, profile, 6), ("vtray.in88.sbs", base + 6))
            self.assertIsNone(resolve({"server": "other.example"}, saved, profile, 6))
            self.assertIsNone(resolve({"server": "vtray.in88.sbs", "delivery_mode": "direct"}, saved, profile, 6))
            self.assertIsNone(resolve(live, {"uri": f"vless://customer@vtray.in88.sbs:{base + 7}"}, profile, 6))
        self.assertIsNone(
            resolve(live, {"uri": "vless://customer@vtray.in88.sbs:25006?type=grpc"}, "grpc_reality", 6)
        )

    def test_migration_validates_config_and_preserves_other_inbounds(self):
        source = MIGRATION.read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn("vless-grpc-reality", source)
        self.assertIn("_validate_file(stage_config)", source)
        self.assertIn('subprocess.run(["systemctl", "restart", "xray"]', source)
        self.assertIn('shutil.copy2(backup_config, CONFIG)', source)


if __name__ == "__main__":
    unittest.main()
