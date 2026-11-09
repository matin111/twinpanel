"""V2Ray public Connection must always use the third approved row layout."""
from pathlib import Path
import shutil
import subprocess
import tempfile

import pytest

ROOT = Path(__file__).resolve().parents[1] / "app" / "routers"


def source(filename: str) -> str:
    return (ROOT / filename).read_text(encoding="utf-8")


def test_v105_applied_after_all_old_presentations():
    chain = source("public_connection_canonical_mobile_v26.py")
    assert 'source = refine_public_connection_unified_surface_dates_v80(source)' in chain
    assert 'return refine_public_connection_v2ray_single_surface_v105(source)' in chain
    assert chain.index('source = refine_public_connection_unified_surface_dates_v80(source)') < (
        chain.index('return refine_public_connection_v2ray_single_surface_v105(source)')
    )


def test_exactly_one_canonical_v2ray_source_removes_both_old_visible_modes():
    ui = source("public_connection_v2ray_single_surface_v105.py")
    assert 'data-v54-v2ray="1"] > .v54-v2ray-groups' in ui
    assert 'data-v54-v2ray="1"] > .ref67-list' in ui
    assert 'tp105-v2ray > .v54-v2ray-groups' in ui
    assert 'tp105-v2ray > .ref67-list' in ui
    assert 'tp105-v2ray > .tp105-v2ray-shell' in ui
    assert 'row.append(copy,title)' in ui  # left copy; right country+name+flag
    assert 'name.textContent=(r.code||' in ui
    assert "copy=button('کپی کانفیگ‌ها','tp105-v2ray-copy')" in ui
    assert 'countryImage(r.code)' in ui
    assert "items.length>1" not in ui  # no old add-panel mode
    assert '＋ افزودن' not in ui
    assert "const real=fromV54(panel)" in ui
    assert "const legacy=fromReference(panel)" in ui


def test_real_profiles_node_names_and_per_server_copy_are_preserved():
    v54 = source("public_connection_v2ray_mobile_restore_v54.py")
    ui = source("public_connection_v2ray_single_surface_v105.py")
    # Original name/IDs and all real profile URIs come from the real /sub/meta feed.
    assert "card.dataset.nodeName=serverLabel(server,index)" in v54
    assert "card.dataset.countryCode=String(server?.country_code||'').toUpperCase()" in v54
    assert "card.dataset.nodeId=String(server?.node_id??'')" in v54
    assert "card.dataset.nodeName" in ui
    assert "card.dataset.tp78Uri" not in ui  # profile URI, never a card-level fake
    assert "p.dataset.tp78Uri" in ui
    assert "unique(uris).join('\\n')" in ui
    assert "navigator.clipboard.writeText(value)" in ui
    # Legacy fallback uses the actual bound node-local copy handler.
    assert "r.originalCopy.click()" in ui
    # No mutation of credentials, DNS, remote clients, ports or subscriptions.
    for forbidden in (
        "db.commit(", "fetch(", "localStorage.", "sessionStorage.",
        "/v1/nodes/", "uuid=", "new WebSocket(", "setInterval(()=>location.reload",
    ):
        assert forbidden not in ui


def test_country_filter_keeps_two_germany_nodes_separate():
    ui = source("public_connection_v2ray_single_surface_v105.py")
    assert 'counts.set(r.code,(counts.get(r.code)||0)+1)' in ui
    assert "count>1?' ('+count+')'" in ui
    assert "row.dataset.nodeId=r.id" in ui
    assert "view.selection!=='ALL'&&row.dataset.country!==view.selection" in ui
    assert "const selected=panel.dataset.tp93V2Selected||'ALL'" not in ui
    assert "if(view.selection!=='ALL'&&!counts.has(view.selection))view.selection='ALL'" in ui


def test_refiner_idempotent_and_preserves_other_page_markup():
    from app.routers.public_connection_v2ray_single_surface_v105 import (
        refine_public_connection_v2ray_single_surface_v105,
    )
    doc = "<html><head><style>body{color:white}</style></head><body><main>Other VPN protocols</main></body></html>"
    rendered = refine_public_connection_v2ray_single_surface_v105(doc)
    assert rendered.count("TWINPANEL_PUBLIC_V2RAY_SINGLE_SURFACE_V105") == 2  # CSS + marker
    assert rendered.count('id="twinpanelPublicV2raySingleSurfaceV105"') == 1
    assert "Other VPN protocols" in rendered
    assert "body{color:white}" in rendered
    assert refine_public_connection_v2ray_single_surface_v105(rendered) == rendered


def test_embedded_javascript_compiles():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js unavailable")
    ui = source("public_connection_v2ray_single_surface_v105.py")
    script = ui.split(
        '<script id="twinpanelPublicV2raySingleSurfaceV105">', 1,
    )[1].split("</script>", 1)[0]
    with tempfile.TemporaryDirectory(prefix="tp-v2ray-ui-") as folder:
        file = Path(folder) / "v105.js"
        file.write_text(script, encoding="utf-8")
        result = subprocess.run(
            [node, "--check", str(file)], capture_output=True, text=True,
            timeout=12,
        )
        assert result.returncode == 0, result.stderr
