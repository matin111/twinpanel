from pathlib import Path

service = Path("app/services/trial_service.py").read_text(encoding="utf-8")
router = Path("app/routers/trial.py").read_text(encoding="utf-8")
models = Path("app/trial_models.py").read_text(encoding="utf-8")

joined = "\n".join([service, router, models]).lower()
assert "license_guard" not in joined
assert "vendor-license" not in joined
assert "license_trial" not in joined
assert "plantrialsetting" in joined
assert "trialclaim" in joined

print("TRIAL_ACCOUNT_NO_LICENSE_COUPLING_V1_OK")
