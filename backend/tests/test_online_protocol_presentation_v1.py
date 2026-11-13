"""Prevent live protocol badges disappearing from current subscription cards and Connection."""
from __future__ import annotations
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class OnlineProtocolPresentationTests(unittest.TestCase):
    def test_admin_cards_have_stable_subscription_identity(self):
        text=(ROOT/"components/legacy-subscriptions-exact.tsx").read_text()
        self.assertIn('data-subscription-id={n(item.id)}',text)

    def test_admin_cards_read_confirmed_protocols_from_live_snapshot(self):
        text=(ROOT/"components/admin-subscription-live-table.tsx").read_text()
        self.assertIn('const decorateCards=()=>',text)
        self.assertIn('state?.protocols||[]',text)
        self.assertIn('online&&!uncertain',text)
        self.assertIn('decorateCards();',text)
        self.assertIn('[data-live-protocols]',text)

    def test_connection_restores_v65_hidden_protocol_status(self):
        text=(ROOT/"backend/app/routers/public_connection_hub_live_v5.py").read_text()
        self.assertIn('tp-live-protocol-status-restored',text)
        self.assertIn('body.tp65-ready .protocol-choice em{display:inline-flex!important',text)
        self.assertIn('paintProtocols(payload.online_protocols,payload.protocol_stats)',text)
        self.assertIn('source = refine_public_connection_canonical_mobile_v26(source)',text)

if __name__=="__main__":
    unittest.main()
