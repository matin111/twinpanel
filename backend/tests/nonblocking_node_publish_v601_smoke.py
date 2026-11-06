"""Regression contract: node publishing must not run per-account provisioning in the HTTP request."""
from pathlib import Path
src=(Path(__file__).resolve().parents[1]/"app/routers/publish_node_all_users_v1.py").read_text()
start=src.index("async def publish_node_to_all_users(")
end=src.index("\nclass BackgroundNodeInstallIn(",start)
body=src[start:end]
assert "db.commit()" in body
assert "TWINPANEL_NODE_PUBLISH_NONBLOCKING_V601" in body
assert "_reconcile_explicit(" not in body
assert "active_memberships_awaiting_background_sync" in body
assert "SubscriptionNodeDeliveryMode(" in body
assert "mode.direct_enabled = True" in body
assert '"ok": True' in body
print("nonblocking publish safety smoke passed")
