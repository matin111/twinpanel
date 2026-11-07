"""Regression checks for live Connection telemetry and English-number UI (V101).

Run without pytest: python3 -m unittest tests.test_connection_live_telemetry_v101
"""
from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app"
ROUTERS = ROOT / "routers"
SERVICES = ROOT / "services"


def source(directory: Path, filename: str) -> str:
    text = (directory / filename).read_text(encoding="utf-8")
    compile(text, filename, "exec")
    return text


class LiveConnectionTelemetryV101(unittest.TestCase):
    def test_xray_recent_traffic_presence_not_legacy_3_minute_cutoff(self):
        code = source(ROUTERS, "public_connection_live_v4.py")
        self.assertIn("_XRAY_TRAFFIC_ACTIVITY_SECONDS = 660", code)
        self.assertIn('recent_activity_rows.append(("xray", xray_recent))', code)
        self.assertIn("QuotaUsageEvent.accepted_bytes > 0", code)
        self.assertIn("QuotaUsageEvent.reported_at >= xray_activity_cutoff", code)
        self.assertIn("online_countries", code)
        self.assertIn('"online_countries": sorted(', code)

    def test_ui_status_cannot_claim_xray_socket_presence(self):
        code = source(ROUTERS, "public_connection_hub_live_v5.py")
        self.assertIn("key==='xray'?'فعال اخیراً':'آنلاین'", code)
        self.assertIn("Intl.NumberFormat('en-US'", code)
        self.assertNotIn("Intl.NumberFormat('fa-IR'", code)
        self.assertIn("item?.online_countries", code)

    def test_interface_digits_are_english_but_configuration_is_preserved(self):
        code = source(ROUTERS, "public_connection_unified_surface_dates_v80.py")
        self.assertIn("installEnglishInterfaceDigits();", code)
        self.assertIn("MutationObserver(records=>", code)
        self.assertIn("script,style,noscript,textarea,input,pre,code,samp,kbd,svg", code)
        self.assertIn('if(/(?:vless|vmess|trojan|hysteria2|wireguard|ss):', code)
        self.assertIn("node.nodeValue.replace(digits", code)
        self.assertIn("TWINPANEL_CONNECTION_ENGLISH_UI_DIGITS_V101", code)

    def test_accounting_probes_protocols_separately(self):
        code = source(SERVICES, "quota_node_sync.py")
        self.assertIn("source_protocols: set[str] | None", code)
        self.assertIn("ProtocolCredential.protocol.in_(allowed)", code)
        cisco = source(SERVICES, "quota_runtime_reconcile.py")
        self.assertIn("source_protocols=source", cisco)
        l2tp = source(SERVICES, "l2tp_quota_runtime_v113.py")
        self.assertIn("source_protocols={'l2tp'}", l2tp)

    def test_javascript_syntax(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js not installed")
        for filename in ("public_connection_live_v4.py",
                         "public_connection_hub_live_v5.py",
                         "public_connection_unified_surface_dates_v80.py"):
            code = source(ROUTERS, filename)
            for match in re.finditer(
                r'_(?:LIVE_)?SCRIPT\s*=\s*r?"""(.*?)"""', code, re.S
            ):
                fragment = match.group(1)
                if "<script" not in fragment:
                    continue
                js = fragment.split("<script", 1)[1].split(">", 1)[1].rsplit(
                    "</script>", 1
                )[0]
                process = subprocess.run(
                    [node, "--check"], input=js, capture_output=True,
                    text=True, check=False,
                )
                self.assertEqual(process.returncode, 0, process.stderr)


if __name__ == "__main__":
    unittest.main()
