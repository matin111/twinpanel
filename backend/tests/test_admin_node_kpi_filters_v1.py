"""Node admin KPI cards and table filters must share one read-only predicate."""
from pathlib import Path
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[2]
VIEW = (ROOT / "components/legacy-nodes-runtime-v2.tsx").read_text()
FILTERS = (ROOT / "lib/node-list-filters.ts").read_text()
ROUTER = (ROOT / "components/routed-page-client-v2.tsx").read_text()


class NodePageFilterSafetyTests(TestCase):
    def test_active_admin_page_uses_updated_runtime(self):
        self.assertIn('routeKey==="admin/nodes"', ROUTER)
        self.assertIn('from "./legacy-nodes-runtime-v2"', ROUTER)

    def test_four_kpi_cards_are_clickable_with_selected_state(self):
        for key in ("all", "online", "iran", "exit"):
            self.assertIn('id:"' + key + '"', VIEW)
            self.assertIn('case "' + key + '"', FILTERS)
        self.assertIn("onClick={()=>selectFilter(item.id)}", VIEW)
        self.assertIn("aria-pressed={filter===item.id}", VIEW)

    def test_counts_and_rows_use_same_authority_and_predicate(self):
        for name, key in (("onlineCount","online"),("iranCount","iran"),("exitCount","exit")):
            self.assertIn(
                'const ' + name + '=nodes.filter(node=>matchesNodeListFilter(node,"' + key + '",statusOf(node))).length',
                VIEW,
            )
        self.assertIn("if(!matchesNodeListFilter(node,filter,statusOf(node)))return false;",VIEW)
        self.assertIn("overviewAvailable&&overview[node.id]?.status", VIEW)
        self.assertIn("const currentStatus=statusOf(node);", VIEW)
        self.assertIn('setQuery(""); // Never hide the counted nodes', VIEW)

    def test_dropdown_and_search_support_every_node_state(self):
        for key in ("all","online","offline","maintenance","iran","exit","mother"):
            self.assertIn('<option value="' + key + '">', VIEW)
        self.assertIn("domain?.public_domain,domain?.domain",VIEW)
        self.assertIn("filtered.length===0?",VIEW)

    def test_no_network_mutations_from_kpi_filter(self):
        fragment = VIEW.split("const selectFilter=",1)[1].split("const filterLabels:",1)[0]
        self.assertNotIn("adminApi.",fragment)
        self.assertNotIn("fetch(",fragment)
        self.assertNotIn("saveNode",fragment)
        self.assertIn("setFilter(next);",fragment)


if __name__=="__main__":
    import unittest
    unittest.main()
