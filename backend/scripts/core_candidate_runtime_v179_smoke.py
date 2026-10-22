from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"


def text(path: str) -> str:
    value = (ROOT / path).read_text(encoding="utf-8")
    ast.parse(value)
    return value


core = text("backend/app/transport_candidates/core_candidate_runtime_v179.py")
reference = text("backend/app/tp27_reference_runtime_v91.py")
retry = text("backend/app/smart_candidate_retry_guard_v169.py")
fair = text("backend/app/smart_candidate_fair_retry_v171.py")
manager = text("backend/app/tunnel_transport_manager_v12.py")

# The core policy must be reached from transport_candidates package bootstrap,
# not only from tunnel_transport_manager_v12.main(). V91 is invoked directly
# by transport_candidates.__init__ in every API / worker / manager process.
assert "apply_core_candidate_runtime_v179" in reference
assert "candidate_core=v179" in reference
assert "from ..tp27_reference_runtime_v91 import apply_tp27_reference_runtime_v91" in text(
    "backend/app/transport_candidates/__init__.py"
)
assert "apply_tp27_reference_runtime_v91()" in text(
    "backend/app/transport_candidates/__init__.py"
)

# API canaries must get all candidate aliases, not only common.probe.
for marker in (
    "candidate_common.probe = probe_v179",
    "tp27_fast.probe = probe_v179",
    "tp27_masque.probe = probe_v179",
    "tp27_tcp_direct.probe = probe_v179",
    "tp27_masque._install_profile = masque_install_profile_ready_v179",
):
    assert marker in core, marker

# MASQUE must prove a real CONNECT-IP session before generic peer ping.
assert "TP27_MASQUE_CLIENT_READY" in core
assert "TP27_MASQUE_SESSION_UP" in core
assert "masque_session_not_ready:" in core
assert core.index("await _original_masque_install_profile") < core.index(
    "TP27_MASQUE_CLIENT_READY"
)

# TCP health must use source-bound sockets; public IP lookup is telemetry only.
assert "s.bind((src,0))" in core
assert "s.connect((host,int(port)))" in core
assert "1.1.1.1" in core and "1.0.0.1" in core and "8.8.8.8" in core
assert "External public-IP services are telemetry only" in core
assert "net.ipv4.conf.{iface}.rp_filter=2" in core

# A new release gets one immediate validation attempt. Same-release retry still
# uses SmartAuto's existing INSTALL_RETRY_SECONDS cooldown.
assert "last_install_attempt_release" in retry
assert "last_install_completed_release" in retry
assert "last_release != current_release" in retry
assert "last_install_attempt_release" in fair
assert "last_install_completed_release" in fair
assert "last_release != current_release" in fair
assert "age < float(smart.INSTALL_RETRY_SECONDS)" in fair

# Existing manager layers remain installed; V179 is process-invariant core,
# not a replacement for qualification/benchmark/failover policy.
for marker in (
    "apply_smart_candidate_retry_guard_v169",
    "apply_smart_candidate_fair_retry_v171",
    "apply_candidate_dataplane_v175",
):
    assert marker in manager

print("CORE_CANDIDATE_RUNTIME_V179_SMOKE_OK")
