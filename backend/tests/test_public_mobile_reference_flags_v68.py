"""Regression: every registered node country renders a flag in public Connection."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1] / "app" / "routers"


def test_flag_parser_accepts_actual_server_tabs_and_new_countries():
    text = (ROOT / "public_connection_reference_desktop_mobile_v67.py").read_text(encoding="utf-8")
    assert "const emojiCode=flagToCode(raw);" in text
    assert "const code=emojiCode||alphaCode;" in text
    assert "new Intl.DisplayNames(['en'],{type:'region'})" in text
    assert "countries={DE:" not in text
    samples = {"DE":"🇩🇪", "TR":"🇹🇷", "US":"🇺🇸", "FR":"🇫🇷", "JP":"🇯🇵", "BR":"🇧🇷", "ZA":"🇿🇦", "AU":"🇦🇺"}
    for iso, emoji in samples.items():
        tab_label=f"{emoji} · 35"
        match=re.search(r"([\U0001F1E6-\U0001F1FF]{2})", tab_label)
        assert match
        actual="".join(chr(ord(c)-0x1F1E6+ord("A")) for c in match.group(1))
        assert actual==iso


def test_status_uses_subscription_username_instead_of_admin_profile_name():
    text=(ROOT/"public_connection_reference_desktop_mobile_v67.py").read_text(encoding="utf-8")
    assert "const user=top?.querySelector('.service')?.textContent?.trim()" in text
    assert "const user=top?.querySelector('.profile-copy strong')" not in text


def test_mobile_ref_layout_and_no_vpn_mutation():
    text=(ROOT/"public_connection_reference_desktop_mobile_v67.py").read_text(encoding="utf-8")
    compile(text,"mobile-ref","exec")
    assert "grid-template-columns:repeat(4,minmax(0,1fr))" in text
    assert ".traffic .stat:nth-child(n+4){display:none!important}" in text
    assert "countryName(code)" in text
    assert "tab.dataset.latencyMs||views[i]?.dataset.latencyMs||''" in text
    assert "const original=linkToOriginal" in text
    assert "db.commit(" not in text
    assert "fetch(" not in text
    assert "UPDATE nodes" not in text


def test_javascript_parser_if_node_available():
    import shutil
    import subprocess
    import tempfile
    import pytest
    node=shutil.which("node")
    if not node: pytest.skip("node unavailable")
    text=(ROOT/"public_connection_reference_desktop_mobile_v67.py").read_text(encoding="utf-8")
    script=text.split('<script id="twinpanelPublicConnectionReferenceV67">',1)[1].split('</script>',1)[0]
    with tempfile.TemporaryDirectory() as directory:
        f=Path(directory)/"reference.js";f.write_text(script,encoding="utf-8")
        subprocess.run([node,"--check",str(f)],check=True,capture_output=True,text=True)
