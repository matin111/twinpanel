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
    *, families=FAMILIES, timeout_seconds=1200, max_concurrent_families=None,
):
    """One remote protocol-wide operation per daemon family; nothing per user.

    All failures keep the Exit hidden. No returned log contains credentials.
    A nonzero return is not interpreted as customer-ready state.
    """
    # Global protocol parity is checked against the authoritative registry,
    # while delta retries may execute a strict subset of those exact families.
    validate_runtime_families()
    if (len(families) != len(set(families))
            or any(family not in FAMILIES for family in families)):
        raise RuntimeError("CENTRAL_RUNTIME_UNKNOWN_DELTA_FAMILY")
    if max_concurrent_families is None:
        # Eylan-like node-wide snapshots should not wait behind unrelated
        # service families when the controller has adequate CPU headroom.
        # Bound to TWO disjoint families (never per subscriber) and keep
        # small controllers serial. Sudoku remains isolated at the end.
        max_concurrent_families=2 if (os.cpu_count() or 1)>=8 else 1
    if (node_id <= 0 or limit <= 0 or max_concurrent_families < 1
            or max_concurrent_families > 3):
        raise ValueError("CENTRAL_RUNTIME_INVALID_TARGET")
    throttle=asyncio.Semaphore(max_concurrent_families)
    async def run_family(family):
        command=adapter_command(family,node_id,limit,backend)
        async with throttle:
            proc=await asyncio.create_subprocess_exec(
                *command,cwd=str(backend),
                env={**os.environ,"PYTHONPATH":str(backend)},
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            started=asyncio.get_running_loop().time()
            try:
                # Consume output concurrently, avoiding child pipe deadlocks.
                # Never print raw output, which may contain config secrets.
                out,_=await asyncio.wait_for(proc.communicate(),timeout_seconds)
                code=proc.returncode
            except (asyncio.TimeoutError,asyncio.CancelledError):
                proc.terminate()
                try:await asyncio.wait_for(proc.wait(),10)
                except asyncio.TimeoutError:proc.kill();await proc.wait()
                raise
            import json
            markers=[]
            for line in out[-65536:].decode("utf-8",errors="replace").splitlines():
                if any(line.startswith(tag) for tag in (
                    "CENTRAL_WIREGUARD_SAFE_STOP", "SUDOKU_SHARED_SAFE_STOP",
                )):
                    # Only consume a bounded, strictly allowlisted diagnostic.
                    import re
                    hit=re.search(r"['\\\"]reason['\\\"]\\s*:\\s*['\\\"]([A-Z0-9_]{5,90})",line)
                    if hit:markers.append(hit.group(1))
                    else:markers.append("SAFE_STOP_UNCLASSIFIED")
            print("CENTRAL_FAMILY_RESULT",json.dumps({
                "node_id":node_id,"family":family.name,
                "exit_code":int(code),
                "elapsed_seconds":round(asyncio.get_running_loop().time()-started,2),
                "error_codes":markers[-2:],
            }),flush=True)
            return family.name,int(code)
    # Sudoku's live whitelist update/verification is a single shared
    # service-wide restart. Other adapters can saturate the controller's
    # SSH/DB and cause a false timeout. Finish the other daemon families
    # before the single Sudoku apply. Still ONE node operation, no user queue.
    parallel=[family for family in families if family.name!="sudoku"]
    shared=[family for family in families if family.name=="sudoku"]
    in_parallel=await asyncio.gather(
        *(run_family(family) for family in parallel),
        return_exceptions=True,
    )
    isolated=[]
    for family in shared:
        # A single restart/listener verification can be momentarily
        # unavailable after the other family applies. Retry ONCE, only
        # for this node-wide daemon. No subscriber-specific retries.
        result=await asyncio.gather(
            run_family(family),return_exceptions=True,
        )
        outcome=result[0]
        if isinstance(outcome,BaseException) or outcome[1]!=0:
            retry=await asyncio.gather(
                run_family(family),return_exceptions=True,
            )
            outcome=retry[0]
        isolated.append(outcome)
    responses=dict(zip(
        [family.name for family in parallel+shared],
        list(in_parallel)+list(isolated),
    ))
    results=[responses[family.name] for family in families]
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
