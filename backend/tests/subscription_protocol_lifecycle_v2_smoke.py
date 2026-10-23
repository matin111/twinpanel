from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"
ROUTERS = APP / "routers"
SERVICES = APP / "services"

registry_path = APP / "protocol_account_registry.py"
lifecycle_path = ROUTERS / "subscription_protocol_lifecycle_v2.py"
routers_init_path = ROUTERS / "__init__.py"
runtime_path = ROUTERS / "modern_enforcement_runtime_v1.py"
enforcement_path = SERVICES / "account_enforcement_v2.py"
main_path = APP / "main.py"

registry_text = registry_path.read_text(encoding="utf-8")
lifecycle_text = lifecycle_path.read_text(encoding="utf-8")
routers_init_text = routers_init_path.read_text(encoding="utf-8")
runtime_text = runtime_path.read_text(encoding="utf-8")
enforcement_text = enforcement_path.read_text(encoding="utf-8")
main_text = main_path.read_text(encoding="utf-8")

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

# Global protocol OFF/ON must update QuotaDevice state too.
assert lifecycle_text.count("node_ids=None") >= 2

# Every account command is controller-owned. The shipped Node Agent does not
# receive account secrets or reconstruct identities from an incomplete payload.
for marker in (
    "CONTROLLER_CLASSIC_PROTOCOLS",
    "CONTROLLER_MODERN_PROTOCOLS",
    '"controller-classic-v2"',
    '"controller-modern-v1"',
    'row.status = "controller_pending"',
):
    assert marker in enforcement_text, marker

# Five Classic runtime identities have explicit, identity-preserving handlers.
for marker in (
    '"openconnect": "cisco"',
    '"openvpn": "openvpn"',
    '"wireguard": "wireguard"',
    '"l2tp": "l2tp"',
    '"xray": "v2ray"',
    "/etc/openvpn/twinpanel-disabled/",
    "/run/twinpanel/l2tp-sessions",
    "wg set wg-access0 peer",
    "stored WireGuard identity",
    "stored V2Ray UUID",
    "ocpasswd -c /etc/ocserv/ocpasswd",
):
    assert marker in enforcement_text, marker

# WireGuard restore derives the public key from the stored private key instead
# of calling the legacy provisioning helper which generates a fresh keypair.
assert "wg pubkey" in enforcement_text
assert "wg genkey" not in enforcement_text

# Runtime and import-time queue hook both point at account_enforcement_v2.
assert "services.account_enforcement_v2" in routers_init_text
assert "install_account_enforcement_hooks()" in routers_init_text
assert "services.account_enforcement_v2" in runtime_text
assert "account_enforcement_loop()" in runtime_text

# Route precedence is intentional: runtime_endpoints is mounted before the
# legacy account_delivery router, and lifecycle V2 is included on it.
assert "_subscription_protocol_lifecycle_v2_router" in routers_init_text
assert "include_router(_subscription_protocol_lifecycle_v2_router)" in routers_init_text
assert main_text.index("app.include_router(runtime_endpoints_router)") < main_text.index(
    "app.include_router(account_delivery.router)"
)

for path, text in (
    (lifecycle_path, lifecycle_text),
    (routers_init_path, routers_init_text),
    (runtime_path, runtime_text),
    (enforcement_path, enforcement_text),
):
    compile(text, str(path), "exec")

print("SUBSCRIPTION_PROTOCOL_LIFECYCLE_V2_SMOKE=PASS")
print("PROTOCOLS=" + ",".join(all_protocols))
print("ENFORCEMENT=controller-owned-all-15")
