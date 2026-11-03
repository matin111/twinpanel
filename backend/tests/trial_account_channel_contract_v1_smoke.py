from pathlib import Path

router = Path("app/routers/trial.py").read_text(encoding="utf-8")
bots = Path("app/telegram_trial_patch_v1.py").read_text(encoding="utf-8")
main_service = Path("app/services/trial_service.py").read_text(encoding="utf-8")
reseller_service = Path("app/services/reseller_trial_service.py").read_text(encoding="utf-8")

# Panel and main bot converge on the same main HTTP endpoint.
assert "claim_trial_for_user" in router
assert '"/v1/trial/claim"' in bots
assert "MainTrialClaim.user_id == int(user_id)" in main_service

# Reseller bot resolves canonical User.id but claims against its own service and
# ledger scoped to (reseller_id, user_id), so a main claim cannot block it.
assert "from .services.reseller_trial_service import claim_reseller_trial_for_user" in bots
assert "claim_reseller_trial_for_user(" in bots
assert "ResellerTrialClaim.reseller_id == int(reseller_id)" in reseller_service
assert "ResellerTrialClaim.user_id == int(user_id)" in reseller_service
assert "reseller_id=int(reseller_id)" in reseller_service
assert "user_id=int(user_id)" in reseller_service

print("TRIAL_ACCOUNT_CHANNEL_CONTRACT_V1_OK")
