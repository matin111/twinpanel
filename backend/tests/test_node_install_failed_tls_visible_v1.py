"""The add-node status must not hide a failed Xray TLS install."""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[2] / "components/node-add-modal-bridge.tsx").read_text(encoding="utf-8")


class AddNodeFailureVisibleTest(unittest.TestCase):
    def test_failed_status_visible_after_modal_closes(self):
        self.assertIn('!open&&jobId&&(job?.state==="failed"||job?.state==="interrupted")', SOURCE)
        self.assertIn('role="alert"', SOURCE)
        self.assertIn('job.error_code', SOURCE)
        self.assertIn('setOpen(true)', SOURCE)

    def test_tls_hint_distinguishes_listener_port_from_acme(self):
        self.assertIn("Changing Xray's listener port cannot fix this", SOURCE)
        self.assertIn("public TCP port 80", SOURCE)
        self.assertIn("Let\'s Encrypt", SOURCE)

if __name__ == "__main__":
    unittest.main()
