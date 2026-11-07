from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "app" / "routers"


def test_reference_design_is_present_and_is_final_refiner():
    ui = (ROOT / "public_connection_reference_desktop_mobile_v67.py").read_text(encoding="utf-8")
    canonical = (ROOT / "public_connection_canonical_mobile_v26.py").read_text(encoding="utf-8")
    compile(ui, "reference-v67", "exec")
    assert "TWINPANEL_PUBLIC_CONNECTION_REFERENCE_DESKTOP_MOBILE_V67" in ui
    assert "return refine_public_connection_reference_desktop_mobile_v67(source)" in canonical
    assert "source = refine_public_connection_approved_responsive_ui_v65(source)" in canonical
    for part in (".ref67-user", ".ref67-categories", ".ref67-list", ".ref67-chip",
                 ".ref67-row", ".ref67-row-actions", ".ref67-footer",
                 "grid-template-columns:repeat(4,minmax(0,1fr))",
                 "grid-template-columns:repeat(3,minmax(0,1fr))"):
        assert part in ui


def test_no_fake_latencies_and_no_backend_changes():
    source = (ROOT / "public_connection_reference_desktop_mobile_v67.py").read_text(encoding="utf-8")
    assert "const latency=tab.dataset.latencyMs||views[i]?.dataset.latencyMs||''" in source
    assert "latency&&Number.isFinite(numeric)&&numeric>=0?numeric+' ms':'—'" in source
    assert "linkToOriginal(views[i]" in source
    assert "const original=linkToOriginal" in source
    assert "copyExisting(original.copy)" in source
    assert "original.deep.getAttribute('href')" in source
    assert "document.body.classList.add('ref67')" in source
    assert "db.commit(" not in source
    assert "fetch(" not in source
    assert "UPDATE subscriptions" not in source
    assert "UPDATE nodes" not in source


def test_legacy_config_inputs_are_unchanged():
    main = (ROOT / "public_connection_hub_v5.py").read_text(encoding="utf-8")
    for field in ("__PERCENT__", "__USED__", "__REMAIN__", "__TOTAL__", "__START__", "__EXPIRE__", "__PCARDS__", "__PPANELS__"):
        assert field in main
    assert "render_protocols(" in main


def test_embedded_javascript_syntax():
    import shutil
    import subprocess
    import tempfile
    import pytest
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js not present')
    source = (ROOT / 'public_connection_reference_desktop_mobile_v67.py').read_text(encoding='utf-8')
    js = source.split('<script id="twinpanelPublicConnectionReferenceV67">',1)[1].split('</script>',1)[0]
    with tempfile.TemporaryDirectory() as path:
        file = Path(path) / 'reference-v67.js'
        file.write_text(js, encoding='utf-8')
        subprocess.run([node, '--check', str(file)], check=True, capture_output=True, text=True)
