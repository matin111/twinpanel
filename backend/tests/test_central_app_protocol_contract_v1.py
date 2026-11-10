"""Static cross-contract tests requiring no production database or secrets."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PANEL = ROOT / "backend/app/routers/public_connection_modern_delivery_v13.py"
SERVER = ROOT / "backend/app/central_app_protocols.py"
API = ROOT / "backend/app/routers/central_app_v1.py"
CLIENT = ROOT / "clients/twinconnect/lib/protocols.dart"
BRIDGE = ROOT / "clients/twinconnect/lib/native_vpn_bridge.dart"


def _assignment(module: ast.Module, name: str):
    for node in module.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                return node.value
    raise AssertionError(f"assignment {name} missing")


def _canonical_codes() -> set[str]:
    tree = ast.parse(PANEL.read_text(encoding="utf-8"))
    codes = []
    for name in ("CLASSIC_PROTOCOLS", "MODERN_PROTOCOLS"):
        codes.extend(ast.literal_eval(_assignment(tree, name)))
    return set(codes)


def _contract_codes() -> set[str]:
    tree = ast.parse(SERVER.read_text(encoding="utf-8"))
    constructors = _assignment(tree, "_PROTOCOLS").elts
    codes = []
    for node in constructors:
        if not isinstance(node, ast.Call) or not node.args:
            raise AssertionError("invalid contract constructor")
        codes.append(ast.literal_eval(node.args[0]))
    if len(codes) != len(set(codes)):
        raise AssertionError("duplicate contract codes")
    return set(codes)


class AllProtocolContractTests(unittest.TestCase):
    def test_all_sixteen_codes_match_existing_panel_and_flutter(self):
        panel = _canonical_codes()
        server = _contract_codes()
        dart = CLIENT.read_text(encoding="utf-8")
        self.assertEqual(len(panel), 16)
        self.assertEqual(server, panel)
        for protocol in server:
            with self.subTest(protocol=protocol):
                self.assertIn(f"code: '{protocol}'", dart)
        self.assertEqual(dart.count("VpnProtocolDefinition("), 17)  # constructor + 16 rows

    def test_engine_separation_for_non_singbox_native_protocols(self):
        source = SERVER.read_text(encoding="utf-8")
        for code, family in {
            "cisco": "openconnect",
            "openvpn": "openvpn",
            "wireguard": "wireguard",
            "l2tp": "native_l2tp",
            "v2ray": "xray",
            "mieru": "mieru",
            "trusttunnel": "trusttunnel",
            "amneziawg": "amneziawg",
            "sudoku": "sudoku",
        }.items():
            with self.subTest(protocol=code):
                self.assertIn(f'ProtocolContract("{code}",', source)
                self.assertIn(f'"{family}"', source)
        self.assertIn('ProtocolContract("shadowtls", "ShadowTLS", "singbox", "singbox_chain"', source)
        self.assertIn('ProtocolContract("v2ray", "V2Ray / Xray", "xray", "xray_profiles"', source)

    def test_protocol_availability_does_not_return_secrets(self):
        source = API.read_text(encoding="utf-8")
        block = source.split('@router.post("/public/protocols")', 1)[1].split('@router.post("/public/profiles")', 1)[0]
        self.assertIn("_verified_protocol_subscription(payload, db)", block)
        self.assertIn("SubscriptionProtocol.subscription_id == subscription_id", source)
        self.assertIn("ProtocolCredential.is_active.is_(True)", block)
        self.assertIn("protocol_catalog(selected, configured)", block)
        self.assertIn('"Cache-Control": "no-store"', block)
        self.assertNotIn("_stored_info(", block)
        self.assertNotIn("share_token", block)

    def test_secret_profiles_require_subscription_and_one_protocol(self):
        source = API.read_text(encoding="utf-8")
        block = source.split('@router.post("/public/profiles")', 1)[1]
        self.assertIn("_verified_protocol_subscription(payload, db)", block)
        self.assertIn("protocol not in _selected_client_protocols(db, sub.id)", block)
        self.assertIn("no-store, private, max-age=0", block)
        self.assertIn("_stored_info(db, sub)", block)
        self.assertIn("_subscription_and_payload(", block)
        self.assertIn("_v2ray_items(projected)", block)
        self.assertIn("PROFILE_RESPONSE_TOO_LARGE", block)
        self.assertNotIn("db.commit()", block)
        self.assertIn("hmac.compare_digest(", source)
        self.assertIn("CENTRAL_APP_NOT_INCLUDED", source)

    def test_native_client_never_reports_available_from_panel_metadata(self):
        client = CLIENT.read_text(encoding="utf-8")
        bridge = BRIDGE.read_text(encoding="utf-8")
        self.assertIn("clientEngineReady: false", client)
        self.assertIn("if (!capabilities.engineReady || !capabilities.fullTunnel)", bridge)
        self.assertIn("requireSafeToConnect(policy, capabilities)", bridge)
        self.assertIn("nativeProtocols.supports(protocol.code)", bridge)


if __name__ == "__main__":
    unittest.main()
