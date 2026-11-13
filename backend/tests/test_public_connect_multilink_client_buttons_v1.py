from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V41 = ROOT / "app" / "routers" / "public_connection_v2ray_actions_v41.py"


def test_v2ray_uses_its_own_client_family_not_karing_or_hiddify() -> None:
    source = V41.read_text(encoding="utf-8")
    authority = source.split("_MARKER =", 1)[0]
    assert 'protocol_client_rows()["v2ray"]' in authority
    catalog = (ROOT / "app/routers/public_connection_client_catalog_v821.py").read_text()
    assert '"v2ray": {"android": "v2rayng", "ios": "v2box", "windows": "v2rayn", "macos": "v2rayn"}' in catalog
    assert 'modern_delivery.CLIENTS["v2ray"] = _V2RAY_CLIENTS' in authority
    assert 'multilink.PROTOCOL_CLIENT["v2ray"] = "v2ray"' in authority
    assert 'modern_delivery.CLIENTS["v2ray"] = modern_delivery._KARING' not in authority
    assert 'multilink.PROTOCOL_CLIENT["v2ray"] = "karing"' not in authority


def test_multilink_buttons_use_one_action_vocabulary() -> None:
    source = V41.read_text(encoding="utf-8")
    assert "link('افزودن به '+client,deep,true,'افزودن به '+client)" in source
    assert "link('افزودن به '+client,deep,true)" in source
    assert ".replace(\"'کپی مولتی‌لینک'\", \"'کپی لینک'\")" in source
    assert ".replace(\"'دانلود همه'\", \"'دانلود کانفیگ‌ها'\")" in source
    assert ".replace(\"'ارسال همه به v2rayNG'\", \"'افزودن به v2rayNG'\")" in source
