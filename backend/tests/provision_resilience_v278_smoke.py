from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESILIENCE = ROOT / "backend" / "app" / "provision_resilience_v278.py"
HOSTED = ROOT / "backend" / "app" / "self_hosted_runtime.py"
LEGACY = ROOT / "backend" / "app" / "routers" / "provision.py"


def main() -> None:
    source = RESILIENCE.read_text(encoding="utf-8")
    hosted = HOSTED.read_text(encoding="utf-8")
    legacy = LEGACY.read_text(encoding="utf-8")

    # Parse every changed Python module before checking behavioral anchors.
    ast.parse(source)
    ast.parse(hosted)

    # Production regression: legacy /install commits Node before Agent/access.
    legacy_commit = legacy.index("db.add(node); db.commit(); db.refresh(node)")
    legacy_agent = legacy.index("agent=await _install_or_upgrade_agent", legacy_commit)
    legacy_access = legacy.index("await _ensure_node_key_on_remote", legacy_agent)
    assert legacy_commit < legacy_agent < legacy_access

    # V278 resumes the exact partial Iran row instead of creating a duplicate.
    assert "by_name = _active_node_by_name" in source
    assert "by_ip = _active_node_by_ip" in source
    assert "resumed = node is not None" in source
    assert "refresh_partial_node" in source
    assert '"resumable": node is not None' in source
    assert '"code": "iran_node_provision_partial"' in source

    # Saved management access is established before network-dependent Agent work.
    access_at = source.index('stage = "save_access"')
    agent_at = source.index('stage = "install_agent"')
    assert access_at < agent_at

    # Iran remains tunnel-only; no customer protocol install path is introduced.
    for flag in (
        "payload.install_cisco = False",
        "payload.install_openvpn = False",
        "payload.install_wireguard = False",
        "payload.install_l2tp = False",
        "payload.install_v2ray = False",
    ):
        assert flag in source

    # Existing healthy Agent environments must not touch PyPI at all. The V278
    # fallback may use pip only when dependencies are actually missing, but it
    # must never perform the production-failing pip self-upgrade first.
    assert "existing_venv" in source
    assert "python3-httpx python3-psutil" in source
    assert "--system-site-packages" in source
    assert "--disable-pip-version-check install --retries 2 --timeout 15" in source
    assert "pip install --upgrade pip >/dev/null" not in source
    assert "pip install --upgrade pip >/dev/null" in legacy

    # Exit authority is preserved by delegation to the V70-captured base paths.
    assert "if payload.node_type != NodeType.IRAN:" in source
    assert "return await _BASE_INSTALL_NODE(payload, request, db)" in source
    assert "return await _BASE_AGENT_INSTALL(conn, node_id, api_base)" in source

    # Runtime activation patches the already-built FastAPI dependant in place.
    assert "route.dependant.call = install_node_v278" in source
    import_at = hosted.index("from .provision_resilience_v278 import")
    apply_at = hosted.index("apply_provision_resilience_v278()", import_at)
    assert import_at < apply_at

    # Direct SessionLocal import avoids relying on attributes of provision.py.
    assert "from .database import SessionLocal, get_db" in source
    assert "provision.SessionLocal" not in source

    print("PROVISION_RESILIENCE_V278=PASS")


if __name__ == "__main__":
    main()
