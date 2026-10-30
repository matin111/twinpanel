from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTER = (ROOT / "app/routers/domains.py").read_text(encoding="utf-8")
RUNTIME = (ROOT / "app/services/domain_ssl_runtime_v1.py").read_text(encoding="utf-8")


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def section(text: str, start: str, end: str) -> str:
    a = text.index(start)
    b = text.index(end, a)
    return text[a:b]


def test_create_domain_has_no_inline_ssl() -> None:
    body = section(
        ROUTER,
        'def create_domain(',
        '@router.put("/{domain_id}")',
    )
    assert_true("issue_ssl(" not in body, "create_domain must not issue SSL inline")
    assert_true("create_nginx_config(" in body, "create_domain must still create HTTP config")
    assert_true("SSLStatus.NONE" in body, "new domain must remain pending SSL")


def test_ssl_runtime_never_installs_packages() -> None:
    assert_true("apt-get" not in RUNTIME, "SSL request runtime must not apt-get")
    assert_true("shutil.which(\"certbot\")" in RUNTIME, "certbot availability must be explicit")
    assert_true("timeout=max(30, int(timeout_seconds))" in RUNTIME, "certbot must be bounded")
    assert_true("certbot_timeout" in RUNTIME, "timeout must have a stable error code")


def test_port_443_conflict_is_explicit() -> None:
    assert_true("https_port_conflict" in RUNTIME, "443 conflict code missing")
    assert_true('name != "nginx"' in RUNTIME, "non-nginx 443 owners must block issuance")
    ssl_body = section(ROUTER, 'def request_ssl(', 'except HTTPException:')
    assert_true('"https_port_conflict"' in ssl_body, "router must map 443 conflict")
    assert_true("status_code = 409" in ssl_body, "443 conflict must not become gateway timeout")


if __name__ == "__main__":
    test_create_domain_has_no_inline_ssl()
    test_ssl_runtime_never_installs_packages()
    test_port_443_conflict_is_explicit()
    print("DOMAIN_MANAGER_NO_504_V1_SMOKE=PASS")
