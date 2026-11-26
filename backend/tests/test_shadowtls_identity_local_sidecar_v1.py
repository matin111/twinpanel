"""Safety contract for separate loopback ShadowTLS identity staging."""
from __future__ import annotations

import base64
import importlib.util
import json
import secrets
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
SRC = BASE/"scripts/twinpanel_shadowtls_identity_local_sidecar_v1.py"
SPEC = importlib.util.spec_from_file_location("tp_shadow_canary_service",SRC)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SidecarSafetyTests(TestCase):
    def fixture(self):
        return {
            "log":{"level":"warn"},
            "inbounds":[
                {"type":"shadowtls","tag":"twinpanel-shadowtls-in",
                 "listen":"0.0.0.0","listen_port":8448,"version":3,
                 "users":[{"name":"tp-sub-1","password":"test-outer-one"},
                          {"name":"tp-sub-2","password":"test-outer-two"},
                          {"name":"twinpanel-bootstrap","password":"not-routable"}],
                 "handshake":{"server":"www.example.com","server_port":443},
                 "detour":"twinpanel-shadowtls-inner"},
                {"type":"shadowsocks","tag":"twinpanel-shadowtls-inner",
                 "listen":"127.0.0.1","method":"aes-256-gcm",
                 "password":"test-old-inner"}],
            "outbounds":[{"type":"direct","tag":"direct"}],
            "route":{"final":"direct"},
        }

    def test_stager_uses_only_isolated_listener_and_real_account_identities(self):
        src=self.fixture()
        unchanged=json.dumps(src,sort_keys=True)
        keys={
            "server_key":base64.b64encode(secrets.token_bytes(16)).decode(),
            "derivation_secret":base64.b64encode(secrets.token_bytes(32)).decode(),
            "api_secret":"never-print-this",
        }
        cfg,n=MODULE.make_config(src,keys)
        self.assertEqual(json.dumps(src,sort_keys=True),unchanged)
        self.assertEqual(n,2)
        self.assertEqual(len(cfg["inbounds"]),2)
        self.assertEqual([x["tag"] for x in cfg["inbounds"]],
                         ["twinpanel-shadowtls-identity-in","twinpanel-shadowtls-identity-inner"])
        self.assertTrue(all(x.get("listen")=="127.0.0.1" for x in cfg["inbounds"]))
        self.assertEqual(cfg["inbounds"][0]["listen_port"],19448)
        self.assertEqual(cfg["outbounds"],[{"type":"direct","tag":"direct"}])
        self.assertEqual(cfg["route"],{"final":"direct"})
        self.assertEqual(cfg["services"][0]["listen_port"],19096)
        self.assertEqual(cfg["services"][0]["listen"],"127.0.0.1")
        self.assertNotIn("twinpanel-bootstrap",str(cfg["inbounds"][1]))
        self.assertNotIn("test-old-inner",str(cfg))
        self.assertNotIn("test-outer-one",str(cfg["inbounds"][1]))

    def test_future_delivery_and_accounting_both_default_off(self):
        source=SRC.read_text()
        self.assertIn('"delivery_enabled": False',source)
        self.assertIn('"public_listener": False',source)
        self.assertIn('"accounting_enabled": False',source)
        self.assertIn('if port_occupied(PORT) or port_occupied(API_PORT)',source)
        self.assertIn('if UNIT.exists()',source)
        self.assertIn('if not apply:',source)

    def test_sidecar_code_never_restarts_live_vpn_daemon(self):
        s=SRC.read_text()
        self.assertNotIn('["systemctl","restart","twinpanel-sing-box"]',s)
        self.assertNotIn('["systemctl","restart","twinpanel-api"]',s)
        self.assertNotIn('["systemctl","restart","xray"]',s)
        self.assertIn('"existing_vpn_services_restarted": False',s)


if __name__=="__main__":
    main()
