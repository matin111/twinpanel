from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "app" / "routers" / "public_connection_v2ray_mobile_restore_v54.py"
CANONICAL = ROOT / "app" / "routers" / "public_connection_canonical_mobile_v26.py"


def test_v54_preserves_v2ray_server_views_and_uses_dedicated_sub_endpoint() -> None:
    source = PATCH.read_text(encoding="utf-8")
    assert "TWINPANEL_PUBLIC_CONNECT_V2RAY_MOBILE_RESTORE_V54" in source
    assert ".v38-server-list-title,.tp-v41-profile-toggle,.server-views" in source
    assert ".v38-server-list-title,.tp-v41-profile-toggle'" in source
    assert "protocol==='v2ray'?'/sub'" in source
    assert "v54-configs-open" in source
    assert "مشاهده اتصال‌های هر سرور" in source


def test_v54_is_last_public_connect_mobile_authority() -> None:
    source = CANONICAL.read_text(encoding="utf-8")
    assert "refine_public_connection_v2ray_mobile_restore_v54" in source
    assert "source = refine_public_connection_mobile_modern_surface_v53(source)" in source
    assert "return refine_public_connection_v2ray_mobile_restore_v54(source)" in source
