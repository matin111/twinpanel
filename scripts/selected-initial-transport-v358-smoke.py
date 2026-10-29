from pathlib import Path

ROUTER = Path("backend/app/routers/tunnel_selected_v358.py").read_text()
MAIN = Path("backend/app/main.py").read_text()
CLIENT = Path("lib/legacy-control-api.ts").read_text()
UI = Path("components/tunnel-protocol-runtime-v307.tsx").read_text()

# Backend authority: isolated create path, only two production-active choices.
assert "TWINPANEL_SELECTED_INITIAL_TRANSPORT_V358" in ROUTER
assert 'Literal["tp27_fast", "spoof_wg"]' in ROUTER
assert '@router.post(\n    "/create-selected"' in ROUTER
assert "_ensure_fabric_for_tunnel_node" in ROUTER
assert "_tp_managed_preflight_pair" in ROUTER
assert "configure_spoof_wg" in ROUTER
assert "install_modern_transport" in ROUTER
assert "select_modern_transport_manual" in ROUTER
assert "_rollback_new_selected_tunnel" in ROUTER
assert "uninstall_transport" in ROUTER
assert "register_tunnel_pair" not in ROUTER
assert 'other_transports": "not_installed"' in ROUTER

# Router is registered without replacing legacy compatibility routes.
assert "tunnel_selected_v358_router" in MAIN
assert "app.include_router(tunnel_selected_v358_router)" in MAIN

# Browser client uses the dedicated endpoint for the current New Tunnel form.
assert "createSelectedTunnel" in CLIENT
assert '"/v1/tunnels/create-selected"' in CLIENT

# Active /admin/tunnels UI explicitly chooses one initial path.
assert 'type InitialTransport="tp27_fast"|"spoof_wg"' in UI
assert 'initial_transport:"tp27_fast"' in UI
assert '<option value="tp27_fast">TP27 Fast</option>' in UI
assert '<option value="spoof_wg">Spoof Tunnel</option>' in UI
assert 'draft.initial_transport==="spoof_wg"' in UI
assert "iran_spoof_ip" in UI
assert "exit_spoof_ip" in UI
assert "legacyControlApi.createSelectedTunnel" in UI
assert 'createManagedTunnel({...draft,transport:"auto"' not in UI

# V357 readiness gate must remain intact.
assert 'readyIranNodes=useMemo(()=>iranNodes.filter(node=>normalize(node.status)==="online")' in UI
assert 'readyExitNodes=useMemo(()=>exitNodes.filter(node=>normalize(node.status)==="online")' in UI

print("SELECTED_INITIAL_TRANSPORT_V358_SMOKE_OK")
