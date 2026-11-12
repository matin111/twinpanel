"""Prevent regressions in the redesigned admin dashboard lower sections."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DASH=(ROOT/"components/admin-dashboard-runtime.tsx").read_text(encoding="utf-8")
UI=(ROOT/"components/admin-dashboard-lower-panels.tsx").read_text(encoding="utf-8")
CSS=(ROOT/"components/admin-dashboard-lower-panels.module.css").read_text(encoding="utf-8")
GUARD=(ROOT/"scripts/verify_release_ui_parity.py").read_text(encoding="utf-8")

class AdminDashboardLowerPanelsTests(unittest.TestCase):
    def test_authoritative_aggregates_not_full_subscription_download(self):
        self.assertIn('adminApi.subscriptionsPageV3({limit:1,offset:0,q:"",status:"all"})',DASH)
        self.assertIn('other:Math.max(0,total-active-expired-suspended)',DASH)
        self.assertNotIn('adminApi.subscriptions()',DASH)
        self.assertIn('loaded={subscriptionBreakdown!==null}',DASH)

    def test_payment_timeline_uses_actual_amount_and_status(self):
        self.assertIn('dashboardPaymentAmount(row)',UI)
        for category in ('"auto_verified"','"pending_payment"','"rejected"','"approved"'):
            self.assertIn(category,UI)
        self.assertIn('paymentTime(row,pick)',UI)
        self.assertIn('href="/admin/payments"',UI)

    def test_server_metrics_and_capacity_do_not_invent_values(self):
        for marker in ('health[n.id]||{}','cpu_percent','memory_percent','disk_percent',
                       'capacity_users','current_users','aria-valuenow',
                       'last_seen_at','node.country_code'):
            self.assertIn(marker,UI.replace('n.country_code','node.country_code') if marker=='node.country_code' else UI)
        self.assertIn('const cap=capacity!=null&&Number.isFinite(capacity)&&capacity>0;',UI)
        self.assertIn('const fullness=cap&&use?',UI)

    def test_colors_and_responsiveness_in_both_themes(self):
        for marker in ('html[data-theme="light"]','@media(max-width:680px)',
                       '@media(max-width:380px)','prefers-reduced-motion:reduce',
                       '.eventBadge','.donutInner','.nodeGrid','.nodeStatus'):
            self.assertIn(marker,CSS)

    def test_released_ui_is_protected_in_artifact_source(self):
        for marker in ('admin-dashboard-lower-panels.tsx','admin-dashboard-lower-panels.module.css',
                       'SUBSCRIPTION MIX','LATEST TRANSACTIONS'):
            self.assertIn(marker,GUARD)
        for component in ('<SubscriptionAnalytics','<RecentPaymentActivity','<ServerFleetVisual'):
            self.assertIn(component,DASH)

if __name__=="__main__":
    unittest.main()
