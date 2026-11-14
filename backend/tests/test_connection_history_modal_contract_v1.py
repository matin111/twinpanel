"""Ensure per-session history stays out of the main Connection surface."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]

class ConnectionHistoryModalContract(unittest.TestCase):
    def test_history_is_modal_and_lazy_loaded(self):
        src = (ROOT/"backend/app/routers/public_connection_hub_live_v5.py").read_text()
        self.assertIn('id="tp-session-open"',src)
        self.assertIn('id="tp-session-dialog"',src)
        self.assertIn('aria-modal="true"',src)
        self.assertIn('dialog.hidden = false',src)
        self.assertIn('dialog.hidden = true',src)
        self.assertIn("if (!loaded) void load();",src)
        self.assertIn("event.key === 'Escape'",src)
        self.assertIn('container.textContent =',src)
        self.assertNotIn("      load();\n    })();",src)
        self.assertIn("append(card,'مجموع همین اتصال',bytes(item.total_bytes))",src)

if __name__ == "__main__":
    unittest.main()
