from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any


MARKER = "TWINPANEL_QUOTA_PROCESS_ISOLATION_V1"
RESULT_PREFIX = "TWINPANEL_QUOTA_PROCESS_RESULT_V1="
WORKER = Path(__file__).resolve().parents[1] / "scripts" / "twinpanel_quota_reconcile_worker_v1.py"
PROCESS_TIMEOUT_SECONDS = 180
_installed = False


async def _terminate_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()


async def _run_quota_reconcile_process() -> dict[str, Any]:
    """Run canonical quota telemetry outside the interactive API process."""

    if not WORKER.is_file():
        raise RuntimeError("quota_reconcile_worker_missing")

    env = dict(os.environ)
    env["TWINPANEL_QUOTA_WORKER_V1"] = "1"
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(WORKER),
        cwd=str(WORKER.parents[1]),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=PROCESS_TIMEOUT_SECONDS,
        )
    except asyncio.CancelledError:
        await _terminate_process(process)
        raise
    except asyncio.TimeoutError as exc:
        await _terminate_process(process)
        raise RuntimeError("quota_reconcile_worker_timeout") from exc

    output = stdout.decode("utf-8", errors="replace")
    error = stderr.decode("utf-8", errors="replace")
    if process.returncode != 0:
        detail = (error or output)[-1200:].replace("\n", " ")
        raise RuntimeError(
            f"quota_reconcile_worker_failed:{process.returncode}:{detail}"
        )

    payload_line = next(
        (
            line[len(RESULT_PREFIX) :]
            for line in reversed(output.splitlines())
            if line.startswith(RESULT_PREFIX)
        ),
        "",
    )
    if not payload_line:
        raise RuntimeError("quota_reconcile_worker_result_missing")

    payload = json.loads(payload_line)
    if not isinstance(payload, dict):
        raise RuntimeError("quota_reconcile_worker_result_invalid")
    return payload


def install() -> None:
    """Keep quota semantics intact while moving polling out of Uvicorn.

    The existing Cisco/Xray, OpenVPN and L2TP reconcilers remain authoritative.
    Only their scheduling boundary changes: one low-priority worker process runs
    the same three reconciliation functions sequentially, then sleeps for the
    existing customer-maintenance cadence. This prevents synchronous DB/device
    scans and collector bookkeeping from blocking the API event loop.
    """

    global _installed
    if _installed or os.environ.get("TWINPANEL_QUOTA_WORKER_V1") == "1":
        return

    from .services import customer_maintenance as runtime

    async def _fast_cisco_presence_worker() -> None:
        # TWINPANEL_CISCO_FAST_PRESENCE_V104
        # ocserv is authoritative for active Cisco/AnyConnect clients.
        # Run independently of the full OpenVPN/Xray/L2TP quota sweep, whose
        # CPU-heavy provisioning work can delay status by several minutes.
        from .services.quota_runtime_reconcile import (
            reconcile_cisco_quota_runtime_once,
        )

        while True:
            started = asyncio.get_running_loop().time()
            try:
                result = await asyncio.wait_for(
                    reconcile_cisco_quota_runtime_once(), timeout=50.0,
                )
                failed = [
                    (item.get("node_id"), str(item.get("error") or "")[:160])
                    for item in (result.get("nodes") or [])
                    if not item.get("ok")
                ]
                if failed:
                    print("CISCO_FAST_PRESENCE_ERRORS", failed, flush=True)
                refreshed = [
                    item
                    for item in (result.get("nodes") or [])
                    if item.get("opened") or item.get("closed")
                ]
                if refreshed:
                    print("CISCO_FAST_PRESENCE_CHANGES", refreshed, flush=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(
                    "CISCO_FAST_PRESENCE_ERROR",
                    f"{type(exc).__name__}:{str(exc)[:300]}",
                    flush=True,
                )
            elapsed = asyncio.get_running_loop().time() - started
            await asyncio.sleep(max(3.0, 20.0 - elapsed))

    async def _fast_openvpn_presence_worker() -> None:
        # TWINPANEL_OPENVPN_FAST_PRESENCE_V1
        # The full quota sweep can take minutes because Xray and L2TP follow
        # it. Run actual management-socket OpenVPN session accounting on its
        # own 30-second cadence. This task lives in the external worker, never
        # inside a public/API request. The heavy subprocess must not run the
        # same collector concurrently.
        from .services.openvpn_quota_runtime_v106 import (
            reconcile_openvpn_quota_runtime_once,
        )

        while True:
            started = asyncio.get_running_loop().time()
            try:
                result = await asyncio.wait_for(
                    reconcile_openvpn_quota_runtime_once(), timeout=75.0,
                )
                failed = [
                    (item.get("node_id"), str(item.get("error") or "")[:160])
                    for item in (result.get("nodes") or [])
                    if not item.get("ok")
                ]
                if failed:
                    print("OPENVPN_FAST_PRESENCE_ERRORS", failed, flush=True)
                refreshed = [
                    item for item in (result.get("nodes") or [])
                    if item.get("opened") or item.get("closed")
                ]
                if refreshed:
                    print("OPENVPN_FAST_PRESENCE_CHANGES", refreshed, flush=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(
                    "OPENVPN_FAST_PRESENCE_ERROR",
                    f"{type(exc).__name__}:{str(exc)[:300]}",
                    flush=True,
                )
            elapsed = asyncio.get_running_loop().time() - started
            await asyncio.sleep(max(3.0, 30.0 - elapsed))

    async def _process_isolated_quota_runtime_worker() -> None:
        if os.environ.get("TWINPANEL_EXTERNAL_HEAVY_RECONCILE") == "1":
            await asyncio.Event().wait()
            return
        # This runs in the existing external heavy-reconcile service, not
        # inside API workers. One fast observer serves all user pages.
        asyncio.create_task(
            _fast_cisco_presence_worker(), name="cisco-fast-presence",
        )
        asyncio.create_task(
            _fast_openvpn_presence_worker(), name="openvpn-fast-presence",
        )
        while True:
            cycle_failed = False
            try:
                result = await _run_quota_reconcile_process()
                changed = result.get("changed") or []
                if changed:
                    print(
                        "QUOTA_RUNTIME_RECONCILE",
                        changed,
                        flush=True,
                    )
                for item in result.get("errors") or []:
                    cycle_failed = True
                    print(
                        "quota runtime reconcile failed:",
                        f"collector={item.get('collector') or 'unknown'}",
                        str(item.get("error") or "unknown_error")[:800],
                        flush=True,
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                cycle_failed = True
                print(
                    "quota runtime process reconcile failed:",
                    f"{type(exc).__name__}:{str(exc)[:800]}",
                    flush=True,
                )

            await asyncio.sleep(180.0 if cycle_failed else max(runtime.QUOTA_RUNTIME_INTERVAL_SECONDS, 120.0))

    runtime._quota_runtime_worker = _process_isolated_quota_runtime_worker
    _installed = True
    print(
        f"{MARKER}_ACTIVE scheduling=worker_process nice=10 "
        "quota_semantics=unchanged collectors=cisco-xray,l2tp; fast=cisco,openvpn",
        flush=True,
    )
