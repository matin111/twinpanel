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

V1_SITE = """server {
  listen 80 default_server;
  server_name custom.example.test _;

  # TWINPANEL_PROVISION_LONG_REQUEST_V1
  # Node provisioning intentionally performs bounded package/protocol setup in
  # the request lifecycle. Keep the long timeout scoped to this one endpoint;
  # ordinary /v1 API calls retain Nginx defaults and fail fast normally.
  location = /v1/provision/install {
    proxy_pass http://127.0.0.1:8095;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_connect_timeout 15s;
    proxy_send_timeout 1800s;
    proxy_read_timeout 1800s;
    send_timeout 1800s;
  }

  location /v1/ {
    proxy_pass http://127.0.0.1:8095;
    proxy_http_version 1.1;
  }
}
"""


def v2_site(api_port: int = 8095) -> str:
    parts = [
        "server {\n",
        "  listen 80 default_server;\n",
        "  server_name custom.example.test _;\n\n",
        f"  {MODULE.PREVIOUS_MARKER}\n",
        "  # Keep only bounded package/runtime mutations on the long timeout.\n",
        "  # Ordinary /v1 reads and fast mutations retain Nginx defaults.\n",
    ]
    for path in MODULE.PREVIOUS_LONG_EXACT_PATHS:
        parts.append(
            MODULE._proxy_block(f"location = {path} {{", api_port, "  ")
        )
    parts.append(MODULE._proxy_block(MODULE.MODERN_INSTALL_LOCATION, api_port, "  "))
    parts.extend(
        [
            "  location /v1/ {\n",
            f"    proxy_pass http://127.0.0.1:{api_port};\n",
            "    proxy_http_version 1.1;\n",
            "  }\n",
            "}\n",
        ]
    )
    return "".join(parts)


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def assert_v3_contract(patched: str, api_port: int) -> None:
    assert_true(patched.count(MODULE.MARKER) == 1, "managed marker must be unique")
    assert_true(
        MODULE.PREVIOUS_MARKER not in patched,
        "previous V2 marker must be removed",
    )
    assert_true(MODULE.LEGACY_MARKER not in patched, "legacy marker must be removed")
    generic_index = patched.index("location /v1/ {")
    for path in MODULE.LONG_EXACT_PATHS:
        location = f"location = {path} {{"
        assert_true(location in patched, f"missing {location}")
        assert_true(
            patched.index(location) < generic_index,
            f"{location} must precede generic /v1/",
        )
    assert_true(
        "location = /v1/tunnels/create-selected {" in patched,
        "create-selected must be scoped as an exact long-running route",
    )
    assert_true(
        MODULE.MODERN_INSTALL_LOCATION in patched,
        "modern protocol install matcher missing",
    )
    assert_true(
        patched.index(MODULE.MODERN_INSTALL_LOCATION) < generic_index,
        "modern install matcher must precede generic /v1/",
    )
    assert_true(
        f"proxy_pass http://127.0.0.1:{api_port};" in patched,
        "rendered block must use detected API port",
    )
    for directive in (
        "proxy_connect_timeout 15s;",
        "proxy_send_timeout 1800s;",
        "proxy_read_timeout 1800s;",
        "send_timeout 1800s;",
    ):
        assert_true(patched.count(directive) >= 5, f"missing scoped {directive}")


def test_patch_is_scoped_and_idempotent() -> None:
    patched = MODULE.patch_nginx_site_text(LEGACY_SITE, 18095)
    assert_v3_contract(patched, 18095)
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


def test_v1_managed_site_is_upgraded_in_place() -> None:
    patched = MODULE.patch_nginx_site_text(V1_SITE, 8095)
    assert_v3_contract(patched, 8095)
    assert_true(
        patched.count("location = /v1/provision/install {") == 1,
        "V1 exact location must not be duplicated",
    )


def test_v2_managed_site_is_upgraded_in_place() -> None:
    before = v2_site(8095)
    assert_true(MODULE.PREVIOUS_MARKER in before, "V2 fixture marker missing")
    assert_true(
        "location = /v1/tunnels/create-selected {" not in before,
        "V2 fixture must represent the pre-fix contract",
    )
    patched = MODULE.patch_nginx_site_text(before, 8095)
    assert_v3_contract(patched, 8095)
    assert_true(
        patched.count("location = /v1/tunnels/create-selected {") == 1,
        "V2 migration must add create-selected exactly once",
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
            str(exc) == "NGINX_LONG_REQUEST_BLOCK_INVALID",
            "broken managed marker must fail explicitly",
        )
    else:
        raise AssertionError("broken managed block was accepted")


def test_file_convergence_and_validation_rollback() -> None:
    with tempfile.TemporaryDirectory(prefix="tp-nginx-long-v3-") as raw:
        root = Path(raw)
        site = root / "twinpanel.conf"
        backup = root / "twinpanel.conf.backup"
        site.write_text(v2_site(8095), encoding="utf-8")

        first = MODULE.reconcile_nginx_site(
            site=site,
            api_port=19095,
            backup=backup,
            nginx_bin="/bin/true",
            systemctl="/bin/true",
            reload_nginx=True,
        )
        assert_true(first["changed"] is True, "V2 site must be upgraded")
        assert_true(first["reloaded"] is True, "successful migration must reload nginx")
        assert_true(
            backup.read_text(encoding="utf-8") == v2_site(8095),
            "backup mismatch",
        )
        migrated = site.read_text(encoding="utf-8")
        assert_v3_contract(migrated, 19095)

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
        failing_site.write_text(v2_site(8095), encoding="utf-8")
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
            failing_site.read_text(encoding="utf-8") == v2_site(8095),
            "failed validation must restore original site",
        )


def test_release_template_contains_create_selected_long_request_contract() -> None:
    template = (ROOT / "deploy/nginx/twinpanel.conf.tpl").read_text(encoding="utf-8")
    exact = "location = /v1/tunnels/create-selected {"
    generic = "location /v1/ {"
    assert_true(MODULE.MARKER in template, "release template must use V3 marker")
    assert_true(exact in template, "release template missing create-selected exact route")
    assert_true(
        template.index(exact) < template.index(generic),
        "create-selected exact route must precede generic /v1/",
    )
    block = template[template.index(exact) : template.index("  }", template.index(exact))]
    for directive in (
        "proxy_connect_timeout 15s;",
        "proxy_send_timeout 1800s;",
        "proxy_read_timeout 1800s;",
        "send_timeout 1800s;",
    ):
        assert_true(directive in block, f"create-selected missing {directive}")


def test_public_updater_bridge_is_present() -> None:
    web_unit = (ROOT / "deploy/systemd/twinpanel-web.service.tpl").read_text(
        encoding="utf-8"
    )
    updater = (ROOT / "backend/scripts/twinpanel_public_updater.py").read_text(
        encoding="utf-8"
    )
    assert_true(
        "twinpanel_nginx_reconcile.py --reload" in web_unit,
        "web unit must reconcile nginx during activation",
    )
    assert_true(
        "install_web_unit(final, web_port)" in updater,
        "public updater must refresh web unit from target release",
    )


if __name__ == "__main__":
    test_patch_is_scoped_and_idempotent()
    test_v1_managed_site_is_upgraded_in_place()
    test_v2_managed_site_is_upgraded_in_place()
    test_invalid_existing_marker_is_rejected()
    test_file_convergence_and_validation_rollback()
    test_release_template_contains_create_selected_long_request_contract()
    test_public_updater_bridge_is_present()
    print("LONG_REQUEST_NGINX_TIMEOUT_V3_INTEGRATION=PASS")
