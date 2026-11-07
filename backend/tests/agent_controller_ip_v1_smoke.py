"""No-network regression checks for DNS-independent, pinned Node Agent HTTPS."""
from __future__ import annotations

import ast
import importlib.util
import json
import shutil
import ssl
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "backend/app/agent_controller_ip_v1.py"
TEMPLATE = ROOT / "backend/app/twinpanel_agent.py.tpl"
PROVISION = ROOT / "backend/app/routers/provision.py"
BOOTSTRAP = ROOT / "backend/app/node_bootstrap_control_v66.py"


def main() -> None:
    spec = importlib.util.spec_from_file_location("agent_controller_ip_v1", MODULE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    resolve = mod.resolve_agent_controller_connection
    assert shutil.which("openssl"), "OpenSSL is required to test certificate pins"

    with tempfile.TemporaryDirectory(prefix="agent-controller-ip-v1-") as root:
        folder = Path(root)
        config = folder / "node-agent.json"
        ca = folder / "controller-ca.pem"

        fallback = "https://api.example.test"
        assert resolve(fallback, config_path=config) == (fallback, "")

        subprocess.run(
            [
                "openssl", "req", "-x509", "-new", "-nodes", "-days", "1",
                "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1",
                "-subj", "/CN=agent-controller-test-CA",
                "-addext", "basicConstraints=critical,CA:TRUE",
                "-keyout", str(folder / "ca.key"), "-out", str(ca),
            ],
            capture_output=True,
            check=True,
            timeout=10,
        )
        url = "https://192.0.2.42:2053"
        config.write_text(json.dumps({
            "api_url": url,
            "ca_cert_path": str(ca),
        }))
        chosen, ca_pem = resolve(fallback, config_path=config)
        assert chosen == url
        assert "BEGIN CERTIFICATE" in ca_pem

        # Exact controller-only trust: no system roots or disabled validation.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=ca_pem)
        assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED

        def invalid(url_to_test: str) -> None:
            config.write_text(json.dumps({
                "api_url": url_to_test,
                "ca_cert_path": str(ca),
            }))
            try:
                resolve(fallback, config_path=config)
            except RuntimeError as exc:
                assert str(exc) == "node_agent_controller_ip_config_invalid"
            else:
                raise AssertionError(f"unsafe URL accepted: {url_to_test!r}")

        invalid("http://192.0.2.42:2053")
        invalid("https://blocked.example:2053")
        invalid("https://192.0.2.42:2053/a")
        invalid("https://192.0.2.42:2053/?token=x")
        invalid("https://password@192.0.2.42:2053")

        config.write_text(json.dumps({
            "api_url": url,
            "ca_cert_path": str(folder / "nonexistent.pem"),
        }))
        try:
            resolve(fallback, config_path=config)
        except RuntimeError:
            pass
        else:
            raise AssertionError("missing CA silently fell back to DNS")

        template = TEMPLATE.read_text()
        source = template.replace("__API_LITERAL__", repr(url))
        source = source.replace("__NODE_ID__", "42")
        source = source.replace("__SECRET_LITERAL__", repr("fake-local-test-secret"))
        source = source.replace("__CONTROLLER_CA_PEM_LITERAL__", repr(ca_pem))
        ast.parse(source)
        compile(source, "<generated-node-agent>", "exec")
        assert "verify=agent_https_verification()" in source
        assert "ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)" in source
        assert "verify=False" not in source

    provision = PROVISION.read_text()
    bootstrap = BOOTSTRAP.read_text()
    assert "resolve_agent_controller_connection(api_base)" in provision
    assert '"__CONTROLLER_CA_PEM_LITERAL__"' in provision
    assert "resolve_agent_controller_connection(api_base)" in bootstrap
    assert "pinned_controller_ip_unreachable_from_exit" in bootstrap
    print("TWINPANEL_AGENT_CONTROLLER_IP_V1_SMOKE=PASS")


if __name__ == "__main__":
    main()
