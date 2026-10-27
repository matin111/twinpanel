from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "backend/app/xray_adaptive_three_profiles_v47.py"
COMPOSE = ROOT / "backend/app/self_hosted_runtime.py"

runtime = RUNTIME.read_text(encoding="utf-8")
compose = COMPOSE.read_text(encoding="utf-8")

required_runtime = (
    'PROFILE_TCP_REALITY = "tcp_reality"',
    "TCP_REALITY_TARGET_OFFSET = 1005",
    "TCP_REALITY_PUBLIC_BASE = 38000",
    '"network": "tcp"',
    '"security": "reality"',
    '("security", "reality")',
    '("type", "tcp")',
    "xray_customer_xhttp_v46.apply_xray_customer_xhttp_v46()",
    "xray_modern_runtime.PROFILE_WS,\n            xray_modern_runtime.PROFILE_XHTTP,\n            PROFILE_TCP_TLS,",
    "xray_modern_runtime.PROFILE_XHTTP,\n        xray_modern_runtime.PROFILE_GRPC,\n        PROFILE_TCP_REALITY,",
    "if len(profiles) != 3:",
    "fake_tls=0",
    "uuid_preserved=1",
    "reality_identity_reused=1",
)

for marker in required_runtime:
    if marker not in runtime:
        raise SystemExit(f"missing V47 marker: {marker}")

if "TCP_REALITY_PUBLIC_BASE = 29000" in runtime:
    raise SystemExit("V47 collides with TUIC public range")
if "TCP_REALITY_PUBLIC_BASE = 40000" in runtime:
    raise SystemExit("V47 collides with Sudoku public range")
if '"id": "tcp_simple"' in runtime:
    raise SystemExit("V47 must not synthesize plaintext tcp_simple")

import_pos = compose.find("apply_xray_adaptive_three_profiles_v47")
policy_call = compose.find("    apply_xray_customer_profile_policy_v30()")
v47_call = compose.find("    apply_xray_adaptive_three_profiles_v47()")
service_call = compose.find("    apply_tunnel_service_connections_admin_runtime()")

if import_pos < 0 or v47_call < 0:
    raise SystemExit("V47 is not composed into self-hosted runtime")
if not (policy_call < v47_call < service_call):
    raise SystemExit("V47 composition order must be V30 -> V47 -> Service Connections")

print("Xray adaptive three-profile V47 smoke: PASS")
