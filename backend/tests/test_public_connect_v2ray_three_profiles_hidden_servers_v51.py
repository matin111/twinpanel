from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "app" / "routers" / "public_connection_multilink_v7.py"


def test_multilink_resolves_runtime_public_payload_dynamically() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_ALL_PROFILES_V51" in source
    assert "from . import account_delivery" in source
    assert "return account_delivery._public_payload(db, sub)" in source
    assert "from .account_delivery import _public_payload" not in source


def test_public_meta_hides_real_server_identity() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert '"server": f"سرور {len(groups) + 1}"' in source
    assert 'item.get("country")' not in source
    assert 'item.get("location")' not in source
    assert 'item.get("server_ip")' not in source


def test_multilink_still_expands_customer_profile_policy() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert "for profile in xray_delivery._customer_profiles(item):" in source
    assert '"profile_count": len(profile_rows)' in source
    assert "resolved_profiles = xray_delivery._customer_profiles(item)" in source
