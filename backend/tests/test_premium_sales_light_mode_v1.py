"""Regression checks for readable premium sales chart in light theme."""
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STYLES = ROOT / "components/premium-revenue-chart.module.css"
PUBLISHER = ROOT / "scripts/verify_release_ui_parity.py"


class PremiumSalesLightModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css = STYLES.read_text(encoding="utf-8")

    def test_light_rules_are_scoped_to_html_theme_and_component(self):
        rules = [line.strip() for line in self.css.splitlines()
                 if ":global(html[data-theme=" in line]
        self.assertGreaterEqual(len(rules), 24)
        self.assertTrue(all(':global(html[data-theme="light"]) .root' in rule
                            for rule in rules))

    def test_background_is_light_and_mint_purple_lines_remain_readable(self):
        start = self.css.index("/* Light theme is opt-in")
        light_css = self.css[start:self.css.index("@media(prefers-reduced-motion:reduce)", start)]
        for piece in (
            "linear-gradient(180deg,#ffffff 0%,#f5f8ff 100%)",
            ".gridline{stroke:rgba(109,126,161,.20)}",
            ".yLabel,",
            ".xLabel{fill:#536781}",
            'path[stroke="#aa96ff"]{stroke:#6b4bd7}',
            'path[stroke="#23dac6"]{stroke:#079e96}',
            "background:linear-gradient(135deg,rgba(255,255,255,.99)",
            "border-color:#cbd3e5",
        ):
            self.assertIn(piece, light_css)

    def test_dark_theme_and_reduced_motion_remain_present(self):
        css = self.css
        self.assertIn("rgba(22,30,54,.6)", css)
        self.assertIn("@media(prefers-reduced-motion:reduce)", css)
        self.assertIn("stroke-dashoffset:0", css)

    def test_official_release_publisher_guards_chart_css(self):
        guard = PUBLISHER.read_text(encoding="utf-8")
        self.assertIn('"components/premium-revenue-chart.module.css"', guard)
        self.assertIn("--check-bundle", (ROOT / ".github/workflows/publish-prebuilt-release.yml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
