"""Static regression guard for token-scoped connection session reporting."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]

class SessionHistoryContract(unittest.TestCase):
    def test_session_history_is_share_token_scoped(self):
        source = (ROOT / "backend/app/routers/public_connection_session_history_v1.py").read_text()
        self.assertIn("_subscription_from_share_token(token, db)", source)
        self.assertIn("QuotaSession.subscription_id == subscription.id", source)
        self.assertIn("QuotaUsageEvent.subscription_id == subscription.id", source)
        self.assertIn("QuotaUsageEvent.node_id.in_", source)
        self.assertIn("QuotaUsageEvent.session_key.in_", source)
        self.assertIn('if event_rows else None', source)
        self.assertNotIn("traffic_used_bytes", source)

    def test_hub_renders_session_details(self):
        source = (ROOT / "backend/app/routers/public_connection_hub_live_v5.py").read_text()
        self.assertIn("router.include_router(connection_session_history_router)", source)
        self.assertIn("id=\"tp-session-items\"", source)
        for field in ("item.protocol", "item.started_at", "item.ended_at",
                      "item.duration_seconds", "item.download_bytes", "item.upload_bytes"):
            self.assertIn(field, source)

if __name__ == "__main__":
    unittest.main()
