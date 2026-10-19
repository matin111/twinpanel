from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile


ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "backend/scripts/twinpanel_nginx_reconcile.py"
SPEC = importlib.util.spec_from_file_location("twinpanel_nginx_reconcile", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("nginx reconcile module could not be loaded")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


LEGACY_SITE = """server {
  listen 80 default_server;
  server_name custom.example.test _;
  # keep-custom-tls-policy
  ssl_certificate /etc/ssl/custom/fullchain.pem;

  location /v1/ {
    proxy_pass http://127.0.0.1:8095;
    proxy_http_version 1.1;
  }

  location / {
    proxy_pass http://127.0.0.1:3000;
  }
}
"""


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def test_patch_is_scoped_and_idempotent() -> None:
    patched = MODULE.patch_nginx_site_text(LEGACY_SITE, 18095)
    assert_true(patched.count(MODULE.MARKER) == 1, "managed marker must be unique")
    assert_true(
        patched.index("location = /v1/provision/install {")
        < patched.index("location /v1/ {"),
        "exact provisioning route must precede generic /v1/ route",
    )
    assert_true(
        "proxy_pass http://127.0.0.1:18095;" in patched,
        "rendered block must use detected API port",
    )
    for directive in (
        "proxy_connect_timeout 15s;",
        "proxy_send_timeout 1800s;",
        "proxy_read_timeout 1800s;",
        "send_timeout 1800s;",
    ):
        assert_true(directive in patched, f"missing {directive}")
    assert_true(
        "server_name custom.example.test _;" in patched,
        "custom server_name must be preserved",
    )
    assert_true(
        "ssl_certificate /etc/ssl/custom/fullchain.pem;" in patched,
        "custom TLS config must be preserved",
    )
    assert_true(
        MODULE.patch_nginx_site_text(patched, 18095) == patched,
        "second convergence must be byte-idempotent",
    )


def test_invalid_existing_marker_is_rejected() -> None:
    broken = LEGACY_SITE.replace(
        "  location /v1/ {",
        f"  {MODULE.MARKER}\n  location /v1/ {{",
    )
    try:
        MODULE.patch_nginx_site_text(broken, 8095)
    except RuntimeError as exc:
        assert_true(
            str(exc) == "NGINX_PROVISION_BLOCK_INVALID",
            "broken managed marker must fail explicitly",
        )
    else:
        raise AssertionError("broken managed block was accepted")


def test_file_convergence_and_validation_rollback() -> None:
    with tempfile.TemporaryDirectory(prefix="tp-nginx-v74-") as raw:
        root = Path(raw)
        site = root / "twinpanel.conf"
        backup = root / "twinpanel.conf.backup"
        state = root / "state.json"
        site.write_text(LEGACY_SITE, encoding="utf-8")

        first = MODULE.reconcile_nginx_site(
            site=site,
            api_port=19095,
            backup=backup,
            nginx_bin="/bin/true",
            systemctl="/bin/true",
            reload_nginx=True,
        )
        assert_true(first["changed"] is True, "legacy site must be changed")
        assert_true(first["reloaded"] is True, "successful migration must reload nginx")
        assert_true(backup.read_text(encoding="utf-8") == LEGACY_SITE, "backup mismatch")
        migrated = site.read_text(encoding="utf-8")
        assert_true(MODULE.MARKER in migrated, "managed block missing after convergence")

        second = MODULE.reconcile_nginx_site(
            site=site,
            api_port=19095,
            backup=backup,
            nginx_bin="/bin/true",
            systemctl="/bin/true",
            reload_nginx=True,
        )
        assert_true(second["changed"] is False, "second convergence must not rewrite")
        assert_true(site.read_text(encoding="utf-8") == migrated, "idempotent file changed")

        failing_site = root / "failing.conf"
        failing_backup = root / "failing.conf.backup"
        failing_site.write_text(LEGACY_SITE, encoding="utf-8")
        try:
            MODULE.reconcile_nginx_site(
                site=failing_site,
                api_port=19095,
                backup=failing_backup,
                nginx_bin="/bin/false",
                reload_nginx=False,
            )
        except RuntimeError as exc:
            assert_true(
                str(exc).startswith("NGINX_CONFIG_TEST_FAILED:"),
                "validation failure stage must be explicit",
            )
        else:
            raise AssertionError("invalid nginx validation unexpectedly succeeded")
        assert_true(
            failing_site.read_text(encoding="utf-8") == LEGACY_SITE,
            "failed validation must restore original site",
        )


if __name__ == "__main__":
    test_patch_is_scoped_and_idempotent()
    test_invalid_existing_marker_is_rejected()
    test_file_convergence_and_validation_rollback()
    print("PROVISION_NGINX_TIMEOUT_V74_INTEGRATION=PASS")
