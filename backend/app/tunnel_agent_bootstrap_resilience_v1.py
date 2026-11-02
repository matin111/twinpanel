from __future__ import annotations

from typing import Any


# TWINPANEL_TUNNEL_AGENT_BOOTSTRAP_RESILIENCE_V1
#
# Managed Tunnel creation should not be blocked only because an already-running
# Node Agent cannot reach PyPI during its opportunistic upgrade. The normal
# bootstrap path remains authoritative. We only recover a narrow dependency
# bootstrap failure when the existing Agent service is still active and its
# current Python environment can import the dependencies the Agent needs.
#
# Agent upgrade/repair endpoints are intentionally untouched: this patch wraps
# only routers.tunnels._ensure_fabric_for_tunnel_node.

_INSTALLED = False
_ORIGINAL = None

_DEPENDENCY_FAILURE_MARKERS = (
    "venv/bin/pip",
    "files.pythonhosted.org",
    "temporary failure in name resolution",
    "could not install packages",
    "failed to establish a new connection",
    "name resolution",
)


def _dependency_bootstrap_failure(exc: BaseException) -> bool:
    text = str(exc or "").strip().lower()
    return any(marker in text for marker in _DEPENDENCY_FAILURE_MARKERS)


async def _ensure_fabric_resilient(node: Any, db: Any) -> dict:
    assert _ORIGINAL is not None

    try:
        return await _ORIGINAL(node, db)
    except Exception as exc:
        if not _dependency_bootstrap_failure(exc):
            raise

        # Import lazily to avoid changing router import ordering during package
        # initialization. This is the exact saved-management path used by the
        # canonical bootstrap implementation.
        from .routers import tunnels

        conn = await tunnels.ssh_connect_saved(node, db)
        try:
            service = (
                await tunnels.cmd(
                    conn,
                    "systemctl is-active twinpanel-agent.service 2>/dev/null || true",
                    check=False,
                )
            ).strip().lower()

            deps = (
                await tunnels.cmd(
                    conn,
                    "/opt/twinpanel-agent/venv/bin/python -c "
                    "'import httpx,psutil; print(\"ok\")' 2>/dev/null || true",
                    check=False,
                )
            ).strip().lower()

            # Fail closed unless an existing Agent is genuinely runnable.
            if service != "active" or deps != "ok":
                raise

            fabric = await tunnels._install_tunnel_fabric_base(conn, node)
            if not isinstance(fabric, dict) or fabric.get("ok") is not True:
                raise RuntimeError(
                    "Tunnel Fabric آماده نشد بعد از deferred Agent upgrade: "
                    + str(fabric)[:1200]
                )

            return {
                "ok": True,
                "node_id": int(node.id),
                "node_name": str(node.name),
                "agent": {
                    "ok": True,
                    "service": "active",
                    "upgrade_deferred": True,
                    "reason": "dependency_bootstrap_unavailable",
                    "error": str(exc)[:1200],
                },
                "fabric": fabric,
            }
        finally:
            conn.close()
            await conn.wait_closed()



def install() -> None:
    global _INSTALLED, _ORIGINAL

    if _INSTALLED:
        return

    from .routers import tunnels

    current = tunnels._ensure_fabric_for_tunnel_node
    if getattr(current, "_twinpanel_tunnel_agent_bootstrap_resilience_v1", False):
        _INSTALLED = True
        return

    _ORIGINAL = current
    _ensure_fabric_resilient._twinpanel_tunnel_agent_bootstrap_resilience_v1 = True
    tunnels._ensure_fabric_for_tunnel_node = _ensure_fabric_resilient
    _INSTALLED = True

    print(
        "TWINPANEL_TUNNEL_AGENT_BOOTSTRAP_RESILIENCE_V1_ACTIVE "
        "scope=tunnel-bootstrap-only active-agent-fallback=1 fabric-authority=unchanged",
        flush=True,
    )
