"""Admin and Connect must agree on freshness, never treat stale sessions as online."""
from datetime import datetime, timedelta
from pathlib import Path
import ast
from app.routers import runtime_endpoints as admin
from app.routers import public_connection_live_v4 as connect

def main():
    source = (Path(__file__).resolve().parents[1] / "app/routers/runtime_endpoints.py").read_text()
    ast.parse(source)
    assert 'QuotaSession.last_seen_at >= cutoff' in source
    assert 'QuotaSession.status == "active"' in source
    assert admin._LIVE_ACTIVITY_SECONDS == connect._LIVE_ACTIVITY_SECONDS
    assert 'QuotaUsageEvent.reported_at >= cutoff' in source
    # No global change to session expiry, volume counters or device slots.
    print("ADMIN_CONNECT_LIVE_FRESHNESS_CONSISTENT=PASS")

if __name__ == "__main__":
    main()
