from pathlib import Path

service = Path("app/services/reseller_trial_service.py").read_text(encoding="utf-8")

assert "ResellerSubscription(" in service
assert "reseller_id=int(reseller_id)" in service
assert "customer_user_id=int(user_id)" in service
assert "subscription_id=int(sub.id)" in service
assert "sell_price_toman=0" in service
assert "buy_price_toman=0" in service

print("TRIAL_ACCOUNT_RESELLER_LINK_V1_OK")
