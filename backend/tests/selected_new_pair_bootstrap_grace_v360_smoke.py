"""Guard new-pair bootstrap grace without relaxing existing manual cutovers."""
from pathlib import Path

source = (Path(__file__).resolve().parents[1] / "app/routers/modern_transports.py").read_text()
start = source.index("async def _wait_manual_cutover_acceptance_v257(")
end = source.index("\ndef _rollback_manual_cutover_v257(", start)
body = source[start:end]
assert "timeout_seconds > 30.0" in body, "grace must be limited to new-pair bootstrap"
assert "elapsed < min(45.0, timeout_seconds)" in body
assert "waiting_peer_key" in body
assert "not_installed" in body
assert "manual_cutover_peer_not_reachable" in body
assert "all(item[\"accepted\"] for item in last_snapshot)" in body
assert "return False, last_snapshot, str(reason)[:900]" in body, "real errors must still rollback"
assert '"manual_cutover_agent_confirmation_timeout"' in body, "no indefinite wait"
print("bootstrap cutover safety smoke passed")
