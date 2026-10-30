from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
SSL_MANAGER = (BACKEND / "app/services/ssl_manager.py").read_text(encoding="utf-8")
INSTALLER = (BACKEND.parent / "installer/install.sh").read_text(encoding="utf-8")


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def test_secure_api_does_not_fail_when_quota_mtls_is_unconfigured() -> None:
    assert_true(
        "TWINPANEL_QUOTA_MTLS_UNAVAILABLE_V1" in SSL_MANAGER,
        "secure API must render a fail-closed quota route when mTLS prerequisites are missing",
    )
    assert_true(
        "return 503;" in SSL_MANAGER,
        "unconfigured quota route must fail closed instead of proxying identity traffic",
    )
    assert_true(
        'raise RuntimeError(\n                "quota_mtls_ca_missing"' not in SSL_MANAGER,
        "missing quota CA must not abort the whole API HTTPS virtual host",
    )
    assert_true(
        'raise RuntimeError(\n                "quota_mtls_proxy_secret_missing"' not in SSL_MANAGER,
        "missing quota proxy secret must not abort the whole API HTTPS virtual host",
    )


def test_installer_includes_stream_module_dependency() -> None:
    assert_true(
        "libnginx-mod-stream" in INSTALLER,
        "official installer must install the Nginx stream module required by the domain front door",
    )


if __name__ == "__main__":
    test_secure_api_does_not_fail_when_quota_mtls_is_unconfigured()
    test_installer_includes_stream_module_dependency()
    print("QUOTA_MTLS_HTTPS_FALLBACK_SMOKE=PASS")
