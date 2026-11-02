from __future__ import annotations

from pathlib import Path


root = Path("app")
models = (root / "trial_models.py").read_text(encoding="utf-8")
service = (root / "services" / "trial_service.py").read_text(encoding="utf-8")
router = (root / "routers" / "trial.py").read_text(encoding="utf-8")
plans = (root / "routers" / "plans.py").read_text(encoding="utf-8")
central = (root / "routers" / "central_account_delivery_runtime_v3.py").read_text(encoding="utf-8")
bots = (root / "telegram_trial_patch_v1.py").read_text(encoding="utf-8")
admin_ui = Path("../components/legacy-plans-exact.tsx").read_text(encoding="utf-8")
customer_ui = Path("../components/customer-buy-runtime.tsx").read_text(encoding="utf-8")

for path, source in (
    (root / "trial_models.py", models),
    (root / "services" / "trial_service.py", service),
    (root / "routers" / "trial.py", router),
    (root / "routers" / "plans.py", plans),
    (root / "routers" / "central_account_delivery_runtime_v3.py", central),
    (root / "telegram_trial_patch_v1.py", bots),
):
    compile(source, str(path), "exec")

# Durable one-claim ledger: deleting/expiring the VPN subscription cannot reset it.
assert 'UniqueConstraint("user_id", name="uq_trial_claim_user")' in models
assert 'user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True' in models

# Requested defaults and strict plan scope.
assert "DEFAULT_TRIAL_DURATION_DAYS = 1" in service
assert "DEFAULT_TRIAL_TRAFFIC_MB = 500" in service
assert '"trial_scope": "plan"' in service
assert "trial_enabled" in plans and "trial_traffic_mb" in plans
assert "اکانت تست عمومی" not in admin_ui
assert "trial_traffic_mb:500" in admin_ui

# The unique claim is acquired before subscription/provisioning work, making a
# second concurrent or sequential claim fail closed.
assert service.index("claim = TrialClaim(") < service.index("create_subscription_core(")
assert service.index("db.add(claim)") < service.index("create_subscription_core(")
assert "except IntegrityError" in service
assert '"trial_already_claimed"' in service
assert "status_code=409" in service

# Trial starts immediately and is not an unlimited first-use reservation.
assert "sub.starts_at = now" in service
assert "sub.expires_at = now + timedelta(days=duration_days)" in service
assert "sub.activation_duration_days = None" in service
assert "traffic_mb * 1024 * 1024" in service

# One central 15-protocol delivery path and one HTTP endpoint for panel/main bot.
assert "_provision_account_v1_locked" in service
assert 'prefix="/v1/trial"' in router
assert '_runtime_endpoints.router.include_router(_trial_router)' in central
assert '"/v1/trial/claim"' in customer_ui
assert '"/v1/trial/claim"' in bots

# Reseller bot calls the exact same central service and links the zero-cost trial
# into ResellerSubscription so it appears under the reseller customer's account.
assert "claim_trial_for_user" in bots
assert 'source="reseller_bot"' in bots
assert "ResellerSubscription(" in service
assert "sell_price_toman=0" in service
assert "buy_price_toman=0" in service

print("TRIAL_ACCOUNT_ONCE_V1_OK")
