from __future__ import annotations

import asyncio
import re
import shlex

from sqlalchemy.orm import Session

from .models import Node, Tunnel
from .routers.provision import ssh_connect_saved


KERNEL_GRE_NAME = "kernel_gre"
_AGENT_PATH = "/opt/twinpanel-agent/agent.py"
_AGENT_BACKUP = "/opt/twinpanel-agent/agent.py.pre-kernel-gre-v21"


# ============================================================
# TWINPANEL KERNEL GRE AGENT COMPAT V21
#
# Existing production Agents predate kernel_gre as an active data-plane name.
# Their service-routing code is already interface-agnostic, but the health /
# reporting allow-list must know kernel_gre or a manual selection can be
# reported back as another transport.
#
# This module provides two ownership-safe paths:
#   1. patch the controller-side make_agent() result for all future upgrades;
#   2. atomically upgrade an already-installed Agent when kernel_gre itself is
#      installed/reinstalled.
#
# No VPN daemon, protocol config, route or firewall rule is changed here.
# ============================================================


def patch_agent_source(source: str) -> str:
    text = str(source or "")

    marker = "# TWINPANEL_AGENT_KERNEL_GRE_V21"
    if marker in text:
        return text

    match = re.search(
        r"(?P<head>\n\s*managed_candidates\s*=\s*\{)(?P<body>.*?)(?P<tail>\n\s*\})",
        text,
        flags=re.DOTALL,
    )

    if not match:
        raise RuntimeError("agent_managed_candidates_block_missing")

    body = match.group("body")

    if '"kernel_gre"' not in body and "'kernel_gre'" not in body:
        indent_match = re.search(r"\n(?P<indent>\s*)[\"']backhaul[\"']\s*,", body)
        if not indent_match:
            raise RuntimeError("agent_backhaul_candidate_anchor_missing")

        indent = indent_match.group("indent")
        body = body + f'\n{indent}"kernel_gre",'

    replacement = (
        match.group("head")
        + body
        + match.group("tail")
        + "\n\n            "
        + marker
    )

    return text[: match.start()] + replacement + text[match.end() :]


_ORIGINAL_MAKE_AGENT = None


def install_make_agent_hook() -> None:
    """Install once in the API process; safe to call repeatedly."""
    global _ORIGINAL_MAKE_AGENT

    from .routers import provision

    current = provision.make_agent

    if getattr(current, "_kernel_gre_v21", False):
        return

    if _ORIGINAL_MAKE_AGENT is None:
        _ORIGINAL_MAKE_AGENT = current

    original = _ORIGINAL_MAKE_AGENT

    def make_agent_v21(node_id: int, api_base: str) -> str:
        return patch_agent_source(
            original(node_id, api_base)
        )

    make_agent_v21._kernel_gre_v21 = True
    provision.make_agent = make_agent_v21


_REMOTE_PATCH = r'''
from pathlib import Path
import os
import py_compile
import shutil

path = Path("/opt/twinpanel-agent/agent.py")
backup = Path("/opt/twinpanel-agent/agent.py.pre-kernel-gre-v21")
marker = "# TWINPANEL_AGENT_KERNEL_GRE_V21"

if not path.exists():
    print("TP_AGENT_COMPAT=missing")
else:
    text = path.read_text(encoding="utf-8")

    if marker in text:
        print("TP_AGENT_COMPAT=already")
    else:
        start = text.find("managed_candidates = {")
        anchor = text.find('"backhaul",', start)
        end = text.find("\n            }", anchor)

        if start < 0 or anchor < 0 or end < 0:
            print("TP_AGENT_COMPAT=pattern_missing")
        else:
            insertion = '\n                "kernel_gre",'
            updated = text[:end] + insertion + text[end:]
            updated = updated[:end + len(insertion)] + "\n\n            " + marker + updated[end + len(insertion):]

            tmp = path.with_suffix(".py.new-kernel-gre-v21")
            tmp.write_text(updated, encoding="utf-8")
            os.chmod(tmp, 0o600)

            try:
                py_compile.compile(str(tmp), doraise=True)
            except Exception as exc:
                tmp.unlink(missing_ok=True)
                print("TP_AGENT_COMPAT=compile_failed:" + type(exc).__name__)
            else:
                if not backup.exists():
                    shutil.copy2(path, backup)
                    os.chmod(backup, 0o600)

                os.replace(tmp, path)
                os.chmod(path, 0o600)
                print("TP_AGENT_COMPAT=patched")
'''


async def ensure_remote_agent_compat(conn) -> dict:
    result = await conn.run(
        "python3 - <<'PY'\n"
        + _REMOTE_PATCH
        + "\nPY\ntrue\n",
        check=False,
        timeout=30,
    )

    text = (result.stdout or "").strip()

    if "TP_AGENT_COMPAT=missing" in text:
        raise RuntimeError("twinpanel_agent_missing")

    if "TP_AGENT_COMPAT=pattern_missing" in text:
        raise RuntimeError("twinpanel_agent_pattern_missing")

    if "TP_AGENT_COMPAT=compile_failed" in text:
        raise RuntimeError(text[-500:])

    changed = "TP_AGENT_COMPAT=patched" in text
    already = "TP_AGENT_COMPAT=already" in text

    if not (changed or already):
        raise RuntimeError("twinpanel_agent_compat_unknown:" + text[-500:])

    if changed:
        restart = await conn.run(
            "set +e\n"
            "systemctl restart twinpanel-agent.service >/dev/null 2>&1 || true\n"
            "sleep 2\n"
            "STATE=\"$(systemctl is-active twinpanel-agent.service 2>/dev/null || true)\"\n"
            "echo TP_AGENT_STATE=$STATE\n"
            "true\n",
            check=False,
            timeout=20,
        )

        state_text = (restart.stdout or "").strip()
        if "TP_AGENT_STATE=active" not in state_text:
            raise RuntimeError("twinpanel_agent_restart_failed:" + state_text[-500:])

    return {
        "ok": True,
        "changed": changed,
        "already": already,
    }


async def ensure_pair_agent_compat(
    tunnel_id: int,
    db: Session,
) -> dict:
    tunnel = db.get(Tunnel, int(tunnel_id))
    if tunnel is None:
        raise RuntimeError("tunnel_not_found")

    iran = db.get(Node, int(tunnel.iran_node_id))
    exit_node = db.get(Node, int(tunnel.exit_node_id))
    if iran is None or exit_node is None:
        raise RuntimeError("tunnel_nodes_missing")

    ci = ce = None

    try:
        ci, ce = await asyncio.gather(
            ssh_connect_saved(iran, db),
            ssh_connect_saved(exit_node, db),
        )

        iran_result, exit_result = await asyncio.gather(
            ensure_remote_agent_compat(ci),
            ensure_remote_agent_compat(ce),
        )

        return {
            "iran": iran_result,
            "exit": exit_result,
        }

    finally:
        for conn in (ci, ce):
            if conn is not None:
                try:
                    conn.close()
                    await conn.wait_closed()
                except Exception:
                    pass
