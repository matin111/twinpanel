from pathlib import Path

plans = Path("app/routers/plans.py").read_text(encoding="utf-8")
service = Path("app/services/trial_service.py").read_text(encoding="utf-8")
reseller_service = Path("app/services/reseller_trial_service.py").read_text(encoding="utf-8")
trial_router = Path("app/routers/trial.py").read_text(encoding="utf-8")
admin_plans_ui = Path("../components/legacy-plans-exact.tsx").read_text(encoding="utf-8")
customer_ui = Path("../components/customer-buy-runtime.tsx").read_text(encoding="utf-8")
admin_trial_ui = Path("../components/admin-trial-settings.tsx").read_text(encoding="utf-8")
reseller_trial_ui = Path("../components/reseller-trial-settings.tsx").read_text(encoding="utf-8")
router_ui = Path("../components/routed-page-client-v2.tsx").read_text(encoding="utf-8")
admin_nav = Path("../components/ui.tsx").read_text(encoding="utf-8")
reseller_nav = Path("../components/portal-shells.tsx").read_text(encoding="utf-8")

# Trial settings must not be Plan fields anymore.
assert "update_plan_trial_setting" not in plans
assert "trial_enabled" not in plans
assert "trial_enabled" not in admin_plans_ui
assert "trial_duration_days" not in admin_plans_ui
assert "trial_traffic_mb" not in admin_plans_ui

# Main Trial owns its own setting and customer CTA reads it directly.
assert "MainTrialSetting" in service
assert "DEFAULT_TRIAL_TRAFFIC_MB = 500" in service
assert '"/v1/trial/status"' in customer_ui
assert "customer-buy-trial-standalone" in customer_ui
assert "trial_enabled?:boolean" not in customer_ui
assert "plan.trial_enabled" not in customer_ui
assert '"/v1/trial/admin/main"' in admin_trial_ui

# Reseller Trial has its own settings and self-service API bound to require_reseller.
assert "ResellerTrialSetting" in reseller_service
assert "ResellerTrialClaim" in reseller_service
assert 'Depends(require_reseller)' in trial_router
assert '@router.get("/reseller/me")' in trial_router
assert '@router.put("/reseller/me")' in trial_router
assert '"/v1/trial/reseller/me"' in reseller_trial_ui

# Both settings screens are real routes and visible in their menus.
assert 'routeKey==="admin/trial"' in router_ui
assert 'routeKey==="reseller/trial"' in router_ui
assert '"/admin/trial"' in admin_nav
assert '"/reseller/trial"' in reseller_nav

print("TRIAL_ACCOUNT_PLAN_PAYLOAD_V1_OK")
