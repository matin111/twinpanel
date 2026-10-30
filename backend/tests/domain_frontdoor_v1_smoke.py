from pathlib import Path
import sys
import tempfile


BACKEND = Path(__file__).resolve().parents[1]
ROUTER = (BACKEND / "app/routers/domains.py").read_text(encoding="utf-8")
RUNTIME = (BACKEND / "app/services/domain_ssl_runtime_v1.py").read_text(encoding="utf-8")
RENDERER = (BACKEND / "app/services/domain_frontdoor_nginx_v1.py").read_text(encoding="utf-8")


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def test_router_uses_frontdoor_renderer() -> None:
    assert_true(
        "from ..services.domain_frontdoor_nginx_v1 import" in ROUTER,
        "domains router must import front-door renderer",
    )
    assert_true("create_nginx_config" in ROUTER, "front-door renderer import missing")
    assert_true("frontdoor_enabled" in ROUTER, "front-door marker helper missing")
    assert_true("refresh_frontdoor_map" in ROUTER, "domain removal must refresh the SNI map")


def test_frontdoor_https_is_internal_only() -> None:
    assert_true('INTERNAL_HTTPS_LISTEN = "127.0.0.1:9443"' in RENDERER, "internal HTTPS listener missing")
    assert_true("TWINPANEL_ACME_WEBROOT_V1" in RENDERER, "permanent ACME webroot location missing")
    assert_true("frontdoor_enabled()" in RENDERER, "front-door marker gate missing")
    assert_true("STREAM_MAP_BUILDER" in RENDERER, "managed SNI map refresh hook missing")
    assert_true("_restore_site(" in RENDERER, "Nginx update rollback helper missing")


def test_enabled_regular_file_converges_to_canonical_symlink() -> None:
    sys.path.insert(0, str(BACKEND))
    from app.services import domain_frontdoor_nginx_v1 as renderer

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        available = root / "sites-available"
        enabled_dir = root / "sites-enabled"
        available.mkdir()
        enabled_dir.mkdir()

        canonical = available / "api.example.test.conf"
        active = enabled_dir / "api.example.test.conf"
        canonical.write_text("new-config\n", encoding="utf-8")
        active.write_text("legacy-copy\n", encoding="utf-8")
        active.chmod(0o600)

        state = renderer._snapshot_enabled_entry(active)
        assert_true(state.get("kind") == "file", "legacy regular file must be snapshotted")

        renderer._ensure_enabled_symlink(canonical, active)
        assert_true(active.is_symlink(), "legacy enabled file must converge to symlink")
        assert_true(
            active.resolve(strict=False) == canonical.resolve(strict=False),
            "enabled symlink must target canonical sites-available file",
        )

        renderer._restore_enabled_entry(active, state)
        assert_true(active.is_file() and not active.is_symlink(), "rollback must restore regular file")
        assert_true(active.read_text(encoding="utf-8") == "legacy-copy\n", "rollback content mismatch")
        assert_true((active.stat().st_mode & 0o777) == 0o600, "rollback mode mismatch")


def test_frontdoor_acme_uses_webroot_not_nginx_mutation() -> None:
    assert_true('"certonly"' in RUNTIME, "front-door ACME must use certonly")
    assert_true('"--webroot"' in RUNTIME, "front-door ACME webroot mode missing")
    assert_true('str(ACME_ROOT)' in RUNTIME, "ACME webroot path missing")
    assert_true('"--nginx"' in RUNTIME, "legacy non-front-door issuance path must remain available")
    assert_true("apt-get" not in RUNTIME, "SSL request runtime must never install packages")


def test_existing_domains_refresh_before_frontdoor_acme() -> None:
    assert_true(
        "if frontdoor_enabled() or not os.path.exists(nginx_path):" in ROUTER,
        "existing managed domains must gain ACME webroot before issuance",
    )
    assert_true('"frontdoor_not_ready"' in ROUTER, "front-door readiness must map to a stable API error")


def test_frontdoor_requires_nginx_on_public_tcp_443() -> None:
    assert_true("frontdoor_tcp_443_not_owned_by_nginx" in RUNTIME, "front-door readiness guard missing")
    assert_true('name != "nginx"' in RUNTIME, "non-nginx TCP/443 owners must still block SSL")


if __name__ == "__main__":
    test_router_uses_frontdoor_renderer()
    test_frontdoor_https_is_internal_only()
    test_enabled_regular_file_converges_to_canonical_symlink()
    test_frontdoor_acme_uses_webroot_not_nginx_mutation()
    test_existing_domains_refresh_before_frontdoor_acme()
    test_frontdoor_requires_nginx_on_public_tcp_443()
    print("DOMAIN_FRONTDOOR_V1_SMOKE=PASS")
