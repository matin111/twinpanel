from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
RENDERER = (BACKEND / "app/services/domain_frontdoor_nginx_v1.py").read_text(encoding="utf-8")


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def test_api_https_quota_mtls_failure_is_fail_closed_not_fatal() -> None:
    assert_true(
        "TWINPANEL_API_HTTPS_QUOTA_FAIL_CLOSED_V1" in RENDERER,
        "front-door renderer must document the API HTTPS quota fail-closed fallback",
    )
    assert_true(
        '"quota_mtls_ca_missing"' in RENDERER,
        "missing quota CA must be handled explicitly",
    )
    assert_true(
        '"quota_mtls_proxy_secret_missing"' in RENDERER,
        "missing quota proxy secret must be handled explicitly",
    )
    assert_true(
        "_service_locations(kind, host, port, False)" in RENDERER,
        "fallback must reuse the non-secure quota route so quota identity remains blocked",
    )


if __name__ == "__main__":
    test_api_https_quota_mtls_failure_is_fail_closed_not_fatal()
    print("DOMAIN_API_HTTPS_QUOTA_GUARD_SMOKE=PASS")
