"""Regression guard: the approved compact Plans modal must expose Exit nodes."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
MODAL = ROOT / "components" / "legacy-plans-exact.tsx"
STYLES = ROOT / "components" / "compact-plan-modal.module.css"


class CompactPlanExitSelectorContract(unittest.TestCase):
    def test_exit_node_selection_remains_visible_in_create_and_edit(self):
        source = MODAL.read_text(encoding="utf-8")
        self.assertIn('Allowed exit servers', source)
        self.assertIn("exitNodes.map(row=>", source)
        self.assertIn("draft.node_ids.includes(nodeId)", source)
        self.assertIn("onChange={event=>toggleNode(nodeId,event.target.checked)}", source)
        self.assertIn("node_ids:[...allNodeIds]", source)
        self.assertNotIn("showNodes", source)
        self.assertIn("styles.selectionLayout", source)

    def test_protocol_and_node_snapshots_and_save_are_unchanged(self):
        source = MODAL.read_text(encoding="utf-8")
        self.assertIn("protocols:protocols.length?protocols:[...ALL_PROTOCOLS]", source)
        self.assertIn("node_ids:allowedNodeIds.length?allowedNodeIds:[...allNodeIds]", source)
        self.assertIn("adminApi.createPlan(draft", source)
        self.assertIn("adminApi.updatePlan(n(editing.id),draft", source)
        self.assertIn("Select at least one exit server", source)

    def test_nodes_and_protocols_are_responsive_side_by_side(self):
        styles = STYLES.read_text(encoding="utf-8")
        self.assertIn(".selectionLayout{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr)", styles)
        self.assertIn(".selectionColumn .pills{grid-template-columns:repeat(2,minmax(0,1fr));max-height:176px", styles)
        self.assertIn(".selectionLayout{grid-template-columns:minmax(0,1fr)}", styles)


if __name__ == "__main__":
    unittest.main()
