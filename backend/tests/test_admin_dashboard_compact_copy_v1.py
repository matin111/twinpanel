"""Keep the administrator dashboard concise without losing functional data."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
SOURCES={
 "network":ROOT/"components/admin-dashboard-network-panels.tsx",
 "lower":ROOT/"components/admin-dashboard-lower-panels.tsx",
 "health":ROOT/"components/admin-overview-visuals.tsx",
 "server":ROOT/"components/admin-dashboard-server-card.tsx",
 "sales":ROOT/"components/premium-revenue-chart.tsx",
 "dashboard":ROOT/"components/admin-dashboard-runtime.tsx",
}

class DashboardCompactCopyTests(unittest.TestCase):
    def test_long_explanations_are_not_visible(self):
        forbidden={
            "network":["className={styles.note}", "NETWORK TRANSPORTS","PROTOCOL COVERAGE",
                       "Online reflects the reported tunnel state", "verified live client connection"],
            "lower":["className={styles.footnote}", "SUBSCRIPTION MIX","LATEST TRANSACTIONS",
                     "Latest recorded payment events","Node status, capacity and reported resources"],
            "health":["className={styles.healthRowSub}","className={styles.healthKicker}",
                      "not a live client-connection test", "All reported items online",
                      "className={styles.kpiCategory}"],
            "server":["INFRASTRUCTURE MONITOR","Live utilization on the main panel server",
                      "Charts include real samples collected since opening this page only"],
            "sales":["LIVE SALES ANALYTICS","Subscription sales and wallet top-ups from recorded transactions",
                     "Wallet inflow, separate from sales revenue","Real data"],
            "dashboard":["LIVE COMMAND CENTER","Unified view of sales, users, nodes, tunnels and TwinPanel protocol health"],
        }
        for name,needles in forbidden.items():
            text=SOURCES[name].read_text(encoding="utf-8")
            for needle in needles:
                with self.subTest(component=name,phrase=needle):
                    self.assertNotIn(needle,text)

    def test_core_visuals_and_real_telemetry_survive(self):
        required={
            "network":["<h2>", "Tunnel monitor","Service protocols","t.latency_ms",
                       "t.iran_node_id","t.exit_node_id","setGroup(option.id)"],
            "lower":["Subscription overview","Recent activity","ServerFleetVisual",
                     "dashboardPaymentAmount(row)","cpu_percent","memory_percent","disk_percent"],
            "health":["<h2>", "safeFraction", "aria-valuetext",
                      "className={styles.healthRing}","className={styles.kpiValue}"],
            "server":["Server pulse","setSamples(before=>", "NetworkGauge","ResourceGauge"],
            "sales":["Sales pulse","seriesVisible","selectPointer"],
            "dashboard":["<PremiumRevenueChart","<OperationalHealthVisual",
                         "<RecentPaymentActivity","<SubscriptionAnalytics",
                         "<TunnelMonitor","<ProtocolMonitor"],
        }
        for name,needles in required.items():
            text=SOURCES[name].read_text(encoding="utf-8")
            for needle in needles:
                with self.subTest(component=name,marker=needle):
                    self.assertIn(needle,text)

if __name__=="__main__":
    unittest.main()
