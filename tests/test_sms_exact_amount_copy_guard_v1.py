"""Regression: every card transfer form exposes copyable exact (non-rounded) amount."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_customer_subscription_checkout_copies_exact_amount():
    source=(ROOT/"components/customer-payments-runtime.tsx").read_text(encoding="utf-8")
    assert 'copy("card-amount",String(intent.payable_amount_toman' in source
    assert "rounded transfers cannot be auto-verified" in source

def test_customer_wallet_copies_unique_card_amount():
    source=(ROOT/"components/customer-wallet-v2.tsx").read_text(encoding="utf-8")
    assert 'copy("card-exact",String(active.payable_amount_toman' in source
    assert "do not round the payment amount" in source

def test_reseller_wallet_copies_unique_card_amount():
    source=(ROOT/"components/reseller-wallet-runtime.tsx").read_text(encoding="utf-8")
    assert "navigator.clipboard.writeText(String(activeTopup.payable_amount_toman" in source
    assert "do not round it" in source

def test_server_never_approves_fuzzy_sms_amount():
    source=(ROOT/"backend/app/routers/wallet_sms_reader.py").read_text(encoding="utf-8")
    assert "PaymentIntent.payable_amount_toman == amount" in source
    assert "CustomerWalletTopup.payable_amount_toman == amount" in source
    assert "if total_matches != 1:" in source
