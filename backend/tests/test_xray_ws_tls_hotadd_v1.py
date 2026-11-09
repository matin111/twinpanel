"""Regression: TLS certificate must yield real WS + XHTTP + TCP TLS.

Tests use mocks/parse-only; they never install, restart or modify live nodes.
"""
from __future__ import annotations

import ast
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT=Path(__file__).resolve().parents[1]
MODULE=ROOT / "app" / "xray_tls_ws_hotadd_v1.py"


class TestSafeHotaddSource(unittest.TestCase):
    def test_node_script_is_valid_and_bounded(self):
        from app.xray_tls_ws_hotadd_v1 import _REMOTE
        ast.parse(_REMOTE.replace("__WS_PORT__","9444"))
        source=MODULE.read_text(encoding="utf-8")
        self.assertIn('"network":"ws"',_REMOTE)
        self.assertIn('"security":"tls"',_REMOTE)
        self.assertIn('"api","adi"',_REMOTE)
        self.assertIn('"api","rmi"',_REMOTE)
        self.assertIn('XRAY_WS_CONFIG_PORT_COLLISION',_REMOTE)
        self.assertIn('XRAY_WS_SOCKET_PORT_COLLISION',_REMOTE)
        self.assertIn('XRAY_WS_CERTIFICATE_NOT_READY',_REMOTE)
        self.assertIn('XRAY_WS_CONCURRENT_CONFIG_CHANGE',_REMOTE)
        self.assertIn('CONFIG.read_bytes()!=original',_REMOTE)
        self.assertNotIn('systemctl restart',_REMOTE)
        self.assertNotIn('systemctl stop',_REMOTE)
        self.assertIn('os.replace(staged,CONFIG)',_REMOTE)

    def test_source_preserves_other_provision_paths(self):
        source=(ROOT/"app"/"xray_node_domain_runtime.py").read_text(encoding="utf-8")
        ensure=source.split("async def _ensure_modern_xray_with_dedicated_domain(",1)[1].split(
            "def _node_payload_with_xray_domain(",1)[0]
        self.assertIn('if bool(state.get("tls_enabled")):',ensure)
        self.assertIn('if xray_modern_runtime.PROFILE_WS not in current:',ensure)
        self.assertIn('await ensure_websocket_tls(',ensure)
        self.assertIn('current.append(xray_modern_runtime.PROFILE_WS)',ensure)


class TestWebsocketTLSRuntime(unittest.IsolatedAsyncioTestCase):
    async def test_only_repairs_missing_ws_if_certificate_valid(self):
        from app import xray_node_domain_runtime as domain
        node=SimpleNamespace(xray_domain="v2uk.in88.sbs",public_domain="uk.in88.sbs")
        async def original(*args,**kwargs):
            return {"tls_enabled":True,"available_profiles":["xhttp_reality"]}
        with patch.object(domain,"_original_ensure_modern_xray",original), patch.object(
            domain.xray_modern_runtime,"_target_port",return_value=9444,
        ), patch(
            "app.xray_tls_ws_hotadd_v1.ensure_websocket_tls",
            new_callable=AsyncMock,return_value={"ready":True},
        ) as repair:
            state=await domain._ensure_modern_xray_with_dedicated_domain(
                object(),8443,node)
            self.assertEqual(state["available_profiles"],
                             ["xhttp_reality","websocket_tls"])
            repair.assert_awaited_once()
            self.assertEqual(repair.call_args.args[1],9444)

    async def test_healthy_tls_does_not_touch_service(self):
        from app import xray_node_domain_runtime as domain
        node=SimpleNamespace(xray_domain="v2de.in88.sbs",public_domain="de.in88.sbs")
        async def original(*args,**kwargs):
            return {"tls_enabled":True,
                    "available_profiles":["xhttp_reality","websocket_tls"]}
        with patch.object(domain,"_original_ensure_modern_xray",original),patch(
            "app.xray_tls_ws_hotadd_v1.ensure_websocket_tls",
            new_callable=AsyncMock,
        ) as repair:
            state=await domain._ensure_modern_xray_with_dedicated_domain(
                object(),8443,node)
            self.assertIn("websocket_tls",state["available_profiles"])
            repair.assert_not_awaited()

    async def test_no_certificate_does_not_install_fake_tls(self):
        from app import xray_node_domain_runtime as domain
        node=SimpleNamespace(xray_domain="v2fin.in88.sbs",public_domain="fin.in88.sbs")
        async def original(*args,**kwargs):
            return {"tls_enabled":False,"available_profiles":["xhttp_reality"]}
        with patch.object(domain,"_original_ensure_modern_xray",original),patch(
            "app.xray_tls_ws_hotadd_v1.ensure_websocket_tls",
            new_callable=AsyncMock,
        ) as repair:
            state=await domain._ensure_modern_xray_with_dedicated_domain(
                object(),8443,node)
            self.assertFalse(state["tls_enabled"])
            repair.assert_not_awaited()


if __name__=="__main__":
    unittest.main()
