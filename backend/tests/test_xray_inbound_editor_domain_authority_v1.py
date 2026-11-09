"""Regression for per-node Xray editor authority and foreign-draft leakage."""
from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, MagicMock, patch

from app import xray_modern_admin as editor


def _draft(hostname: str):
    return {
        "connection_domain": hostname,
        "tls_server_name": hostname,
        "reality_server_name": "www.microsoft.com",
        "reality_target": "www.microsoft.com:443",
        "transport": "tcp",
        "security": "tls",
        "inbounds": {
            key: {
                "connection_domain": hostname,
                "server_name": "www.microsoft.com"
                if key == "xhttp_reality" else hostname,
                "path": "",
                "target": "",
                "transport": "ws" if key == "ws_tls" else (
                    "xhttp" if key == "xhttp_reality" else "tcp"
                ),
                "security": "reality" if key == "xhttp_reality" else "tls",
            }
            for key in ("ws_tls", "tcp_tls", "xhttp_reality")
        },
    }


class EditorNodeDomainTests(IsolatedAsyncioTestCase):
    async def _get(self, *, node_id, configured, live_tls, draft):
        node = SimpleNamespace(
            id=node_id,
            xray_domain=configured,
            public_domain="other-general-node-domain.example.com",
        )
        db = MagicMock()
        db.execute.return_value.scalar_one_or_none.return_value = json.dumps(
            {"draft": draft}
        )
        conn = MagicMock()
        conn.wait_closed = AsyncMock()
        live = {
            "tls_enabled": True,
            "tls_domain": live_tls,
            "tls_sni_tcp": live_tls,
            "tls_sni_ws": live_tls,
            "ws_path": "/ws-kept",
            "xhttp_path": "/xh-kept",
            "reality_server_name": "www.microsoft.com",
            "reality_target": "www.microsoft.com:443",
        }
        with (
            patch.object(editor, "_node_or_404", return_value=node),
            patch.object(editor.account_delivery, "ssh_connect_saved",
                         new_callable=AsyncMock, return_value=conn),
            patch.object(editor.provision, "cmd",
                         new_callable=AsyncMock, return_value=json.dumps(live)),
        ):
            return await editor.get_xray_inbound_editor(node_id, db)

    async def test_usa_foreign_uk_draft_is_flagged_and_live_tls_not_falsified(self):
        state = await self._get(
            node_id=11, configured="v2usa.in88.sbs",
            live_tls="tunel.in88.sbs", draft=_draft("v2uk.in88.sbs"),
        )
        self.assertEqual(state["configured_xray_domain"], "v2usa.in88.sbs")
        self.assertEqual(state["active_tls_domain"], "tunel.in88.sbs")
        self.assertTrue(state["tls_domain_mismatch"])
        self.assertTrue(state["draft_domain_conflict"])
        self.assertEqual(
            state["defaults"]["inbounds"]["ws_tls"]["connection_domain"],
            "v2usa.in88.sbs",
        )
        self.assertEqual(
            state["defaults"]["inbounds"]["ws_tls"]["server_name"],
            "tunel.in88.sbs",
        )
        self.assertEqual(
            state["draft"]["inbounds"]["ws_tls"]["connection_domain"],
            "v2uk.in88.sbs",
        )  # preserved separately, never auto-loaded

    async def test_finland_live_tls_identity_and_saved_draft_match(self):
        state = await self._get(
            node_id=22, configured="v2fin.in88.sbs",
            live_tls="v2fin.in88.sbs", draft=_draft("v2fin.in88.sbs"),
        )
        self.assertFalse(state["tls_domain_mismatch"])
        self.assertFalse(state["draft_domain_conflict"])
        self.assertEqual(
            state["defaults"]["inbounds"]["tcp_tls"]["connection_domain"],
            "v2fin.in88.sbs",
        )
        self.assertEqual(
            state["defaults"]["inbounds"]["tcp_tls"]["server_name"],
            "v2fin.in88.sbs",
        )

    def test_drafts_from_other_exit_rejected_without_database_modification(self):
        self.assertTrue(editor._inbound_draft_uses_other_node_domain(
            _draft("v2uk.in88.sbs"), "v2usa.in88.sbs",
        ))
        self.assertFalse(editor._inbound_draft_uses_other_node_domain(
            _draft("v2fin.in88.sbs"), "v2fin.in88.sbs",
        ))
        self.assertFalse(editor._inbound_draft_uses_other_node_domain(
            None, "v2fin.in88.sbs",
        ))


class XrayCertHostnameCheckTests(IsolatedAsyncioTestCase):
    async def _evaluate(self, certificate_host: str):
        with tempfile.TemporaryDirectory(prefix="tp-xray-cert-gate-") as folder:
            cert = Path(folder) / "fullchain.pem"
            key = Path(folder) / "privkey.pem"
            args = [
                "openssl", "req", "-x509", "-newkey", "ec",
                "-pkeyopt", "ec_paramgen_curve:P-256",
                "-nodes", "-keyout", str(key), "-out", str(cert),
                "-days", "2", "-subj", f"/CN={certificate_host}",
                "-addext", f"subjectAltName=DNS:{certificate_host}",
            ]
            done = subprocess.run(args, capture_output=True, text=True, timeout=15)
            self.assertEqual(done.returncode, 0, done.stderr)
            async def run_local(_conn, command, *, check, **_kw):
                # Keep the exact remotely dispatched Bash logic while forcing
                # the test to access only our disposable certificate.
                start = command.index("for CERT in ")
                end = command.index("\ndo", start)
                script = command[:start] + (
                    "for CERT in " + str(cert)
                ) + command[end:]
                result = subprocess.run(
                    ["bash", "-c", script],
                    capture_output=True, text=True, timeout=12,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout
            with patch.object(editor.provision, "cmd", new=run_local):
                return await editor._certificate_available(
                    MagicMock(), "v2usa.in88.sbs",
                )

    async def test_matching_cert_is_accepted(self):
        self.assertTrue(await self._evaluate("v2usa.in88.sbs"))

    async def test_mismatched_cert_rejected_even_if_openssl_exits_zero(self):
        self.assertFalse(await self._evaluate("v2uk.in88.sbs"))


class XrayDomainWriteIsolationTests(TestCase):
    def test_domain_admin_does_not_update_node_public_domain(self):
        file = Path(__file__).resolve().parents[1] / "app/xray_modern_admin.py"
        content = file.read_text()
        save = content.split("def save_xray_domain(", 1)[1].split(
            '@router.get("/nodes/{node_id}/status")', 1
        )[0]
        self.assertIn("node.xray_domain = domain or None", save)
        self.assertNotIn("node.public_domain =", save)

    def test_ui_does_not_eagerly_load_saved_draft_over_live_settings(self):
        root = Path(__file__).resolve().parents[2]
        protocol = (
            root / "components/xray-inbound-editor-in-protocol.tsx"
        ).read_text()
        advanced = (
            root / "components/node-xray-domain-runtime-v33.tsx"
        ).read_text()
        self.assertIn("setDraft(value.defaults)", protocol)
        self.assertIn("value.draft?.inbounds", protocol)
        self.assertIn("draft_domain_conflict", protocol)
        self.assertIn("setInboundDraft(state.defaults)", advanced)
        self.assertNotIn("setInboundDraft(state.draft||state.defaults)", advanced)


if __name__ == "__main__":
    import unittest
    unittest.main()
