"""A node-owned certificate must survive every Xray protocol Repair.

No SSH, live nodes, source configs or customer accounts are touched: the real
generated installer executes against fake paths in a disposable directory.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from app.xray_modern_runtime import _state_generator_script


class RetainedManagedCertificateTests(unittest.TestCase):
    DOMAIN="v2fin.in88.sbs"

    def _run(self, root, *, domain=None):
        root=Path(root)
        state=root/"twinpanel-modern-state.json"
        certdir=root/"twinpanel-tls"
        source=_state_generator_script(domain or self.DOMAIN)
        source=source.replace(
            "/usr/local/etc/xray/twinpanel-modern-state.json", str(state)
        ).replace(
            "/usr/local/etc/xray/twinpanel-tls",str(certdir)
        ).replace(
            "/etc/letsencrypt/live/",str(root/"no-letsencrypt")+"/"
        ).replace(
            "/root/.acme.sh/",str(root/"no-acme")+"/"
        )
        script=root/"generated-state.py"
        script.write_text(source)
        return subprocess.run(
            [sys.executable,str(script)],capture_output=True,text=True,timeout=15,
        )

    @staticmethod
    def _state(path, *, previously_tls=False):
        obj={
            "reality_private_key":"a"*43,
            "reality_password":"b"*43,
            "reality_target":"www.microsoft.com:443",
            "reality_server_name":"www.microsoft.com",
            "short_id_xhttp":"1122334455667788",
            "xhttp_path":"/xh-12345678",
            "ws_path":"/ws-12345678",
            "httpupgrade_path":"/hu-12345678",
            "tls_enabled":previously_tls,
        }
        if previously_tls:
            obj.update(
                tls_domain=RetainedManagedCertificateTests.DOMAIN,
                managed_cert="/unused/previous/fullchain.pem",
            )
        path.write_text(json.dumps(obj))

    @staticmethod
    def _self_signed(cert_dir, hostname):
        cert_dir.mkdir(parents=True)
        result=subprocess.run([
            "openssl","req","-x509","-newkey","ec",
            "-pkeyopt","ec_paramgen_curve:P-256","-nodes",
            "-keyout",str(cert_dir/"privkey.pem"),
            "-out",str(cert_dir/"fullchain.pem"),
            "-days","2","-subj",f"/CN={hostname}",
            "-addext",f"subjectAltName=DNS:{hostname}",
        ],capture_output=True,text=True,timeout=12)
        if result.returncode:
            raise RuntimeError(result.stderr[-300:])

    def test_valid_managed_cert_survives_repair_when_prior_state_was_downgraded(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            certdir=root/"twinpanel-tls"
            self._self_signed(certdir,self.DOMAIN)
            state=root/"twinpanel-modern-state.json"
            self._state(state,previously_tls=False)
            key_before=(certdir/"privkey.pem").read_bytes()
            cert_before=(certdir/"fullchain.pem").read_bytes()
            result=self._run(root)
            self.assertEqual(result.returncode,0,result.stderr)
            item=json.loads(state.read_text())
            self.assertTrue(item["tls_enabled"])
            self.assertEqual(item["tls_domain"],self.DOMAIN)
            self.assertEqual(item["managed_cert"],str(certdir/"fullchain.pem"))
            self.assertEqual(item["managed_key"],str(certdir/"privkey.pem"))
            self.assertEqual((certdir/"privkey.pem").read_bytes(),key_before)
            self.assertEqual((certdir/"fullchain.pem").read_bytes(),cert_before)
            # A second Repair must remain idempotent and never switch to REALITY.
            second=self._run(root)
            self.assertEqual(second.returncode,0,second.stderr)
            self.assertTrue(json.loads(state.read_text())["tls_enabled"])

    def test_mismatched_domain_never_overwrites_previously_tls_enabled_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            self._self_signed(root/"twinpanel-tls","wrong.example.com")
            state=root/"twinpanel-modern-state.json"
            self._state(state,previously_tls=True)
            original=state.read_bytes()
            result=self._run(root)
            self.assertNotEqual(result.returncode,0)
            self.assertIn(
                "XRAY_DEDICATED_TLS_CERTIFICATE_MISSING_STOP",
                result.stderr,
            )
            self.assertEqual(state.read_bytes(),original)

    def test_legacy_domainless_node_does_not_require_certificate(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            state=root/"twinpanel-modern-state.json"
            self._state(state,previously_tls=False)
            result=self._run(root,domain="")
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertFalse(json.loads(state.read_text())["tls_enabled"])


if __name__=="__main__":
    unittest.main()
