from __future__ import annotations

import ast

from app.xray_provision_patch import _build_xray_mutation_script


def test_xray_mutation_script_uses_real_newlines_and_compiles() -> None:
    script = _build_xray_mutation_script(
        "mv-999@twinpanel",
        "00000000-0000-0000-0000-000000000999",
    )

    assert "import json\n" in script
    assert "\\n" not in script

    compile(script, "<xray-generated-script>", "exec")
    ast.parse(script)


def test_xray_mutation_script_is_idempotent_for_subscription_email() -> None:
    script = _build_xray_mutation_script(
        "mv-121@twinpanel",
        "00000000-0000-0000-0000-000000000121",
    )

    assert "isinstance(c, dict)" in script
    assert "c.get('email')!='mv-121@twinpanel'" in script
    assert "'id': '00000000-0000-0000-0000-000000000121'" in script
    assert "'email': 'mv-121@twinpanel'" in script
