from __future__ import annotations

import ast
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SINGBOX_PATH = ROOT / "backend" / "app" / "singbox_subscription_accounts.py"
RECONCILE_PATH = ROOT / "backend" / "app" / "routers" / "modern_legacy_reconcile_v1.py"

singbox_source = SINGBOX_PATH.read_text(encoding="utf-8")
reconcile_source = RECONCILE_PATH.read_text(encoding="utf-8")
compile(singbox_source, str(SINGBOX_PATH), "exec")
compile(reconcile_source, str(RECONCILE_PATH), "exec")

tree = ast.parse(singbox_source, filename=str(SINGBOX_PATH))
wanted = {
    "_client_tls",
    "_naive_tls_requires_repair",
    "naive_client_item_requires_repair",
    "client_outbound",
}
functions = [
    node
    for node in tree.body
    if isinstance(node, ast.FunctionDef) and node.name in wanted
]
assert {node.name for node in functions} == wanted

namespace = {
    "Any": Any,
    "Node": object,
    "SingBoxAccountSecret": object,
    "SingBoxAccountError": RuntimeError,
    "CERT_PATH": "/etc/twinpanel/sing-box/cert.pem",
    "json": json,
}
exec(
    compile(
        ast.Module(body=functions, type_ignores=[]),
        str(SINGBOX_PATH),
        "exec",
    ),
    namespace,
)

client_outbound = namespace["client_outbound"]
requires_repair = namespace["naive_client_item_requires_repair"]

node = SimpleNamespace(
    public_domain=None,
    public_ip="203.0.113.10",
)

naive_secret = SimpleNamespace(
    protocol="naive",
    username="tp-sub-17",
    password="synthetic-naive-password",
    uuid=None,
    userkey=None,
)
naive_inbound = {
    "listen_port": 443,
    "network": "udp",
    "quic_congestion_control": "bbr",
    "tls": {
        "certificate_path": "/etc/twinpanel/sing-box/cert.pem",
    },
}
naive_certificate = """-----BEGIN CERTIFICATE-----
VEVTVF9DRVJUSUZJQ0FURQ==
-----END CERTIFICATE-----
"""

naive = client_outbound(
    node,
    naive_secret,
    naive_inbound,
    server="203.0.113.10",
    port=443,
    tls_certificate=naive_certificate,
)
assert naive["type"] == "naive"
assert naive["quic"] is True
assert naive["quic_congestion_control"] == "bbr"
assert naive["tls"]["enabled"] is True
assert naive["tls"]["server_name"] == "203.0.113.10"
assert "insecure" not in naive["tls"]
assert naive["tls"]["certificate"] == naive_certificate

# The fix is protocol-specific. Existing TLS behavior for the other sing-box
# client outbounds must remain unchanged.
hysteria_secret = SimpleNamespace(
    protocol="hysteria2",
    username="tp-sub-17",
    password="synthetic-hysteria-password",
    uuid=None,
    userkey=None,
)
hysteria_inbound = {
    "listen_port": 443,
    "tls": {
        "certificate_path": "/etc/twinpanel/sing-box/cert.pem",
    },
}
hysteria = client_outbound(
    node,
    hysteria_secret,
    hysteria_inbound,
    server="203.0.113.10",
    port=443,
)
assert hysteria["tls"]["insecure"] is True

legacy_outbound = {
    "type": "naive",
    "tag": "twinpanel-naive",
    "server": "203.0.113.10",
    "server_port": 443,
    "username": "tp-sub-17",
    "password": "synthetic-naive-password",
    "tls": {
        "enabled": True,
        "server_name": "203.0.113.10",
        "insecure": True,
    },
}
legacy_item = {
    "outbound": legacy_outbound,
    "config": json.dumps({"outbounds": [legacy_outbound]}),
}
assert requires_repair(legacy_item) is True

# v218 removed tls.insecure but did not provide a replacement trust anchor.
# That payload validates syntactically yet fails the real TLS handshake with
# Chromium ERR_CERT_AUTHORITY_INVALID (-202), so it also needs self-healing.
untrusted_v218 = dict(naive)
untrusted_v218["tls"] = {
    "enabled": True,
    "server_name": "203.0.113.10",
}
untrusted_v218_item = {
    "outbound": untrusted_v218,
    "config": json.dumps({"outbounds": [untrusted_v218]}),
}
assert requires_repair(untrusted_v218_item) is True

# Detect legacy payloads even if only the serialized config representation is
# present, because older credentials may not retain the convenience outbound.
assert requires_repair({"config": legacy_item["config"]}) is True
assert requires_repair({"config": untrusted_v218_item["config"]}) is True

fixed_item = {
    "outbound": naive,
    "config": json.dumps({"outbounds": [naive]}),
}
assert requires_repair(fixed_item) is False

# The account provisioning path must read the server's actual configured
# certificate and carry it into the Naive client item. This keeps verification
# enabled without reintroducing the unsupported tls.insecure field.
for marker in (
    "async def _read_naive_tls_certificate(",
    'if secret.protocol == "naive":',
    "tls_certificate = await _read_naive_tls_certificate(conn, inbound)",
    "tls_certificate=tls_certificate",
    'tls["certificate"] = certificate + "\\n"',
):
    assert marker in singbox_source, marker

# Reconcile must continue to classify bad complete Naive payloads as repair
# candidates so existing credentials can refresh without rotating identity.
for marker in (
    "def _reconcile_credential_state(",
    'return "legacy_naive_client"',
    "protocol: _reconcile_credential_state(credentials.get(protocol))",
    "current_state = _reconcile_credential_state(current)",
    '"legacy_naive_client"',
    "_LEGACY_REPAIR_STATES",
):
    assert marker in reconcile_source, marker

print("NAIVE_CLIENT_TLS_V218_SMOKE=PASS")
print("NAIVE_TLS_INSECURE=OMITTED")
print("NAIVE_TLS_CERTIFICATE=EMBEDDED")
print("OTHER_TLS_BEHAVIOR=PRESERVED")
print("LEGACY_NAIVE_DELIVERY=SELF_HEAL_CANDIDATE")
