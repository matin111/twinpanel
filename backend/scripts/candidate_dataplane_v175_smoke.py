from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "backend" / "app" / "candidate_dataplane_v175.py"
MANAGER = ROOT / "backend" / "app" / "tunnel_transport_manager_v12.py"

module_text = MODULE.read_text(encoding="utf-8")
manager_text = MANAGER.read_text(encoding="utf-8")

# Syntax is a hard gate even when application dependencies are not installed.
ast.parse(module_text, filename=str(MODULE))
ast.parse(manager_text, filename=str(MANAGER))

required_module_fragments = (
    'MARKER = "TWINPANEL_CANDIDATE_DATAPLANE_V175"',
    '"tp27_mieru_tcp",\n    "tp27_tcp_direct",\n    "tp27_masque",',
    'net.ipv4.conf.{iface}.rp_filter=2',
    'TCP_EGRESS_TARGETS = (',
    '("1.1.1.1", 443)',
    '("1.0.0.1", 443)',
    '("8.8.8.8", 443)',
    'tcp_egress_probe_failed:',
    'Public-IP discovery is useful telemetry, not a health dependency.',
    'TP27_MASQUE_CLIENT_READY',
    'TP27_MASQUE_SESSION_UP',
    'masque_session_not_ready:',
    'candidate_common.probe = probe_v175',
    'tp27_mieru_tcp.probe = probe_v175',
    'tp27_tcp_direct.probe = probe_v175',
    'smart.candidate_probe = probe_v175',
    'tp27_masque._install_profile = masque_install_profile_ready_v175',
    'smart.AUTO_INSTALL_NAMES = AUTO_INSTALL_ORDER_V175',
)

for fragment in required_module_fragments:
    if fragment not in module_text:
        raise SystemExit(f"V175_MODULE_CONTRACT_MISSING:{fragment}")

required_manager_fragments = (
    'from .candidate_dataplane_v175 import (',
    'apply_candidate_dataplane_v175,',
    'apply_smart_candidate_fair_retry_v171()',
    'apply_candidate_dataplane_v175()',
    'candidate_dataplane=v175',
    'install_order=tp27_fast,tp27_mieru_tcp,tp27_tcp_direct,tp27_masque',
)

for fragment in required_manager_fragments:
    if fragment not in manager_text:
        raise SystemExit(f"V175_MANAGER_CONTRACT_MISSING:{fragment}")

if manager_text.index("apply_smart_candidate_fair_retry_v171()") > manager_text.index(
    "apply_candidate_dataplane_v175()"
):
    raise SystemExit("V175_APPLY_ORDER_INVALID:fair_retry_must_precede_dataplane")

if manager_text.index("apply_candidate_dataplane_v175()") > manager_text.index(
    "apply_adaptive_candidate_qualification_v155()"
):
    raise SystemExit("V175_APPLY_ORDER_INVALID:dataplane_must_precede_qualification")

# The HTTP public-IP services may remain as optional telemetry, but they must
# not be the statement whose exit status decides tcp_egress health.
if 'raise RuntimeError("tcp_egress_probe_failed")' in module_text:
    raise SystemExit("V175_GENERIC_HTTP_TCP_GATE_STILL_PRESENT")

print(
    "CANDIDATE_DATAPLANE_V175_SMOKE_OK "
    "tcp_gate=multi_target_bound_socket "
    "rp_filter=loose "
    "masque=current_process_ready "
    "order=fast,mieru,direct,masque"
)
