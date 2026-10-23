from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"
ROUTERS = APP / "routers"

registry_text = (APP / "protocol_account_registry.py").read_text(encoding="utf-8")
lifecycle_text = (ROUTERS / "subscription_protocol_lifecycle_v2.py").read_text(encoding="utf-8")
routers_init_text = (ROUTERS / "__init__.py").read_text(encoding="utf-8")
main_text = (APP / "main.py").read_text(encoding="utf-8")

registry_tree = ast.parse(registry_text)
values: dict[str, tuple[str, ...]] = {}
for node in registry_tree.body:
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        continue
    target = node.targets[0]
    if not isinstance(target, ast.Name):
        continue
    if target.id not in {"CLASSIC_PROTOCOL_KEYS", "MODERN_PROTOCOL_KEYS"}:
        continue
    values[target.id] = tuple(ast.literal_eval(node.value))

classic = values["CLASSIC_PROTOCOL_KEYS"]
modern = values["MODERN_PROTOCOL_KEYS"]
all_protocols = classic + modern

assert len(classic) == 5, classic
assert len(modern) == 10, modern
assert len(all_protocols) == 15, all_protocols
assert len(set(all_protocols)) == 15, all_protocols

assert '@router.patch("/v1/subscriptions/{subscription_id}/admin-edit")' in lifecycle_text
assert "normalize_protocols(" in lifecycle_text
assert "plan_protocols(db, plan)" in lifecycle_text
assert "MODERN_PROTOCOL_KEYS" in lifecycle_text
assert "ProtocolCredential.is_active: False" in lifecycle_text
assert 'reason="protocol_removed_v2"' in lifecycle_text
assert 'reason="protocol_reenabled_v2"' in lifecycle_text
assert "restore_candidates" in lifecycle_text
assert "sync_subscription_quota_nodes" in lifecycle_text

# Revoke must be queued while the old credential is still active. Otherwise
# enforcement's provisioned-protocol resolver would drop the command.
revoke_pos = lifecycle_text.index('reason="protocol_removed_v2"')
deactivate_pos = lifecycle_text.index("ProtocolCredential.is_active: False")
assert revoke_pos < deactivate_pos

# Global protocol OFF/ON must update QuotaDevice state too, so lifecycle V2 must
# not use node-scoped enforcement for these transitions.
assert lifecycle_text.count("node_ids=None") >= 2

# Route precedence is intentional: runtime_endpoints is mounted before the
# legacy account_delivery router, and lifecycle V2 is included on it.
assert "_subscription_protocol_lifecycle_v2_router" in routers_init_text
assert "include_router(_subscription_protocol_lifecycle_v2_router)" in routers_init_text
assert main_text.index("app.include_router(runtime_endpoints_router)") < main_text.index(
    "app.include_router(account_delivery.router)"
)

compile(lifecycle_text, str(ROUTERS / "subscription_protocol_lifecycle_v2.py"), "exec")
compile(routers_init_text, str(ROUTERS / "__init__.py"), "exec")

print("SUBSCRIPTION_PROTOCOL_LIFECYCLE_V2_SMOKE=PASS")
print("PROTOCOLS=" + ",".join(all_protocols))
