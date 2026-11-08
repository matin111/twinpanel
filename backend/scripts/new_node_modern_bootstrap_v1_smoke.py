"""CI source-contract smoke for central-first Add Server lifecycle."""
import ast
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
worker=(ROOT/'backend/app/routers/publish_node_all_users_v1.py').read_text()
helper=(ROOT/'backend/app/services/new_node_modern_bootstrap_v1.py').read_text()
central=(ROOT/'backend/app/services/central_first_exit_bootstrap_v1.py').read_text()
pool=(ROOT/'backend/app/services/central_new_exit_wireguard_pool_v1.py').read_text()
registry=(ROOT/'backend/app/protocol_account_registry.py').read_text()

# The actual public Add Server worker uses the new central-only runtime
# bootstrap, never the old full install_node for Exit nodes.
assert "await bootstrap_hidden_central_exit(install_payload, request, db)" in worker
assert "if install_payload.node_type == NodeType.EXIT" in worker
assert "else await install_node(install_payload, request, db)" in worker
assert "central_stage.run" in worker
assert "stage_rc = await asyncio.to_thread(" in worker
assert "publish_result = await publish_node_to_all_users(" in worker
assert worker.index("bootstrap_hidden_central_exit(install_payload") < worker.index(
    "stage_rc = await asyncio.to_thread(") < worker.index(
    "publish_result = await publish_node_to_all_users(")
assert "if stage_rc != 0:" in worker

# The new Exit builder uses canonical catalog presets; importing secret
# settings or port mappings from a different Exit is forbidden.
assert "PROTOCOL_CATALOG" in helper
assert '"mode": "central_catalog"' in helper
assert "Node.id != int(target.id)" not in helper
assert "ModernProtocolSetting" not in helper
assert "from ..routers.modern_protocol_admin_v3 import (" in helper
assert "for group in groups:" in helper
assert "except HTTPException as exc:" in helper
assert "db.rollback()" in helper
assert "CENTRAL_EXIT_MODERN_INSTALL_GROUP" in helper
assert "occupied_ports.get(chosen_port, set()) - {key}" in helper
assert "result = await install(node_id=int(node_id), payload=payload, db=db)" in helper

# Reusable daemon installers are allowed; legacy account installation isn't.
assert "await prov.provision_protocols(" in central
assert "await prov.install_node(" not in central
assert "bootstrap_fresh_hidden_exit_quota" in central
assert "prepare_hidden_exit_wireguard_pool(conn)" in central
assert '"central_runtime_owns_all_subscriptions"' in central
assert "show_to_users=False" in central
assert "restarted" in pool
# Validate remote generated Python as well as the controller service.
ast.parse(pool)
for protocol in ('hysteria2','tuic','anytls','naive','shadowtls','snell','mieru','trusttunnel','amneziawg','sudoku','socks5'):
    assert f'"{protocol}"' in registry, protocol
print("NEW_NODE_CENTRAL_FIRST_BOOTSTRAP_SMOKE=OK")
