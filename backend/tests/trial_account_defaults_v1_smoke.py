from pathlib import Path

service = Path("app/services/trial_service.py").read_text(encoding="utf-8")
models = Path("app/trial_models.py").read_text(encoding="utf-8")

assert "DEFAULT_TRIAL_DURATION_DAYS = 1" in service
assert "DEFAULT_TRIAL_TRAFFIC_MB = 500" in service
assert "duration_days: Mapped[int] = mapped_column(Integer, default=1" in models
assert "traffic_mb: Mapped[int] = mapped_column(Integer, default=500" in models

print("TRIAL_ACCOUNT_DEFAULTS_V1_OK")
