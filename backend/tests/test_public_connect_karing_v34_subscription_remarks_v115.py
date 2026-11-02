from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "app" / "public_connect_import_identity_v1.py"


def test_v34_subscription_karing_carries_username_protocol_name() -> None:
    source = PATCH.read_text(encoding="utf-8")

    assert "TWINPANEL_PUBLIC_CONNECT_IMPORT_IDENTITY_V3" in source
    assert "async function useSubscription(protocol,client){" in source
    assert "response.headers.get('Profile-Title')" in source
    assert "account+'-'+String(protocol||'vpn')" in source
    assert "&name='+encodeURIComponent(profile)" in source
    assert "forward_v34._SCRIPT = _canonicalize_v34_subscription_name" in source


def test_v34_no_longer_strips_karing_name_to_host_fallback() -> None:
    source = PATCH.read_text(encoding="utf-8")

    install_body = source.split("def install() -> None:", 1)[1]
    assert "forward_v34._SCRIPT = _remove_panel_brand" not in install_body
    assert "forward_v34._SCRIPT = _canonicalize_v34_subscription_name" in install_body
