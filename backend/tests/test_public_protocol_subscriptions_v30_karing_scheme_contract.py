from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V30 = ROOT / "app" / "routers" / "public_connection_protocol_subscriptions_v30.py"


def test_v30_uses_karing_install_config_name_parameter() -> None:
    source = V30.read_text(encoding="utf-8")
    assert "karing://install-config?url=" in source
    assert "&name=" in source
    assert "window.location.href=karingHref(url,title);" in source
