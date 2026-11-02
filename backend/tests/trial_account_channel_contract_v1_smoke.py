from pathlib import Path

router = Path("app/routers/trial.py").read_text(encoding="utf-8")
bots = Path("app/telegram_trial_patch_v1.py").read_text(encoding="utf-8")
service = Path("app/services/trial_service.py").read_text(encoding="utf-8")

# Panel and main bot converge on the same HTTP endpoint; reseller bot resolves
# its canonical User row then calls the same backend service directly.
assert "claim_trial_for_user" in router
assert '"/v1/trial/claim"' in bots
assert "from .services.trial_service import claim_trial_for_user" in bots
assert 'source="reseller_bot"' in bots

# One ledger key is canonical User.id, not Telegram chat id or reseller id.
assert "TrialClaim.user_id == int(user_id)" in service
assert "user_id=int(user_id)" in service

print("TRIAL_ACCOUNT_CHANNEL_CONTRACT_V1_OK")
