from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTERS = ROOT / "app" / "routers"

def test_approved_ui_is_presentation_only():
    ui = (ROUTERS / "public_connection_approved_responsive_ui_v65.py").read_text(encoding="utf-8")
    canonical = (ROUTERS / "public_connection_canonical_mobile_v26.py").read_text(encoding="utf-8")
    compile(ui, "approved-ui", "exec")
    assert 'TWINPANEL_PUBLIC_CONNECT_APPROVED_RESPONSIVE_UI_V65' in ui
    assert "return refine_public_connection_approved_responsive_ui_v65(source)" in canonical
    assert "source = refine_public_connection_v2ray_mobile_restore_v54(source)" in canonical
    assert "classList.add('tp65-ready')" in ui
    assert "grid-template-columns:repeat(4,minmax(0,1fr))" in ui
    assert ".v51-multi-actions" in ui
    assert ".v34-server-actions.tp65-replaced" in ui
    assert "if(!direct&&!fallback)return" in ui
    assert "validDeep(a.getAttribute('href')" in ui
    assert "const fallback=stored||copyLink?.getAttribute('href')||''" in ui
    assert 'item["config"] =' not in ui
    assert "db.commit(" not in ui
    assert "UPDATE nodes" not in ui
    assert "UPDATE subscriptions" not in ui
    assert "rewrite_reality" not in ui

def test_neutral_header_and_existing_delivery_paths_stay_in_place():
    hub = (ROUTERS / "public_connection_hub_v5.py").read_text(encoding="utf-8")
    routes = (ROUTERS / "public_connection_all_multilink_v34.py").read_text(encoding="utf-8")
    assert 'brand_name = "Connection"' in hub
    for protocol in ("openvpn", "wireguard", "v2ray", "hysteria2", "tuic", "anytls"):
        assert f'"{protocol}"' in routes
    assert 'return Response(content=content, media_type="text/plain; charset=utf-8", headers=headers)' in routes
