from __future__ import annotations

import ast
import shlex
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
LIFECYCLE_PATH = ROOT / "backend" / "app" / "naive_tls_lifecycle_v224.py"

source = LIFECYCLE_PATH.read_text(encoding="utf-8")
compile(source, str(LIFECYCLE_PATH), "exec")

for marker in (
    'MANAGED_CA_CERT_PATH = f"{CONFIG_DIR}/managed-ca.crt"',
    'MANAGED_CA_KEY_PATH = f"{CONFIG_DIR}/managed-ca.key"',
    'MANAGED_NAIVE_TRUST_MODEL = "managed-ca-v1"',
    "LEAF_VALIDITY_DAYS = 180",
    "MAX_CHROMIUM_LEAF_DAYS = 200",
    "LEAF_RENEW_BEFORE_DAYS = 30",
    'basicConstraints=critical,CA:TRUE',
    'basicConstraints=critical,CA:FALSE',
    'openssl verify -CAfile "$CA_CERT" "$CERT"',
    'openssl x509 -checkend "$RENEW_BEFORE_SECONDS"',
    'systemctl enable --now {MANAGED_CERT_RENEW_TIMER}',
    "RandomizedDelaySec=1h",
    "Persistent=true",
    "managed TLS rotation restart failed",
    "managed CA certificate/key mismatch",
):
    assert marker in source, marker

tree = ast.parse(source, filename=str(LIFECYCLE_PATH))
renew = next(
    node
    for node in tree.body
    if isinstance(node, ast.FunctionDef) and node.name == "_renew_script"
)

namespace = {
    "Node": object,
    "shlex": shlex,
    "CONFIG_DIR": "/tmp/twinpanel-naive-v224",
    "MANAGED_CA_CERT_PATH": "/tmp/twinpanel-naive-v224/managed-ca.crt",
    "MANAGED_CA_KEY_PATH": "/tmp/twinpanel-naive-v224/managed-ca.key",
    "CERT_PATH": "/tmp/twinpanel-naive-v224/server.crt",
    "KEY_PATH": "/tmp/twinpanel-naive-v224/server.key",
    "SERVICE_NAME": "twinpanel-sing-box",
    "LEAF_VALIDITY_DAYS": 180,
    "MAX_CHROMIUM_LEAF_DAYS": 200,
    "LEAF_RENEW_BEFORE_DAYS": 30,
    "CA_VALIDITY_DAYS": 3650,
    "_safe_cert_identity": lambda _node: (
        "203.0.113.10",
        ["IP:203.0.113.10"],
    ),
}
exec(
    compile(
        ast.Module(body=[renew], type_ignores=[]),
        str(LIFECYCLE_PATH),
        "exec",
    ),
    namespace,
)

script = namespace["_renew_script"](SimpleNamespace())
with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as handle:
    handle.write(script)
    path = handle.name

result = subprocess.run(
    ["bash", "-n", path],
    check=False,
    capture_output=True,
    text=True,
)
assert result.returncode == 0, result.stderr
assert "LEAF_DAYS=180" in script
assert "MAX_LEAF_SECONDS=17280000" in script
assert "RENEW_BEFORE_SECONDS=2592000" in script
assert "IP Address:203.0.113.10" in script
assert 'subjectAltName=$SAN_TEXT' in script
assert 'exit 30' in script
assert 'exit 31' in script
assert 'exit 32' in script

print("NAIVE_TLS_LIFECYCLE_V224_SMOKE=PASS")
print("MANAGED_CA=STABLE")
print("LEAF_VALIDITY_DAYS=180")
print("CHROMIUM_MAX_GUARD_DAYS=200")
print("RENEW_BEFORE_DAYS=30")
print("RENEW_TIMER=PRESENT")
print("ROLLBACK_ON_RESTART_FAILURE=PRESENT")
