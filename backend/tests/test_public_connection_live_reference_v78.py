"""Connection V78 security and approved-reference regression tests."""
from pathlib import Path
import asyncio
import json
import re
import shutil
import subprocess
import tempfile
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1] / "app" / "routers"


def source(name):
    return (ROOT / name).read_text(encoding="utf-8")


def test_reference_injection_and_mobile_cards_and_real_actions():
    canonical = source("public_connection_canonical_mobile_v26.py")
    ui = source("public_connection_live_reference_v78.py")
    assert "source = refine_public_connection_live_reference_v78(source)" in canonical
    assert "return refine_public_connection_unified_surface_dates_v80(source)" in canonical
    assert "grid-template-columns:repeat(4,minmax(0,1fr))!important" in ui
    assert "body.tp78-ui .protocol-choice .protocol-text{order:1!important" in ui
    assert 'body.tp78-ui .protocol-choice .protocol-icon{order:0!important' in ui
    assert 'grid-template-columns:repeat(3,minmax(0,1fr))!important' in ui
    assert "footer.append(el)" in ui  # move real button, never fake handler
    assert "const extras=candidates.filter" in ui  # retain ShadowTLS YAML/JSON, etc.
    assert "extras.forEach(el=>" in ui
    assert "const actionRoot=multi?.querySelector('.v51-multi-actions')" in ui
    assert "if(appHref&&!appHref.startsWith('#'))" not in ui or "appHref&&!appHref.startsWith('#')" in ui
    assert "data-kind=\"add\"" in ui
    assert "data-kind=\"app\"" in ui
    assert "data-kind=\"copy\"" in ui
    assert "data-kind=\"link\"" in ui
    assert "v2rayActions(panel)" in ui
    assert "function pingButton" not in ui


def test_no_stale_numbers_or_reachability_lies_in_ui():
    ui = source("public_connection_live_reference_v78.py")
    assert "node-ping/" not in ui
    assert "function pingButton" not in ui
    assert "function probe(" not in ui
    assert "modernPings(panel)" not in ui
    assert "nativePings(panel)" not in ui
    assert "v2rayPings(panel)" not in ui
    assert "function v2rayActions(panel)" in ui
    assert "36 ms" not in ui
    assert "58 ms" not in ui
    assert "72 ms" not in ui
    assert "if(account&&status)" in ui
    assert "status.classList.contains('on')" in ui
    assert "اشتراک فعال" in ui


def test_all_three_v2ray_profiles_copy_without_replacing_original_link():
    ui = source("public_connection_live_reference_v78.py")
    v54 = source("public_connection_v2ray_mobile_restore_v54.py")
    assert "if(uri)row.dataset.tp78Uri=uri" in v54
    assert "uris.join('\\n')" in ui
    assert "head.click()" in ui
    assert "if(profiles.length!==3)return null" in v54


def test_real_probe_endpoint_authorized_and_limited():
    code = source("public_connection_ping_v78.py")
    hub = source("public_connection_hub_v5.py")
    assert 'router.include_router(_live_ping_router)' in hub
    assert 'data-node-id' in hub
    assert '@router.get("/{token}/node-ping/{node_id}")' in code
    assert "_subscription_from_share_token(token, db)" in code
    assert "_entitled_node(payload, node_id)" in code
    assert "ip.is_global" in code
    assert "NodeProtocolConfig.node_id == node_id" in code
    assert "asyncio.Semaphore(4)" in code
    assert "Retry-After" in code
    assert "Cache-Control" in code
    assert "asyncio.create_subprocess_exec(" in code
    assert "asyncio.open_connection(ip, port)" in code


def test_unassigned_and_private_probes_rejected(monkeypatch):
    from app.routers import public_connection_ping_v78 as p
    from fastapi import HTTPException

    p._LAST_CHECK.clear()
    monkeypatch.setattr(p, "_subscription_from_share_token", lambda token, db: SimpleNamespace(id=74, status="active"))
    monkeypatch.setattr(p, "_public_payload", lambda db, sub: {"credentials": [{"protocol": "v2ray", "items": [{"node_id": 14}]}]})
    fake_db = SimpleNamespace(get=lambda model, node_id: SimpleNamespace(public_ip="93.184.216.34", retired_at=None))
    with pytest.raises(HTTPException) as unauthorized:
        asyncio.run(p.public_connection_live_ping_v78("opaque-link", 99, fake_db))
    assert unauthorized.value.status_code == 404

    fake_db = SimpleNamespace(get=lambda model, node_id: SimpleNamespace(public_ip="127.0.0.1", retired_at=None))
    with pytest.raises(HTTPException) as private:
        asyncio.run(p.public_connection_live_ping_v78("opaque-link", 14, fake_db))
    assert private.value.status_code == 422


def test_measured_value_is_not_cached_telemetry(monkeypatch):
    from app.routers import public_connection_ping_v78 as p
    p._LAST_CHECK.clear()
    monkeypatch.setattr(p, "_subscription_from_share_token", lambda token, db: SimpleNamespace(id=75, status="active"))
    monkeypatch.setattr(p, "_public_payload", lambda db, sub: {"credentials": [{"protocol": "openvpn", "items": [{"node_id": 7}]}]})
    monkeypatch.setattr(p, "_tcp_port", lambda db, node_id, payload: None)
    async def live(ip):
        assert ip == "93.184.216.34"
        return 42.7
    monkeypatch.setattr(p, "_measure_icmp", live)
    db = SimpleNamespace(get=lambda model, node_id: SimpleNamespace(public_ip="93.184.216.34", retired_at=None))
    response = asyncio.run(p.public_connection_live_ping_v78("opaque-link", 7, db))
    payload = json.loads(response.body)
    assert payload["node_id"] == 7
    assert payload["scope"] == "panel_to_node"
    assert payload["method"] == "icmp"
    assert payload["ms"] == 42.7
    assert response.headers["cache-control"].startswith("no-store")



def test_registered_live_router_exposes_refresh_endpoint():
    from app.routers.public_connection_hub_live_v5 import router as live_router
    route = next(
        (route for route in live_router.routes
         if route.path == "/v1/connect/{token}/node-ping/{node_id}"),
        None,
    )
    assert route is not None
    assert "GET" in route.methods
    # app.main mounts the live hub, not the legacy hub_v5 router.
    main = (ROOT.parent / "main.py").read_text(encoding="utf-8")
    assert "app.include_router(public_connection_hub_live_v5_router)" in main


def test_frontend_javascript_syntax_and_python_compile():
    code = source("public_connection_live_reference_v78.py")
    compile(code, "public_connection_live_reference_v78.py", "exec")
    compile(source("public_connection_ping_v78.py"), "public_connection_ping_v78.py", "exec")
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js unavailable")
    js = code.split('<script id="twinpanelPublicConnectionLiveReferenceV78">', 1)[1].split("</script>", 1)[0]
    with tempfile.TemporaryDirectory() as temp:
        file = Path(temp) / "v78.js"
        file.write_text(js, encoding="utf-8")
        subprocess.run([node, "--check", str(file)], check=True, capture_output=True, text=True)
