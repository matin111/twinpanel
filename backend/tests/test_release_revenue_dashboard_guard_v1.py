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
                '<PremiumRevenueChart series={sales} pick={pick}/>\n',
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

    def test_compiled_premium_chart_passes(self):
        folder = self.source / ".next/standalone/.next/static/chunks"
        folder.mkdir(parents=True)
        (folder / "chunk.js").write_text("Sales pulse", encoding="utf-8")
        guard.verify_ui_release(self.source, self.current, check_bundle=True)


if __name__ == "__main__":
    unittest.main()
