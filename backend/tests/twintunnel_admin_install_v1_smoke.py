"""Offline safety and state-model tests for 3-node TwinTunnel admin installer."""
from pathlib import Path
import ast

ROOT=Path(__file__).resolve().parents[1]
API=(ROOT/"app/routers/twintunnel_install_v1.py").read_text()
UI=(ROOT.parent/"components/tunnel-control-center-v1.tsx").read_text()
ACTIVE_UI=(ROOT.parent/"components/tunnel-protocol-runtime-v307.tsx").read_text()
MAIN=(ROOT/"app/main.py").read_text()
CLIENT=(ROOT.parent/"lib/twintunnel-install-api.ts").read_text()

def _view():
    tree=ast.parse(API)
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_view")
    namespace={"Tunnel": object}
    exec(compile(ast.Module(body=[node],type_ignores=[]),"install_view","exec"),namespace)
    return namespace["_view"]

class Tunnel:
    iran_node_id=2
    exit_node_id=6
    active_transport="tp27_fast"

MANIFEST={"revision":"0123456789abcdef0123"}
PLAN={
  "status":"staged",
  "tunnel_id":42,
  "iran_node_id":2,
  "exit_node_id":6,
  "backup_node_id":13,
  "revision":"0123456789abcdef0123",
  "nodes":[
     {"node_id":2,"ok":True,"selftest":"ok"},
     {"node_id":6,"ok":True,"selftest":"ok"},
     {"node_id":13,"ok":True,"selftest":"ok"},
  ],
}

def test_three_node_success_remains_off_production():
    result=_view()(42,Tunnel(),MANIFEST,PLAN)
    assert result["status"]=="staged"
    assert result["can_activate"] is False
    assert result["production_activated"] is False
    assert result["active_transport"]=="tp27_fast"
    assert result["backup_node_id"]==13
    assert result["deployment_mode"]=="isolated_stage_only"

def test_partial_or_stale_stage_cannot_be_ready():
    view=_view()
    assert view(42,Tunnel(),MANIFEST,{**PLAN,"nodes":PLAN["nodes"][:2]})["status"]=="not_staged"
    assert view(42,Tunnel(),MANIFEST,{**PLAN,"revision":"11111111111111111111"})["needs_update"]
    assert view(42,Tunnel(),MANIFEST,{**PLAN,"iran_node_id":99})["status"]=="not_staged"
    failed=[*PLAN["nodes"]]
    failed[1]={**failed[1],"selftest":"failed"}
    assert view(42,Tunnel(),MANIFEST,{**PLAN,"nodes":failed})["status"]=="not_staged"

def test_endpoints_are_admin_guarded_and_nonactivating():
    assert 'dependencies=[Depends(require_admin)]' in API
    assert '/{tunnel_id}/twintunnel-install' in API
    assert 'backup_node_id: int = Field(gt=0)' in API
    assert 'len(set(node_ids)) != 3' in API
    assert 'NodeStatus.ONLINE' in API and 'NodeType.EXIT' in API
    assert 'fcntl.LOCK_NB' in API
    assert 'close_read_transaction_before_ssh=True' in API
    assert 'STAGER = BACKEND / "scripts/twintunnel_stage_active_nodes_v1.py"' in API
    assert '"mode" == "install"' not in API
    assert "systemctl restart" not in API
    assert "systemctl start" not in API
    assert "ip route add" not in API
    assert "iptables" not in API
    assert "active_transport =" not in API
    assert 'production_activated": False' in API
    assert 'app.include_router(twintunnel_install_v1_router)' in MAIN

def test_ui_clear_distinction_between_install_and_cutover():
    assert "twintunnel_standby" in UI
    assert 'twinTunnelInstallApi.install' in UI
    assert 'twinTunnelInstallApi.verify' in UI
    assert 'TwinTunnel · 3 paths' in UI
    assert "Production cutover remains locked" in UI
    assert 'getCustomerToken()' in CLIENT
    assert '"Authorization":"Bearer "+token' in CLIENT
    assert "twintunnel_standby" in ACTIVE_UI
    assert "twinTunnelInstallApi.install" in ACTIVE_UI
    assert "twinTunnelInstallApi.verify" in ACTIVE_UI
    assert 'tp-selected-tunnel-standby-intent' in ACTIVE_UI
    assert 'BACKUP_NODE_MISSING' in ACTIVE_UI
    assert "TwinTunnel سه‌مسیره" in ACTIVE_UI
    assert "not connected to subscribers" in ACTIVE_UI


if __name__=="__main__":
    test_three_node_success_remains_off_production()
    test_partial_or_stale_stage_cannot_be_ready()
    test_endpoints_are_admin_guarded_and_nonactivating()
    test_ui_clear_distinction_between_install_and_cutover()
    print("TWINTUNNEL_ADMIN_INSTALL_V1_SMOKE_OK")
