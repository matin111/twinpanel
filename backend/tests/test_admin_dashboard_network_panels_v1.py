"""Regression tests for dashboard tunnel and protocol monitor UX and truthfulness."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DASH=(ROOT/"components/admin-dashboard-runtime.tsx").read_text(encoding="utf-8")
NETWORK=(ROOT/"components/admin-dashboard-network-panels.tsx").read_text(encoding="utf-8")
CSS=(ROOT/"components/admin-dashboard-network-panels.module.css").read_text(encoding="utf-8")
NODES=(ROOT/"components/admin-dashboard-lower-panels.tsx").read_text(encoding="utf-8")
GUARD=(ROOT/"scripts/verify_release_ui_parity.py").read_text(encoding="utf-8")

class AdminDashboardNetworkPanelsTests(unittest.TestCase):
    def test_real_network_status_and_latencies_not_invented(self):
        for text in ('classify(t.status)', 'latency(t.latency_ms)', 't.active_transport||t.transport',
                     't.iran_node_id', 't.exit_node_id', 'tunnels.slice(0,6)',
                     'loaded?display(tunnels.length):"—"', 't.status'):
            self.assertIn(text,NETWORK)
        self.assertIn('not a verified user traffic',NETWORK)
        self.assertNotIn("Math.random(",NETWORK)

    def test_protocols_derive_count_and_categories(self):
        for text in ('const CLASSIC=new Set(', 'hysteria2', 'socks5',
                     'classicCount=protocols.filter', 'modernCount=protocols.length-classicCount',
                     'setGroup(option.id)', 'aria-pressed=', 'p.reported&&p.online',
                     'p.reported?display(p.onlineNodes)', 'not a verified live client'):
            self.assertIn(text,NETWORK)
        self.assertNotIn('15 service protocols',DASH)
        self.assertIn('<ProtocolMonitor protocols={protocols} pick={pick}/>',DASH)

    def test_nodes_get_both_roles_and_true_online_summary(self):
        for text in ('node_type', 'ورودی ایران', 'سرور خروجی', 'nodeRole',
                     'onlineCount=nodes.filter', 'loaded?num(onlineCount)'):
            self.assertIn(text,NODES)

    def test_light_dark_mobile_and_accessibility(self):
        for text in ('html[data-theme="light"]', '@media(max-width:680px)',
                     '@media(max-width:460px)', 'prefers-reduced-motion:reduce',
                     '.protocolGrid', '.tunnelRoute', '.status'):
            self.assertIn(text,CSS)
        self.assertIn('aria-pressed=',NETWORK)
        self.assertIn('aria-label=',NETWORK)

    def test_stale_release_is_blocked(self):
        for text in ('admin-dashboard-network-panels.tsx','admin-dashboard-network-panels.module.css',
                     'NETWORK TRANSPORTS','PROTOCOL COVERAGE','fleetSummary'):
            self.assertIn(text,GUARD)
        self.assertIn('<TunnelMonitor tunnels={tunnels} nodes={nodes} loaded={tunnelsLoaded} pick={pick}/>',DASH)
        self.assertIn('classify(status:unknown)',NETWORK)

if __name__=="__main__":
    unittest.main()
