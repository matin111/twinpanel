"""Regression for BBR opt-in limited to VLESS customer inbounds only."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "backend/scripts/xray_vless_inbound_bbr_v1.py"
RUNTIME = ROOT / "backend/app/xray_modern_runtime.py"
TCP_TLS = ROOT / "backend/app/xray_tcp_tls_v39.py"

spec = importlib.util.spec_from_file_location("vless_bbr_script", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def example():
    return {
        "inbounds": [
            {"tag": tag, "protocol": "vless", "port": port,
             "settings": {"clients": [{"id": f"uuid-{port}", "email": "kept"}]},
             "streamSettings": {
                 "network": network, "security": security,
                 "path": f"/keep/{port}", "sockopt": {"tcpKeepAliveIdle": 77},
             }}
            for (tag, (network, security)), port
            in zip(module.PUBLIC.items(), (9444, 9447, 9446))
        ] + [
            {"tag": "legacy-other", "protocol": "vless", "port": 8443,
             "settings": {"clients": [{"id": "legacy-uuid"}]},
             "streamSettings": {"network": "tcp", "security": "none"}},
            {"tag": "dokodemo", "protocol": "dokodemo-door", "port": 10085},
        ],
        "outbounds": [{"tag": "direct", "protocol": "freedom"}],
        "routing": {"domainStrategy": "AsIs"},
    }


class BBRScopeTest(unittest.TestCase):
    def test_only_three_customer_inbounds_are_modified(self):
        before = example()
        original = json.dumps(before, sort_keys=True)
        after, changed, ports = module.targeted_config(before)
        self.assertTrue(changed)
        self.assertEqual(set(ports), set(module.PUBLIC))
        self.assertEqual(json.dumps(before, sort_keys=True), original)
        self.assertEqual(after["inbounds"][3:], before["inbounds"][3:])
        self.assertEqual(after["outbounds"], before["outbounds"])
        self.assertEqual(after["routing"], before["routing"])
        for index in range(3):
            old = before["inbounds"][index]
            new = after["inbounds"][index]
            self.assertEqual(new["settings"], old["settings"])
            self.assertEqual(new["streamSettings"]["path"], old["streamSettings"]["path"])
            self.assertEqual(new["streamSettings"]["sockopt"]["tcpKeepAliveIdle"], 77)
            self.assertEqual(new["streamSettings"]["sockopt"]["tcpCongestion"], "bbr")
        again, changed_again, _ = module.targeted_config(after)
        self.assertFalse(changed_again)
        self.assertEqual(after, again)

    def test_refuses_incomplete_or_incompatible_inbounds(self):
        sample = example()
        sample["inbounds"].pop(0)
        with self.assertRaises(RuntimeError):
            module.targeted_config(sample)
        sample = example()
        sample["inbounds"][0]["streamSettings"]["sockopt"]["tcpCongestion"] = "reno"
        with self.assertRaises(RuntimeError):
            module.targeted_config(sample)
        sample = example()
        sample["inbounds"][0]["streamSettings"]["security"] = "none"
        with self.assertRaises(RuntimeError):
            module.targeted_config(sample)

    def test_future_xray_generators_keep_bbr_per_inbound(self):
        runtime = RUNTIME.read_text(encoding="utf-8")
        tcp = TCP_TLS.read_text(encoding="utf-8")
        for tag in ("vless-xhttp-reality", "vless-ws-tls"):
            section = runtime[runtime.index('"tag": "' + tag + '"'):]
            self.assertIn('"sockopt": {"tcpCongestion": "bbr"}', section[:550])
        self.assertIn('"sockopt": {{"tcpCongestion": "bbr"}}', tcp)
        # Do not change the OS default or apply BBR to unrelated services.
        helper = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn('sysctl -w net.ipv4.tcp_congestion_control', helper)
        self.assertNotIn('"tag": "vless-in"', json.dumps(module.PUBLIC))
        self.assertIn("time.monotonic() + timeout", helper)
        self.assertIn("time.sleep(0.4)", helper)


if __name__ == "__main__":
    unittest.main()
