from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
worker=(ROOT/'backend/app/routers/publish_node_all_users_v1.py').read_text()
helper=(ROOT/'backend/app/services/new_node_modern_bootstrap_v1.py').read_text()
registry=(ROOT/'backend/app/protocol_account_registry.py').read_text()
bootstrap='bootstrap_new_exit_modern_protocols('
publish='result = await publish_node_to_all_users(node_id=node_id, db=db)'
assert bootstrap in worker
assert publish in worker
assert worker.index(bootstrap) < worker.index(publish)
assert 'from ..routers.modern_protocol_admin_v3 import ModernInstallV3In, ProtocolProfileIn, install' in helper
assert 'result = await install(node_id=int(node_id), payload=payload, db=db)' in helper
assert 'NodeProtocolConfig.status == "online"' in helper
assert 'ModernProtocolSetting' in helper
assert 'PROTOCOL_CATALOG' in helper
assert 'Node.id != int(target.id)' in helper
for protocol in ('hysteria2','tuic','anytls','naive','shadowtls','snell','mieru','trusttunnel','amneziawg','sudoku'):
    assert f'"{protocol}"' in registry, protocol
print('NEW_NODE_MODERN_BOOTSTRAP_V1_SMOKE=OK')
