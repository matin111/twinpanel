from __future__ import annotations

from pathlib import Path


root = Path("app")
models = (root / "trial_models.py").read_text(encoding="utf-8")
main_service = (root / "services" / "trial_service.py").read_text(encoding="utf-8")
reseller_service = (root / "services" / "reseller_trial_service.py").read_text(encoding="utf-8")
router = (root / "routers" / "trial.py").read_text(encoding="utf-8")
plans = (root / "routers" / "plans.py").read_text(encoding="utf-8")
central = (root / "routers" / "central_account_delivery_runtime_v3.py").read_text(encoding="utf-8")
bots = (root / "telegram_trial_patch_v1.py").read_text(encoding="utf-8")
admin_plans_ui = Path("../components/legacy-plans-exact.tsx").read_text(encoding="utf-8")
customer_ui = Path("../components/customer-buy-runtime.tsx").read_text(encoding="utf-8")

for path, source in (
    (root / "trial_models.py", models),
    (root / "services" / "trial_service.py", main_service),
    (root / "services" / "reseller_trial_service.py", reseller_service),
    (root / "routers" / "trial.py", router),
    (root / "routers" / "plans.py", plans),
    (root / "routers" / "central_account_delivery_runtime_v3.py", central),
    (root / "telegram_trial_patch_v1.py", bots),
):
    compile(source, str(path), "exec")

# Main and reseller Trial now own independent durable ledgers.
assert 'UniqueConstraint("user_id", name="uq_main_trial_claim_user")' in models
assert 'UniqueConstraint("reseller_id", "user_id", name="uq_reseller_trial_claim_reseller_user")' in models
assert '__tablename__ = "main_trial_settings"' in models
assert '__tablename__ = "reseller_trial_settings"' in models

# Requested defaults remain 1 day / 500 MB, but settings are not Plan fields.
assert "DEFAULT_TRIAL_DURATION_DAYS = 1" in main_service
assert "DEFAULT_TRIAL_TRAFFIC_MB = 500" in main_service
assert '"scope": "main_trial_only"' in main_service
assert "update_plan_trial_setting" not in plans
assert "trial_enabled" not in admin_plans_ui

# Main ledger is acquired before subscription/provisioning work.
assert main_service.index("claim = MainTrialClaim(") < main_service.index("create_subscription_core(")
assert main_service.index("db.add(claim)") < main_service.index("create_subscription_core(")
assert "except IntegrityError" in main_service
assert '"main_trial_already_claimed"' in main_service
assert "status_code=409" in main_service

# Reseller has an independent per-reseller/user ledger and zero-cost link.
assert reseller_service.index("claim = ResellerTrialClaim(") < reseller_service.index("create_subscription_core(")
assert "ResellerSubscription(" in reseller_service
assert "reseller_id=int(reseller_id)" in reseller_service
assert "sell_price_toman=0" in reseller_service
assert "buy_price_toman=0" in reseller_service

# Trial starts immediately and uses the central modern provisioner.
for service in (main_service, reseller_service):
    assert "sub.starts_at = now" in service
    assert "sub.expires_at = now + timedelta(days=duration_days)" in service
    assert "sub.activation_duration_days = None" in service
    assert "traffic_mb * 1024 * 1024" in service
    assert "_provision_account_v1_locked" in service

# Panel + main bot share main HTTP claim; reseller bot uses only reseller service.
assert 'prefix="/v1/trial"' in router
assert '_runtime_endpoints.router.include_router(_trial_router)' in central
assert '"/v1/trial/claim"' in customer_ui
assert '"/v1/trial/claim"' in bots
assert "claim_reseller_trial_for_user" in bots
assert "claim_trial_for_user" not in bots.split("async def claim_reseller_trial", 1)[1]

print("TRIAL_ACCOUNT_ONCE_V1_OK")
