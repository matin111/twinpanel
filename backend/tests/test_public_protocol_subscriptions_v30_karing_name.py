from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V30 = ROOT / "app" / "routers" / "public_connection_protocol_subscriptions_v30.py"


def test_v30_karing_deep_link_passes_profile_title_as_name() -> None:
    source = V30.read_text(encoding="utf-8")
    assert "function karingHref(url,title)" in source
    assert "'&name='+encodeURIComponent(name)" in source
    assert "const title=await subscriptionIdentity(protocol,url);" in source
    assert "window.location.href=karingHref(url,title);" in source
    assert "Profile-Title" in source


def test_v30_subscription_is_one_feed_for_all_protocol_nodes() -> None:
    source = V30.read_text(encoding="utf-8")
    assert '"/{token}/sub/{protocol}"' in source
    assert 'raw = "\\n".join' in source
    assert "profile_title = f\"{_account_name(sub)}-{normalized}\"" in source
    assert "profile_name = _profile_name(sub, protocol, item)" in source
