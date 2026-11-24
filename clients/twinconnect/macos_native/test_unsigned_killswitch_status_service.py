import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unsigned_killswitch_status_service import report,publish
from unsigned_killswitch_attestation import Evidence
from unsigned_killswitch_policy import Transport

class StatusTests(unittest.TestCase):
    def command(self,args):
        self.assertIn(args[1:],(("-s","info"),("-a","com.apple/twinconnect-killswitch","-sr")))
        return SimpleNamespace(returncode=0,stdout="Status: Disabled\n" if args[1]=="-s" else "")
    def test_remote_off_never_claims_protection(self):
        row=report(command=self.command,evidence=lambda:None,remote=True,now=lambda:100)
        self.assertEqual(row["state"],"off")
        self.assertEqual(row["reason"],"KS_REMOTE_RECOVERY_REQUIRED")
        self.assertFalse(row["activation_available"])
        self.assertFalse(row["leak_verified"])
        self.assertFalse(row["pf_enabled"])
    def test_live_evidence_does_not_enable(self):
        evidence=Evidence("sudoku","utun15","en0",(Transport("1.2.3.4",443,"tcp"),),123)
        row=report(command=self.command,evidence=lambda:evidence,remote=False)
        self.assertEqual(row["protocol"],"sudoku")
        self.assertFalse(row["activation_available"])
        self.assertNotIn("1.2.3.4",json.dumps(row))
        self.assertNotIn("utun15",json.dumps(row))
    def test_existing_anchor_never_reports_off(self):
        row=report(command=lambda args:SimpleNamespace(returncode=0,stdout="Status: Enabled" if args[1]=="-s" else "block drop quick all"),evidence=lambda:None,remote=True)
        self.assertEqual(row["state"],"unknown")
        self.assertFalse(row["leak_verified"])
    def test_unknown_kernel_status(self):
        row=report(command=lambda args:SimpleNamespace(returncode=1,stdout=""),evidence=lambda:None,remote=True)
        self.assertEqual(row["state"],"unknown")
    def test_native_report_reads_real_status_without_active_claim(self):
        source=Path(__file__).with_name("TwinConnectMacOSNativeDashboard.swift").read_text()
        block=source.split("private func nativeKillSwitchReport()",1)[1].split("@objc private func copyDiagnostics",1)[0]
        self.assertIn('status.json',block)
        self.assertIn('ownerAccountID',block)
        self.assertIn('activation_available',block)
        self.assertIn('leak_verified',block)
        self.assertIn('"Kill Switch: " + nativeKillSwitchReport()',source)
        self.assertNotIn('UserDefaults',block)

    def test_publish_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            row=report(command=self.command,evidence=lambda:None,remote=True)
            publish(root,row)
            self.assertEqual(json.loads((root/"status.json").read_text()),row)
            self.assertEqual(list(root.iterdir()),[root/"status.json"])

if __name__=="__main__":
    unittest.main()
