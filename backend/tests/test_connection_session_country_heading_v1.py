"""Country labels in Connection history must come from saved node country codes."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]

class ConnectionSessionCountryContract(unittest.TestCase):
    def test_country_from_real_node_column(self):
        source=(ROOT/"backend/app/routers/public_connection_session_history_v1.py").read_text()
        self.assertIn('getattr(node, "country_code"', source)
        self.assertIn('"country_code": country_code or None', source)
        self.assertIn('"node_name": node_name or None', source)
        self.assertNotIn('getattr(node, "country", None)',source)

    def test_heading_uses_country_not_node_number(self):
        source=(ROOT/"backend/app/routers/public_connection_hub_live_v5.py").read_text()
        self.assertIn("Intl.DisplayNames(['fa'], {type:'region'})",source)
        self.assertIn("heading.textContent = countryTitle(item)",source)
        self.assertNotIn("' · سرور #'+String(item.node_id)",source)
        self.assertIn("if (!/^[A-Z]{2}$/.test(code)) return 'کشور نامشخص';",source)

if __name__=="__main__":
    unittest.main()
