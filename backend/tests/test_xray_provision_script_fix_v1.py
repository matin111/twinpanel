from __future__ import annotations

import ast

from app.xray_provision_patch import _build_xray_mutation_script


def test_xray_mutation_script_compiles_and_has_hot_api():
    script = _build_xray_mutation_script(
        "mv-999@twinpanel",
        "00000000-0000-0000-0000-000000000999",
    )
    compile(script, "<xray-hot-user-script>", "exec")
    ast.parse(script)
    assert "import json\n" in script
    assert "_api_add(tag, port, client)" in script
    assert "_api_confirm(tag, EMAIL, CLIENT_ID)" in script
    assert "os.replace(stage, CONFIG)" in script
    assert '"hot_applied": True' in script
    assert "systemctl restart xray" not in script


def test_xray_mutation_script_never_replaces_existing_credentials():
    script = _build_xray_mutation_script(
        "mv-121@twinpanel",
        "00000000-0000-0000-0000-000000000121",
    )
    assert "duplicate VLESS account email" in script
    assert "VLESS UUID rotation requires explicit user-scoped migration" in script
    assert "VLESS client list" not in script or "VLESS client" in script
    assert "CLIENT_ID = '00000000-0000-0000-0000-000000000121'" in script
    assert "EMAIL = 'mv-121@twinpanel'" in script


def test_legacy_delivery_and_import_hook_never_restart_xray():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "app"
    delivery = (root / "routers/account_delivery.py").read_text(encoding="utf-8")
    source = delivery[delivery.index("async def _xray("):delivery.index("async def _openvpn(")]
    patch = (root / "xray_provision_patch.py").read_text(encoding="utf-8")
    section = patch[patch.index("def _patch_account_delivery("):patch.index("class _AccountDeliveryPatchLoader")]
    for code in (source, section):
        assert "hot" in code.lower()
        assert "systemctl restart xray" not in code
        assert 'result.get("hot_applied")' in code
        assert "updated_inbounds" in code
