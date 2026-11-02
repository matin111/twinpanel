from pathlib import Path

plans = Path("app/routers/plans.py").read_text(encoding="utf-8")
service = Path("app/services/trial_service.py").read_text(encoding="utf-8")
admin_ui = Path("../components/legacy-plans-exact.tsx").read_text(encoding="utf-8")
customer_ui = Path("../components/customer-buy-runtime.tsx").read_text(encoding="utf-8")

assert "update_plan_trial_setting(db, int(plan.id), raw, creating=True)" in plans
assert "update_plan_trial_setting(db, int(plan.id), raw, creating=False)" in plans
assert "**trial" in plans
assert "DEFAULT_TRIAL_TRAFFIC_MB = 500" in service
assert "trial_enabled:false,trial_duration_days:1,trial_traffic_mb:500" in admin_ui
assert "trial_enabled?:boolean" in customer_ui
assert "🎁 دریافت اکانت تست" in customer_ui

print("TRIAL_ACCOUNT_PLAN_PAYLOAD_V1_OK")
