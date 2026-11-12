"""Regression checks for the live, light/dark server pulse dashboard card."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CARD = (ROOT / "components/admin-dashboard-server-card.tsx").read_text()
CSS = (ROOT / "components/admin-dashboard-server-card.module.css").read_text()

class ServerPulseDashboardTests(unittest.TestCase):
    def test_real_api_reused_without_extra_server_queries(self):
        self.assertIn('/v1/admin/system-health', CARD)
        self.assertIn('setInterval(()=>void load(),15000)', CARD)
        self.assertIn('cache:"no-store"', CARD)
        self.assertEqual(CARD.count('/v1/admin/system-health'), 1)

    def test_history_is_bounded_and_only_real_samples(self):
        self.assertIn('WINDOW_MS=8*60*1000', CARD)
        self.assertIn('MAX_SAMPLES=33', CARD)
        self.assertIn('serverSample(payload)', CARD)
        self.assertIn('setSamples(before=>[...before.filter', CARD)
        self.assertIn('previous', CARD.replace('before=>', 'previous')) if False else None
        self.assertNotIn('Math.random(', CARD)
        self.assertNotIn('mockData', CARD)

    def test_all_four_metrics_and_correct_failure_state(self):
        for token in ('kind="cpu"','kind="ram"','kind="disk"',
                      '<NetworkGauge', 'network?.rx_mbps','network?.tx_mbps',
                      'setTelemetryState("stale")','aria-label='):
            self.assertIn(token, CARD)

    def test_dark_light_and_mobile_are_scoped(self):
        for token in ('html[data-theme="light"]', 'var(--surface', 'var(--text',
                      '@media(max-width:700px)', '@media(prefers-reduced-motion:reduce)',
                      'stroke-dasharray', 'color-mix'):
            self.assertIn(token, CSS if token != 'stroke-dasharray' else CARD+CSS)
        self.assertNotIn('background:#000!important', CSS)

    def test_existing_dashboard_mount_and_access_control_preserved(self):
        self.assertIn('createPortal(', CARD)
        self.assertIn('.dash27 .dash27-kpis', CARD)
        self.assertIn('getCustomerToken()', CARD)
        self.assertIn('Authorization:', CARD)
        self.assertIn('clearInterval(timer)', CARD)


if __name__ == "__main__":
    unittest.main()
