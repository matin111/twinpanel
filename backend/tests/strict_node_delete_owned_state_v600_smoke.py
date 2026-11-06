"""Static regression checks for strict Node retirement."""
from pathlib import Path
root = Path(__file__).resolve().parents[1]
nodes = (root / "app/routers/nodes.py").read_text()
cleanup = (root / "app/lifecycle_cleanup.py").read_text()
start = nodes.index("async def delete_node(")
end = nodes.index("\n@router.", start)
deletion = nodes[start:end]
assert 'Node.public_ip == node.public_ip' in deletion
assert 'Node.id != node_id' in deletion
assert 'Node.retired_at.is_(None)' in deletion
assert 'DELETE FROM subscription_node_delivery_modes' in deletion
assert 'DELETE FROM plan_nodes WHERE node_id = :node_id' in deletion
assert 'DELETE FROM node_telemetry WHERE node_id = :node_id' in deletion
assert 'remove_node_from_delivery_credentials(' in deletion
assert 'if not delivery_cleanup.get("ok"):' in deletion
assert 'removed_items": 0' in deletion  # initial counter, not swallowed exceptions
assert 'except Exception:\n            # Runtime cleanup and retirement must not be' not in deletion
assert 'node.retired_at = now' in deletion
assert deletion.index('remove_node_from_delivery_credentials(') < deletion.index('node.retired_at = now')
assert 'twinpanel-sing-box.service' in cleanup
assert 'twinpanel-trusttunnel.service' in cleanup
assert '/etc/twinpanel/standalone' in cleanup
assert '/etc/twinpanel/sing-box' in cleanup
assert 'if [ -d /etc/twinpanel/standalone/mieru ]; then' in cleanup
assert 'wg-quick@wg-access0.service' in cleanup
print("strict node retirement safety contract passed")
