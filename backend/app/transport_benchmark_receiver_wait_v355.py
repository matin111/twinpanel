from __future__ import annotations

import asyncio
import math
import re
import shlex

from . import smart_transport_auto_v21 as smart


MARKER = "TWINPANEL_TRANSPORT_BENCHMARK_RECEIVER_WAIT_V355"
RESULT_WAIT_SECONDS = 3.0
RESULT_POLL_INTERVAL_SECONDS = 0.25

_applied = False
_original_one_direction = None


async def _one_direction_v355(
    sender,
    receiver,
    *,
    src: str,
    dst: str,
    port: int,
    label: str,
) -> float:
    """Run the existing bounded benchmark and wait for receiver finalization.

    Production Tunnel #8 proved that a healthy Spoof WG upload can finish on the
    sender while the receiver needs about one additional second to join its
    worker threads and flush RX_MBPS. V21 read and removed the receiver log after
    a fixed 0.5 second sleep, producing a false
    throughput_receiver_result_missing error.

    V355 changes only result collection. Sender/receiver programs, byte limits,
    duration, stream count, transport routing, candidate health and production
    authority remain unchanged.
    """

    logfile = f"/tmp/twinpanel-smart-v21-{int(port)}-{label}.log"

    await smart._run(
        receiver,
        "rm -f " + shlex.quote(logfile) + " || true",
        4,
    )

    receiver_cmd = (
        "nohup timeout 15s python3 -u -c "
        + shlex.quote(smart.RECEIVER_CODE)
        + " "
        + shlex.quote(dst)
        + " "
        + str(int(port))
        + " "
        + str(int(smart.BENCHMARK_STREAMS))
        + " >"
        + shlex.quote(logfile)
        + " 2>&1 </dev/null &\ntrue"
    )
    await smart._run(receiver, receiver_cmd, 5)

    if not await smart._wait_ready(receiver, logfile):
        raise RuntimeError("throughput_receiver_not_ready:" + label)

    sender_cmd = (
        "timeout 12s python3 -u -c "
        + shlex.quote(smart.SENDER_CODE)
        + " "
        + shlex.quote(src)
        + " "
        + shlex.quote(dst)
        + " "
        + str(int(port))
        + " "
        + str(float(smart.BENCHMARK_SECONDS))
        + " "
        + str(int(smart.BENCHMARK_MAX_BYTES))
        + " "
        + str(int(smart.BENCHMARK_STREAMS))
    )

    tx = await smart._run(sender, sender_cmd, 14)
    if tx.exit_status != 0:
        raise RuntimeError(
            "throughput_sender_failed:"
            + label
            + ":"
            + ((tx.stderr or tx.stdout or "")[-600:])
        )

    loop = asyncio.get_running_loop()
    deadline = loop.time() + RESULT_WAIT_SECONDS
    rx_text = ""

    try:
        while True:
            rx = await smart._run(
                receiver,
                "cat " + shlex.quote(logfile) + " 2>/dev/null || true",
                5,
            )
            rx_text = rx.stdout or ""

            match = re.search(
                r"^RX_MBPS=([0-9]+(?:\.[0-9]+)?)$",
                rx_text,
                flags=re.MULTILINE,
            )
            if match:
                value = float(match.group(1))
                if not math.isfinite(value) or value <= 0:
                    raise RuntimeError(
                        "throughput_receiver_result_invalid:" + label
                    )
                return value

            if loop.time() >= deadline:
                tail = rx_text[-600:].replace("\n", " ").strip()
                detail = (":" + tail) if tail else ""
                raise RuntimeError(
                    "throughput_receiver_result_missing:"
                    + label
                    + detail
                )

            await asyncio.sleep(RESULT_POLL_INTERVAL_SECONDS)
    finally:
        await smart._run(
            receiver,
            "rm -f " + shlex.quote(logfile) + " || true",
            4,
        )


def apply_transport_benchmark_receiver_wait_v355() -> None:
    global _applied
    global _original_one_direction

    if _applied:
        return

    current = getattr(smart, "_one_direction", None)
    if not callable(current):
        raise RuntimeError("smart_transport_one_direction_missing_v355")

    _original_one_direction = current
    smart._one_direction = _one_direction_v355
    _applied = True

    print(
        f"{MARKER}_ACTIVE "
        f"result_wait_seconds={RESULT_WAIT_SECONDS:g} "
        f"poll_seconds={RESULT_POLL_INTERVAL_SECONDS:g} "
        "measurement=v21-unchanged authority=unchanged dataplane=unchanged",
        flush=True,
    )
