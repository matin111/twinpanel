from __future__ import annotations

"""Regression: live OpenVPN accounting must not depend on heavy Xray sweeps."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
controller = (ROOT / "app" / "quota_process_isolation_v1.py").read_text(encoding="utf-8")
heavy = (ROOT / "scripts" / "twinpanel_quota_reconcile_worker_v1.py").read_text(encoding="utf-8")
ast.parse(controller)
ast.parse(heavy)

assert "async def _fast_openvpn_presence_worker()" in controller
assert "reconcile_openvpn_quota_runtime_once(), timeout=75.0" in controller
assert 'name="openvpn-fast-presence"' in controller
assert "30.0 - elapsed" in controller
assert "OPENVPN_FAST_PRESENCE_ERRORS" in controller
assert "OPENVPN_FAST_PRESENCE_CHANGES" in controller
assert '("openvpn", reconcile_openvpn_quota_runtime_once)' not in heavy
assert '("l2tp", reconcile_l2tp_quota_runtime_once)' in heavy
assert '("cisco_xray", reconcile_quota_runtime_once)' in heavy

print("OPENVPN_FAST_PRESENCE_INDEPENDENT_OWNER=PASS")
print("OPENVPN_FAST_PRESENCE_BOUNDED_INTERVAL=PASS")
print("OPENVPN_FAST_PRESENCE_NO_DUPLICATE_WRITER=PASS")
