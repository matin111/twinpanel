"""Runtime-family reconciliation, not a per-subscriber provisioning queue.

One controller desired-state snapshot is applied to each installed service
family through the already-existing node-wide adapters. Service families can
run concurrently because their remote state and DB credential protocol rows
are disjoint. No legacy user-level worker, queue or per-user SSH.
"""
from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from ..protocol_account_registry import ALL_PROTOCOL_SET
from ..singbox_subscription_accounts import SINGBOX_PROTOCOLS


@dataclass(frozen=True)
class RuntimeFamily:
    name: str
    adapter: str
    protocols: frozenset[str]


FAMILIES = (
    RuntimeFamily("l2tp","twinpanel_central_l2tp_node_bulk_v1.py",frozenset({"l2tp"})),
    RuntimeFamily("cisco","twinpanel_central_cisco_node_bulk_v1.py",frozenset({"cisco"})),
    RuntimeFamily("singbox","twinpanel_central_singbox_node_bulk_v1.py",frozenset(SINGBOX_PROTOCOLS)),
    RuntimeFamily("xray","twinpanel_central_xray_node_bulk_v1.py",frozenset({"v2ray"})),
    RuntimeFamily("openvpn","twinpanel_central_openvpn_node_bulk_v1.py",frozenset({"openvpn"})),
    RuntimeFamily("wireguard","twinpanel_central_wireguard_node_bulk_v1.py",frozenset({"wireguard"})),
    RuntimeFamily("mieru","twinpanel_central_mieru_node_bulk_v1.py",frozenset({"mieru"})),
    RuntimeFamily("trusttunnel","twinpanel_central_trusttunnel_node_bulk_v1.py",frozenset({"trusttunnel"})),
    RuntimeFamily("amneziawg","twinpanel_central_amneziawg_node_bulk_v1.py",frozenset({"amneziawg"})),
    RuntimeFamily("sudoku","twinpanel_central_sudoku_shared_v2.py",frozenset({"sudoku"})),
)


def validate_runtime_families(families=FAMILIES):
    seen = set()
    for family in families:
        overlap = seen.intersection(family.protocols)
        if overlap:
            raise RuntimeError("CENTRAL_RUNTIME_PROTOCOL_ASSIGNED_TWICE")
        seen.update(family.protocols)
        if not family.protocols or not family.adapter.startswith("twinpanel_central_"):
            raise RuntimeError("CENTRAL_RUNTIME_INVALID_ADAPTER")
    if seen != ALL_PROTOCOL_SET:
        raise RuntimeError("CENTRAL_RUNTIME_PROTOCOL_PARITY_MISSING")
    return families


def adapter_command(family: RuntimeFamily, node_id: int, limit: int,
                    backend: Path, executable: str = sys.executable):
    command = [
        executable, str(backend/"scripts"/family.adapter),
        "--node-id",str(node_id),"--limit",str(limit),
    ]
    if family.name == "xray":
        command[command.index("--limit")+1] = "100"
        command.append("--all")
    command += ["--apply","--confirm-node-id",str(node_id)]
    return command


async def reconcile_runtime_families(
    node_id: int, limit: int, backend: Path,
    *, families=FAMILIES, timeout_seconds=1200, max_concurrent_families=3,
):
    """One remote protocol-wide operation per daemon family; nothing per user.

    All failures keep the Exit hidden. No returned log contains credentials.
    A nonzero return is not interpreted as customer-ready state.
    """
    validate_runtime_families(families)
    if node_id <= 0 or limit <= 0 or max_concurrent_families < 1:
        raise ValueError("CENTRAL_RUNTIME_INVALID_TARGET")
    # Limit contention on the controller and on shared remote SSH/database
    # resources. This is concurrency across DAEMONS, never a per-user queue.
    throttle = asyncio.Semaphore(max_concurrent_families)
    async def run_family(family):
        command=adapter_command(family,node_id,limit,backend)
        async with throttle:
            proc=await asyncio.create_subprocess_exec(
                *command,cwd=str(backend),
                env={**os.environ,"PYTHONPATH":str(backend)},
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                code=await asyncio.wait_for(proc.wait(),timeout_seconds)
            except (asyncio.TimeoutError,asyncio.CancelledError):
                proc.terminate()
                try:await asyncio.wait_for(proc.wait(),10)
                except asyncio.TimeoutError:proc.kill();await proc.wait()
                raise
            return family.name,int(code)
    results=await asyncio.gather(
        *(run_family(family) for family in families),
        return_exceptions=True,
    )
    failed=[]
    succeeded=[]
    for family,result in zip(families,results):
        if isinstance(result,BaseException):
            failed.append(family.name)
        else:
            name,code=result
            (succeeded if code==0 else failed).append(name)
    return {
        "ok":not failed,
        "succeeded":sorted(succeeded),
        "failed":sorted(failed),
        "runtime_families":len(families),
    }
