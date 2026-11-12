"""Tests for reported-data driven admin KPIs and infrastructure status panels."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DASH=(ROOT/"components/admin-dashboard-runtime.tsx").read_text(encoding="utf-8")
COMP=(ROOT/"components/admin-overview-visuals.tsx").read_text(encoding="utf-8")
CSS=(ROOT/"components/admin-overview-visuals.module.css").read_text(encoding="utf-8")
GUARD=(ROOT/"scripts/verify_release_ui_parity.py").read_text(encoding="utf-8")

class DashboardOverviewTests(unittest.TestCase):
    def test_five_unique_actual_kpi_cards(self):
        self.assertEqual(DASH.count("<OverviewKpiCard kind="),5)
        for metric in ("users","subscriptions","online","sales","nodes"):
            self.assertIn('kind="'+metric+'"',DASH)
        self.assertIn("summary?.sales_today",DASH) if False else None
        self.assertIn("summary.sales_today",DASH)
        self.assertIn("summary?.total_users",DASH)
        self.assertIn("summary?.online_users",DASH)

    def test_health_indicators_use_real_reported_counts(self):
        for marker in ("<OperationalHealthVisual","nodesLoaded?onlineNodes:summary?.online_nodes",
                       "tunnelsLoaded?onlineTunnels:null",
                       "protocolReported?protocolOnline:null",
                       "protocolTotal={protocolReported||null}"):
            self.assertIn(marker,DASH)

    def test_missing_telemetry_never_becomes_fake_zero_or_full_health(self):
        self.assertIn("safeFraction",COMP)
        self.assertIn("total<1?null",COMP)
        self.assertIn("allKnown",COMP)
        self.assertIn("No reported data",COMP)
        self.assertNotIn("not a live client-connection test",COMP)
        self.assertIn("aria-valuetext=",COMP)

    def test_responsive_theme_and_motion_sensitivity(self):
        self.assertIn('html[data-theme="light"]',CSS)
        self.assertIn("@media(max-width:860px)",CSS)
        self.assertIn("@media(max-width:560px)",CSS)
        self.assertIn("prefers-reduced-motion:reduce",CSS)
        self.assertIn(".healthTrack",CSS)
        self.assertIn(".kpiProgress",CSS)

    def test_release_source_parity_guards_critical_files(self):
        for filename in ("admin-overview-visuals.tsx","admin-overview-visuals.module.css"):
            self.assertIn(filename,GUARD)
        self.assertIn("Compiled production assets are missing premium KPIs",GUARD)

if __name__=="__main__":
    unittest.main()
