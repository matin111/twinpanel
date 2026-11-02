from pathlib import Path

PATCH = Path("backend/app/tunnel_agent_bootstrap_resilience_v1.py").read_text()
INIT = Path("backend/app/__init__.py").read_text()

assert "TWINPANEL_TUNNEL_AGENT_BOOTSTRAP_RESILIENCE_V1" in PATCH
assert "routers.tunnels._ensure_fabric_for_tunnel_node" in PATCH
assert "_dependency_bootstrap_failure" in PATCH
assert '"venv/bin/pip"' in PATCH
assert '"files.pythonhosted.org"' in PATCH
assert "systemctl is-active twinpanel-agent.service" in PATCH
assert "/opt/twinpanel-agent/venv/bin/python -c" in PATCH
assert 'service != "active" or deps != "ok"' in PATCH
assert "_install_tunnel_fabric_base" in PATCH
assert '"upgrade_deferred": True' in PATCH
assert "tunnels._ensure_fabric_for_tunnel_node = _ensure_fabric_resilient" in PATCH
assert "provision._install_or_upgrade_agent =" not in PATCH
assert "_install_tunnel_agent_bootstrap_resilience_v1" in INIT
assert "_install_tunnel_agent_bootstrap_resilience_v1()" in INIT

print("TUNNEL_AGENT_BOOTSTRAP_RESILIENCE_V1_SMOKE_OK")
