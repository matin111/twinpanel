"""Release publisher may never regress a previously merged premium chart."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts/verify_release_ui_parity.py"
spec = importlib.util.spec_from_file_location("verify_release_ui_parity", SCRIPT)
assert spec and spec.loader
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class ReleaseRevenueGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.source = root / "pinned"
        self.current = root / "main"
        for directory in (self.source, self.current):
            (directory / "components").mkdir(parents=True)
            (directory / "components/admin-dashboard-runtime.tsx").write_text(
                'import {PremiumRevenueChart} from "./premium-revenue-chart";\n'
                '<PremiumRevenueChart series={sales} pick={pick}/>\n'
                'OverviewKpiCard OperationalHealthVisual tunnelsLoaded nodesLoaded '
                'SubscriptionAnalytics RecentPaymentActivity ServerFleetVisual '
                'subscriptionsPageV3 subscriptionBreakdown '
                'TunnelMonitor ProtocolMonitor tunnelsLoaded protocols={protocols}',
                encoding="utf-8",
            )
            (directory / "components/premium-revenue-chart.tsx").write_text(
                'export function PremiumRevenueChart(){return "Sales pulse";} '
                'const seriesVisible=true; const selectPointer=()=>{}; '
                'const subscription_revenue_toman=0;',
                encoding="utf-8",
            )
            (directory / "components/premium-revenue-chart.module.css").write_text(
                ".line{stroke:#9178ff;}@media(prefers-reduced-motion:reduce){.line{animation:none;}}",
                encoding="utf-8",
            )
            (directory / "components/admin-dashboard-server-card.tsx").write_text(
                'function ResourceGauge(){} function NetworkGauge(){} '
                'const serverSample=(payload)=>payload; '
                'const sample=serverSample(payload); '
                'const handler=()=>setSamples(before=>before);',
                encoding="utf-8",
            )
            (directory / "components/admin-dashboard-server-card.module.css").write_text(
                ':global(html[data-theme="light"]) .panel{background:white;} '
                '@media(prefers-reduced-motion:reduce){.panel{animation:none;}}',
                encoding="utf-8",
            )
            (directory / "components/admin-overview-visuals.tsx").write_text(
                'function HealthRow(){return null}; '
                'export function OverviewKpiCard(){} '
                'export function OperationalHealthVisual(){} '
                'function safeFraction(){} const a = "aria-valuetext";',
                encoding="utf-8",
            )
            (directory / "components/admin-overview-visuals.module.css").write_text(
                ':global(html[data-theme="light"]) .kpiValue{color:#234;} '
                '.healthTrack{height:4px} '
                '@media(prefers-reduced-motion:reduce){.healthTrack{animation:none}}',
                encoding="utf-8",
            )
            (directory / "components/admin-dashboard-lower-panels.tsx").write_text(
                'export function SubscriptionAnalytics(){} '
                'export function RecentPaymentActivity(){} '
                'export function ServerFleetVisual(){} '
                'function paymentStatus(){} '
                'const a = "dashboardPaymentAmount aria-valuenow fleetSummary nodeRole";',
                encoding="utf-8",
            )
            (directory / "components/admin-dashboard-lower-panels.module.css").write_text(
                ':global(html[data-theme="light"]) .donutInner{background:white} '
                '.nodeGrid{display:grid} '
                '@media(prefers-reduced-motion:reduce){.nodeGrid{transition:none}}',
                encoding="utf-8",
            )
            (directory / "components/admin-dashboard-network-panels.tsx").write_text(
                'const CLASSIC=new Set(); '
                'export function TunnelMonitor(){} '
                'export function ProtocolMonitor(){} '
                'const f=()=>setGroup(option.id); '
                'const note="reported online nodes classify(t.status) latency(t.latency_ms) aria-pressed";',
                encoding="utf-8",
            )
            (directory / "components/admin-dashboard-network-panels.module.css").write_text(
                ':global(html[data-theme="light"]) .protocolGrid{display:grid} '
                '.tunnelRoute{display:flex}.protocolState{color:green} '
                '@media(prefers-reduced-motion:reduce){.protocolGrid{animation:none}}',
                encoding="utf-8",
            )
            (directory / "components/legacy-subscriptions-exact.tsx").write_text(
                'const a = "mobile-subscription-actions toggleStatus(item)"; '
                'const b = \'html[data-theme="light"] .legacy-subscriptions-page .mobile-subscription-card\'; '
                'const c = \'html[data-theme="light"] .legacy-subscriptions-page .mobile-subscription-identities b\'; '
                'const d = \'html[data-theme="light"] .legacy-subscriptions-page .mobile-subscription-usage\'; '
                'const e = \'html[data-theme="light"] .legacy-subscriptions-page .subscription-presence-offline\';',
                encoding="utf-8",
            )
            (directory / "components/admin-users-runtime.tsx").write_text(
                'const a = "adminApi.usersFastPage adminApi.toggleUser"; '
                'const b = \'html[data-theme="light"] .admin-users-runtime .admin-user-card\'; '
                'const c = \'html[data-theme="light"] .admin-users-runtime .admin-user-contact\'; '
                'const d = \'html[data-theme="light"] .admin-users-runtime .admin-user-action\'; '
                'const e = \'html[data-theme="light"] .admin-users-runtime .admin-user-account-count\';',
                encoding="utf-8",
            )
            (directory / "components/central-app-brand-studio.css").write_text(
                'html[data-theme="light"] .tbs-page{color:#1c2941} '
                'html[data-theme="light"] .tbs-page .tbs-tabs{display:flex} '
                'html[data-theme="light"] .tbs-page .tbs-readonly{color:#1c2941} '
                'html[data-theme="light"] .tbs-page .tbs-preview{background:white} '
                'html[data-theme="light"] .tbs-page .tbs-save:disabled{color:#506080}',
                encoding="utf-8",
            )

    def test_up_to_date_pinned_chart_passes(self):
        guard.verify_ui_release(self.source, self.current)

    def test_old_dashboard_is_blocked_even_if_release_number_newer(self):
        (self.source / "components/admin-dashboard-runtime.tsx").write_text(
            "<polyline points={chart.subscriptionPoints}/>",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "stale"):
            guard.verify_ui_release(self.source, self.current)

    def test_missing_chart_component_is_blocked(self):
        (self.source / "components/premium-revenue-chart.tsx").unlink()
        with self.assertRaisesRegex(ValueError, "Missing"):
            guard.verify_ui_release(self.source, self.current)

    def test_new_main_chart_change_invalidates_old_candidate(self):
        with (self.current / "components/premium-revenue-chart.module.css").open("a") as css:
            css.write("\n/* future chart improvement */")
        with self.assertRaisesRegex(ValueError, "stale"):
            guard.verify_ui_release(self.source, self.current)

    def test_missing_compiled_chart_blocks_asset_publish(self):
        (self.source / ".next/standalone/.next/static/chunks").mkdir(parents=True)
        (self.source / ".next/standalone/.next/static/chunks/chunk.js").write_text(
            "old chart", encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "Compiled"):
            guard.verify_ui_release(self.source, self.current, check_bundle=True)

    def test_missing_server_resource_chart_is_blocked(self):
        (self.source / "components/admin-dashboard-server-card.tsx").unlink()
        with self.assertRaisesRegex(ValueError, "Missing"):
            guard.verify_ui_release(self.source, self.current)

    def test_old_server_chart_is_blocked_even_when_sales_chart_is_current(self):
        (self.source / "components/admin-dashboard-server-card.module.css").write_text(
            ".old-bars{height:5px}", encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "stale"):
            guard.verify_ui_release(self.source, self.current)

    def test_missing_dashboard_overview_is_blocked(self):
        (self.source / "components/admin-overview-visuals.tsx").unlink()
        with self.assertRaisesRegex(ValueError, "Missing"):
            guard.verify_ui_release(self.source, self.current)

    def test_old_kpi_stylesheet_is_blocked(self):
        (self.source / "components/admin-overview-visuals.module.css").write_text(
            ".old-kpis{display:grid}", encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "stale"):
            guard.verify_ui_release(self.source, self.current)

    def test_missing_subscription_chart_is_blocked(self):
        (self.source / "components/admin-dashboard-lower-panels.tsx").unlink()
        with self.assertRaisesRegex(ValueError, "Missing"):
            guard.verify_ui_release(self.source, self.current)

    def test_outdated_server_fleet_style_is_blocked(self):
        (self.source / "components/admin-dashboard-lower-panels.module.css").write_text(
            ".old-cards{display:grid}",encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "stale"):
            guard.verify_ui_release(self.source, self.current)

    def test_missing_tunnel_protocol_monitor_is_blocked(self):
        (self.source / "components/admin-dashboard-network-panels.tsx").unlink()
        with self.assertRaisesRegex(ValueError, "Missing"):
            guard.verify_ui_release(self.source, self.current)

    def test_old_network_dashboard_stylesheet_is_blocked(self):
        (self.source / "components/admin-dashboard-network-panels.module.css").write_text(
            ".legacy-tunnel{display:block}",encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "stale"):
            guard.verify_ui_release(self.source, self.current)

    def test_missing_light_subscription_card_is_blocked(self):
        (self.source / "components/legacy-subscriptions-exact.tsx").unlink()
        with self.assertRaisesRegex(ValueError, "Missing"):
            guard.verify_ui_release(self.source, self.current)

    def test_light_users_card_reverts_are_blocked(self):
        p = self.source / "components/admin-users-runtime.tsx"
        p.write_text('old dark-only styling',encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "stale"):
            guard.verify_ui_release(self.source, self.current)

    def test_missing_brand_studio_light_theme_is_blocked(self):
        p = self.source / "components/central-app-brand-studio.css"
        p.write_text('html[data-theme="light"] .tbs-page{}',encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "stale"):
            guard.verify_ui_release(self.source, self.current)

    def test_compiled_premium_chart_passes(self):
        folder = self.source / ".next/standalone/.next/static/chunks"
        folder.mkdir(parents=True)
        (folder / "chunk.js").write_text("Sales pulse Server pulse Service health Subscription overview Recent activity Tunnel monitor Service protocols", encoding="utf-8")
        guard.verify_ui_release(self.source, self.current, check_bundle=True)


if __name__ == "__main__":
    unittest.main()
