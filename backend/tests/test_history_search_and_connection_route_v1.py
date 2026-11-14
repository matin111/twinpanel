"""Regression guard: the Connection history route and admin popup search."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]

class HistorySearchAndConnectionRoute(unittest.TestCase):
    def test_connection_history_has_one_prefix(self):
        history = (ROOT/"backend/app/routers/public_connection_session_history_v1.py").read_text()
        hub = (ROOT/"backend/app/routers/public_connection_hub_live_v5.py").read_text()
        self.assertIn('router = APIRouter(tags=["connection-session-history"])', history)
        self.assertIn('@router.get("/{token}/sessions")', history)
        self.assertIn('router.include_router(connection_session_history_router)', hub)
        self.assertIn('prefix="/v1/connect"', hub)
        self.assertIn('_subscription_from_share_token(token, db)', history)
        self.assertIn('QuotaUsageEvent.session_key.in_', history)

    def test_admin_search_is_server_side_and_role_protected(self):
        api = (ROOT/"backend/app/routers/admin_activity_v1.py").read_text()
        popup = (ROOT/"components/admin-activity-popup.tsx").read_text()
        self.assertIn("Depends(require_admin)", api)
        self.assertIn('search: str = Query(default="", max_length=100)', api)
        self.assertIn('QuotaAuditLog.actor_id.in_(matched_admins)', api)
        self.assertIn('QuotaAuditLog.subject_id.ilike(pattern)', api)
        self.assertIn('encodeURIComponent(appliedSearch)', popup)
        self.assertIn('type="search"', popup)
        self.assertIn('setAppliedSearch(search.trim())', popup)

if __name__ == "__main__":
    unittest.main()
