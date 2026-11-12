"""Guard against unreadable admin nodes dashboard when the global theme is light."""
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
CSS=(ROOT/"app/node-observability-v1.css").read_text(encoding="utf-8")
VIEW=(ROOT/"components/legacy-nodes-runtime-v2.tsx").read_text(encoding="utf-8")
GUARD=(ROOT/"scripts/verify_release_ui_parity.py").read_text(encoding="utf-8")

def luminance(h):
    x=[int(h[j:j+2],16)/255 for j in (1,3,5)]
    v=[y/12.92 if y<=.04045 else ((y+.055)/1.055)**2.4 for y in x]
    return sum(a*b for a,b in zip(v,(.2126,.7152,.0722)))

def contrast(a,b):
    hi,lo=sorted((luminance(a),luminance(b)),reverse=True)
    return (hi+.05)/(lo+.05)

class AdminNodeListLightThemeTests(unittest.TestCase):
    def test_dark_gradient_does_not_remain_on_light_selected_filter(self):
        self.assertIn('background:linear-gradient(135deg,rgba(111,72,214,.14),rgba(18,23,38,.93))',CSS)
        match=re.search(
            r'html\[data-theme="light"\]\s+\.legacy-control-page\s+\.node-list-quick-filters\s+\.node-list-filter-card\.active\s*\{([^}]+)\}',
            CSS,
        )
        self.assertIsNotNone(match)
        self.assertIn('background:linear-gradient(135deg,#f3edff 0%,#edf3ff 100%)',match.group(1))
        self.assertNotIn('18,23,38',match.group(1))

    def test_light_theme_covers_kpis_table_actions_and_toolbar(self):
        for name in (
            '.node-list-filter-card.active',
            '.node-list-stat-text b',
            '.node-list-stat-text small',
            '.stat-icon',
            '.node-list-filter-summary',
            '.table .primary-soft',
            '.runtime-toolbar input',
            '.table table td',
        ):
            self.assertIn('html[data-theme="light"] .legacy-control-page',CSS)
            self.assertIn(name,CSS)

    def test_selected_unselected_filter_functionality_is_preserved(self):
        for marker in ('aria-pressed={filter===item.id}','selectFilter(item.id)',
                       'node-list-quick-filters','node-list-filter-card',
                       'filtered.map(node=>','adminApi'):
            self.assertIn(marker,VIEW)

    def test_light_palette_has_readable_text(self):
        for fg,bg in (('#1e2d46','#ffffff'),('#1b2942','#f3edff'),
                      ('#566680','#ffffff'),('#64508c','#f3edff'),
                      ('#5639ac','#f1ecff'),('#253750','#ffffff')):
            with self.subTest(foreground=fg,background=bg):
                self.assertGreaterEqual(contrast(fg,bg),4.5)

    def test_nodes_page_is_scoped_and_dark_mode_stays_unchanged(self):
        self.assertIn('.legacy-control-page .node-list-quick-filters .node-list-filter-card.active{',CSS)
        self.assertIn('html[data-theme="light"]',CSS)
        self.assertNotIn('html[data-theme="light"] body',CSS)
        self.assertNotIn('!important',CSS)

    def test_release_stale_source_is_rejected(self):
        self.assertIn('app/node-observability-v1.css',GUARD)
        self.assertIn('components/legacy-nodes-runtime-v2.tsx',GUARD)
        self.assertIn('Admin node list light-mode KPI',GUARD)

if __name__=="__main__":
    unittest.main()
