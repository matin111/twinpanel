from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import Node, NodeType
from .routers import provision
from . import node_bootstrap_control_v63 as v63
from . import node_bootstrap_control_v72 as v72
from . import ssh_management_fallback_v61 as v61


# ============================================================
# TWINPANEL NODE BOOTSTRAP CONTROL PLANE V74
#
# Production root cause (2026-10-28):
# V72 promises one direct Controller -> Exit saved-SSH attempt followed by one
# sequential native Iran fallback. However V72's saved path called
# v66._BASE_EXIT_MANAGEMENT. Through the V61 -> V63 -> V64 compatibility capture
# chain that symbol resolves to V61, and V61 itself races direct SSH against up
# to four local OpenSSH ProxyCommand relays (`ssh -> Iran -> nc -> private:22`).
#
# Background accounting opens saved Exit management every few seconds. The
# accidental nested V61 race therefore spawned repeated local ssh/nc fanout
# below the single Uvicorn worker and correlated with request starvation and
# accepted-but-unread HTTP sockets.
#
# V74 restores the architecture V72 documents:
#   1) exactly one direct saved SSH attempt using the original connector;
#   2) only after direct failure, select one Iran management node;
#   3) open that Iran session directly (no Exit relay race);
#   4) run V72/V73 native OpenSSH on Iran to reach the Exit.
#
# V61 remains installed for legacy compatibility callers. V74 only makes the
# active saved-node control path direct-first and sequential. No tunnel, route,
# firewall, TP27, VXLAN, VPN dataplane, credential, or quota semantics change.
# ============================================================


_RUNTIME_APPLIED = False

# Capture the connector which V61 itself wrapped at package initialization.
# This is the canonical direct saved-SSH implementation from routers.provision,
# before any Exit relay compatibility layer was installed.
_DIRECT_SAVED_CONNECT = v61._ORIGINAL_SSH_CONNECT_SAVED


async def _open_iran_management_direct(iran: Node, db: Session):
    try:
        return await _DIRECT_SAVED_CONNECT(iran, db)
    except asyncio.CancelledError:
        raise
    except BaseException as exc:
        raise v72.NativeBootstrapError(
            "iran_ssh",
            v72._safe_error(exc),
        ) from exc


async def _saved_exit_via_iran_native_v74(
    node: Node,
    node_access,
    node_key: Path,
    iran: Node,
    db: Session,
):
    iran_conn = await _open_iran_management_direct(iran, db)

    try:
        try:
            private_key = node_key.read_text(encoding="utf-8")
        except OSError as exc:
            raise v72.NativeBootstrapError(
                "exit_auth",
                "saved_private_key_unreadable",
            ) from exc

        # node_bootstrap_control_v73 replaces this class in v72's module globals
        # at import time, so the deterministic failed-open cleanup remains active.
        return await v72.NativeIranExitConnection.open_with_private_key(
            iran_conn,
            host=str(node.public_ip),
            port=int(node_access.ssh_port or 22),
            username=str(node_access.ssh_username or "root"),
            private_key=private_key,
        )

    except asyncio.CancelledError:
        await v72._close_quietly(iran_conn)
        raise
    except BaseException:
        await v72._close_quietly(iran_conn)
        raise


async def ssh_connect_saved_v74(node: Node, db: Session):
    # Iran and any future non-Exit management remain direct-only, matching V61's
    # original non-Exit behavior without entering the legacy relay selector.
    if node.node_type != NodeType.EXIT:
        return await _DIRECT_SAVED_CONNECT(node, db)

    direct_error = "not_attempted"

    try:
        return await _DIRECT_SAVED_CONNECT(node, db)
    except asyncio.CancelledError:
        raise
    except BaseException as exc:
        direct_error = v72._safe_error(exc)

    node_access = v63._access(db, int(node.id))
    if node_access is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "اتصال مدیریتی نود خارج ناموفق بود: "
                f"direct={direct_error} | exit_auth=saved_access_missing"
            ),
        )

    node_key = Path(str(node_access.private_key_path or ""))
    if not node_key.exists():
        raise HTTPException(
            status_code=409,
            detail=(
                "اتصال مدیریتی نود خارج ناموفق بود: "
                f"direct={direct_error} | exit_auth=saved_private_key_missing"
            ),
        )

    iran = v72._first_management_iran(db, node)
    if iran is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "اتصال مدیریتی نود خارج ناموفق بود: "
                f"direct={direct_error} | iran_ssh=no_management_candidate"
            ),
        )

    try:
        return await _saved_exit_via_iran_native_v74(
            node,
            node_access,
            node_key,
            iran,
            db,
        )
    except asyncio.CancelledError:
        raise
    except BaseException as exc:
        fallback_error = v72._safe_error(exc)
        raise HTTPException(
            status_code=400,
            detail=(
                "اتصال مدیریتی نود خارج ناموفق بود: "
                f"direct={direct_error} | "
                f"via_iran_native_{int(iran.id)}_{node.public_ip}="
                f"{fallback_error}"
            ),
        ) from exc


def apply_node_bootstrap_control_v74() -> None:
    global _RUNTIME_APPLIED
    if _RUNTIME_APPLIED:
        return

    # First-install bootstrap remains V72/V73. Only saved-node management is
    # corrected so recurring background collectors cannot re-enter V61 fanout.
    provision.ssh_connect_saved = ssh_connect_saved_v74
    _RUNTIME_APPLIED = True


apply_node_bootstrap_control_v74()


__all__ = [
    "apply_node_bootstrap_control_v74",
    "ssh_connect_saved_v74",
]
