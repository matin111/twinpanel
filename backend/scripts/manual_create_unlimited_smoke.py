"""Regression: blank traffic or duration in unified admin create means unlimited."""
from pathlib import Path

root = Path(__file__).resolve().parents[2]
frontend = (root / "components" / "admin-subscription-create-unified.tsx").read_text("utf-8")
fast = (root / "backend" / "app" / "routers" / "subscription_create_fast_v1.py").read_text("utf-8")
schema = (root / "backend" / "app" / "routers" / "subscription_admin_v2.py").read_text("utf-8")
compile(fast, "subscription_create_fast_v1.py", "exec")
compile(schema, "subscription_admin_v2.py", "exec")

assert 'traffic.trim()===""?0:clean(traffic)' in frontend
assert 'duration.trim()===""?0:clean(duration)' in frontend
assert 'traffic_gb:trafficValue,duration_days:durationValue' in frontend
assert 'خالی یا صفر = حجم نامحدود' in frontend
assert 'خالی یا صفر = زمان نامحدود' in frontend
assert 'duration_days: int | None = Field(default=None, ge=0, le=3650)' in schema
assert 'duration_unlimited = duration_days == 0' in fast
assert 'duration_unlimited=duration_unlimited' in fast
assert 'traffic_bytes=int(round(traffic_gb * (1024 ** 3)))' in fast
assert 'if duration_days <= 0:' not in fast
print("MANUAL_CREATE_UNLIMITED_SMOKE=PASS")
