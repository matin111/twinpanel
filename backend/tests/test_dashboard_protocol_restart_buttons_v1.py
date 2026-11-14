"""Dashboard protocol restarts must remain per-node, confirmed, and authenticated."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]

class DashboardProtocolRestartContract(unittest.TestCase):
    def test_every_dashboard_protocol_has_restart_action(self):
        src=(ROOT/"components/admin-dashboard-network-panels.tsx").read_text()
        self.assertIn("shown.map(p=>",src)
        self.assertIn('<DashboardProtocolRestart protocol={p.key}',src)
        self.assertIn("onComplete={onRestart}",src)

    def test_restart_requires_node_selection_and_uses_existing_admin_endpoints(self):
        src=(ROOT/"components/dashboard-protocol-restart.tsx").read_text()
        self.assertIn("legacyAdminApi.classicProtocols()",src)
        self.assertIn("legacyAdminApi.restartProtocol(node.id,protocol as ClassicProtocolKey)",src)
        self.assertIn('/modern-protocols/${node.id}/${encodeURIComponent(protocol)}/restart',src)
        self.assertIn("const node=choices.find(row=>row.id===selected)",src)
        self.assertIn("disabled={busy||loading||selected===null||Boolean(notice)}",src)
        self.assertIn("getCustomerToken()",src)
        self.assertIn("hasSharedCore&&",src)
        self.assertNotIn("Promise.all(choices.map",src)

    def test_dashboard_refreshes_after_restart(self):
        src=(ROOT/"components/admin-dashboard-runtime.tsx").read_text()
        self.assertIn('onRestart={()=>void load(true)}',src)

if __name__=="__main__":
    unittest.main()
