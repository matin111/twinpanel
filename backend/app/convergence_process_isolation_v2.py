from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any


MARKER = "TWINPANEL_CONVERGENCE_PROCESS_ISOLATION_V2"
RESULT_PREFIX = "TWINPANEL_CONVERGENCE_PROCESS_RESULT_V2="
WORKER = Path(__file__).resolve().parents[1] / "scripts" / "twinpanel_convergence_worker_v2.py"
PROCESS_TIMEOUT_SECONDS = 300
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


async def _run_reconcile_process() -> dict[str, Any]:
    """Execute canonical convergence outside the Uvicorn Python process.

    Thread isolation prevents direct event-loop blocking, but CPU-heavy Python
    loops still contend for the same GIL. A short-lived worker process keeps the
    canonical V114/V299 reconciliation implementation while isolating its GIL,
    CPU scheduling and synchronous DB work from the interactive API process.
    """

    if not WORKER.is_file():
        raise RuntimeError("convergence_worker_missing")

    env = dict(os.environ)
    env["TWINPANEL_CONVERGENCE_WORKER_V2"] = "1"
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
        raise RuntimeError("convergence_worker_timeout") from exc

    output = stdout.decode("utf-8", errors="replace")
    error = stderr.decode("utf-8", errors="replace")
    if process.returncode != 0:
        detail = (error or output)[-1200:].replace("\n", " ")
        raise RuntimeError(f"convergence_worker_failed:{process.returncode}:{detail}")

    payload_line = next(
        (
            line[len(RESULT_PREFIX) :]
            for line in reversed(output.splitlines())
            if line.startswith(RESULT_PREFIX)
        ),
        "",
    )
    if not payload_line:
        raise RuntimeError("convergence_worker_result_missing")
    payload = json.loads(payload_line)
    if not isinstance(payload, dict):
        raise RuntimeError("convergence_worker_result_invalid")
    return payload


def install() -> None:
    """Move historical subscription convergence into a low-priority process.

    Scheduling only changes here. The canonical topology signature, retry
    cadence, provisioning functions, credentials, quota semantics and protocol
    dataplane remain owned by V114/V299.
    """

    global _installed
    if _installed or os.environ.get("TWINPANEL_CONVERGENCE_WORKER_V2") == "1":
        return

    from . import node_subscription_convergence_v114 as runtime

    async def _process_isolated_convergence_loop() -> None:
        await asyncio.sleep(runtime._INITIAL_DELAY_SECONDS)

        while True:
            stage = "topology_signature"
            try:
                signature = await asyncio.to_thread(runtime._topology_signature)
                if signature != runtime._last_topology_signature:
                    stage = "reconcile_process"
                    result = await _run_reconcile_process()
                    changed = [
                        item
                        for item in result.get("nodes", [])
                        if (
                            item.get("membership_added")
                            or item.get("provisioned_pairs")
                            or item.get("skipped_missing_plan")
                            or item.get("failed_count")
                        )
                    ]
                    if changed:
                        print(runtime.DYNAMIC_MARKER, changed, flush=True)
                    if result.get("ok"):
                        stage = "post_reconcile_signature"
                        runtime._last_topology_signature = await asyncio.to_thread(
                            runtime._topology_signature
                        )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(
                    f"{runtime.DYNAMIC_MARKER}_FAILED",
                    f"stage={stage}",
                    f"{type(exc).__name__}:{str(exc)[:500]}",
                    flush=True,
                )

            await asyncio.sleep(runtime._RETRY_INTERVAL_SECONDS)

    runtime._convergence_loop = _process_isolated_convergence_loop
    _installed = True
    print(
        f"{MARKER}_ACTIVE scheduling=worker_process nice=10 "
        "convergence=v114-v299 semantics=unchanged",
        flush=True,
    )
