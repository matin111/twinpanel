from pathlib import Path

service = Path("app/services/trial_service.py").read_text(encoding="utf-8")

assert "now = datetime.utcnow()" in service
assert "sub.starts_at = now" in service
assert "sub.expires_at = now + timedelta(days=duration_days)" in service
assert "sub.activation_duration_days = None" in service

print("TRIAL_ACCOUNT_IMMEDIATE_EXPIRY_V1_OK")
