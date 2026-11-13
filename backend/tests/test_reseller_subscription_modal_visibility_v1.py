"""Regression guard: reseller renewal/edit dialogs must escape page stacking contexts."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
COMP=ROOT/"components/reseller-subscriptions-parity.tsx"

class ResellerSubscriptionDialogTests(unittest.TestCase):
    def test_dialog_actions_are_wired_to_state(self):
        s=COMP.read_text()
        self.assertIn('onClick={()=>openEdit(row)}',s)
        self.assertIn('onClick={()=>openExtend(row)}',s)

    def test_dialogs_are_rendered_in_document_root(self):
        s=COMP.read_text()
        self.assertIn('import {createPortal} from "react-dom"',s)
        for state in ("sellOpen","editRow","extendRow"):
            self.assertIn("{"+state+"&&createPortal(<div className=\"runtime-modal reseller-subscription-dialog\"",s)
        self.assertEqual(s.count("</div>, document.body)}"),3)

    def test_forms_keep_actions(self):
        s=COMP.read_text()
        for callback in ("submitEdit","submitExtend","submitSale"):
            self.assertIn('onSubmit={'+callback+'}',s)

if __name__=="__main__":unittest.main()
