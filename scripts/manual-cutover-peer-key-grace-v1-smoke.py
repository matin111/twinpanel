from pathlib import Path

PATCH = Path("backend/app/manual_cutover_peer_key_grace_v1.py").read_text()
INIT = Path("backend/app/__init__.py").read_text()

assert "TWINPANEL_MANUAL_CUTOVER_PEER_KEY_GRACE_V1" in PATCH
assert 'reason == "waiting_peer_key"' in PATCH
assert "await asyncio.sleep(1.0)" in PATCH
assert 'timeout_seconds: float = 30.0' in PATCH
assert '"manual_cutover_agent_confirmation_timeout"' in PATCH
assert "return False, last_snapshot, reason[:900]" in PATCH
assert "_wait_manual_cutover_acceptance_v257" in PATCH
assert "_install_manual_cutover_peer_key_grace_v1" in INIT
assert "_install_manual_cutover_peer_key_grace_v1()" in INIT

print("MANUAL_CUTOVER_PEER_KEY_GRACE_V1_SMOKE_OK")
