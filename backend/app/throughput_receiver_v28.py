from __future__ import annotations

import asyncio
import math
import re
import shlex

from . import throughput_auto_v27 as v27


# ============================================================
# TWINPANEL THROUGHPUT RECEIVER COMPLETION V28
#
# V27 launched the remote receiver correctly and waited for READY, but after
# the sender returned it slept a fixed 0.5 seconds, read the logfile once, and
# immediately removed it. On real WAN paths the receiver can still be draining
# queued TCP data / observing FIN at that point. Production therefore produced
# throughput_receiver_result_missing even though the sender completed.
#
# V28 changes only result collection:
#   * keep the receiver/log ownership used by V27
#   * poll the receiver logfile until RX_MBPS appears or a bounded deadline
#   * never treat a normal sub-second completion race as a failed benchmark
#   * preserve V27 byte/time caps, cache format, schedule and scoring
#   * no route/firewall/service/schema changes
# ============================================================


RECEIVER_RESULT_WAIT_SECONDS = 8.5
RECEIVER_RESULT_POLL_SECONDS = 0.1
RECEIVER_OUTER_TIMEOUT_SECONDS = 10

_RX_RE = re.compile(
    r"^RX_MBPS=([0-9]+(?:\.[0-9]+)?)$",
    flags=re.MULTILINE,
)


def receiver_mbps_from_text(text: str) -> float | None:
    match = _RX_RE.search(str(text or ""))
    if not match:
        return None

    try:
        value = float(match.group(1))
    except (TypeError, ValueError):
        return None

    if not math.isfinite(value) or value <= 0:
        return None

    return value


async def _wait_receiver_result(
    conn,
    logfile: str,
    *,
    runner=None,
    wait_seconds: float = RECEIVER_RESULT_WAIT_SECONDS,
    poll_seconds: float = RECEIVER_RESULT_POLL_SECONDS,
) -> tuple[float | None, str]:
    run = runner or v27._run
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max(0.1, float(wait_seconds))
    last_text = ""

    while loop.time() < deadline:
        result = await run(
            conn,
            "cat " + shlex.quote(logfile) + " 2>/dev/null || true",
            4,
        )

        last_text = (
            (getattr(result, "stdout", "") or "")
            + "\n"
            + (getattr(result, "stderr", "") or "")
        ).strip()

        value = receiver_mbps_from_text(last_text)
        if value is not None:
            return value, last_text

        await asyncio.sleep(max(0.02, float(poll_seconds)))

    return None, last_text


def _compact_log(text: str, limit: int = 700) -> str:
    value = " ".join(str(text or "").split())
    if not value:
        return "empty"
    return value[-int(limit):]


async def one_direction_v28(
    sender,
    receiver,
    *,
    src: str,
    dst: str,
    port: int,
    label: str,
) -> float:
    logfile = f"/tmp/twinpanel-v28-{port}-{label}.log"

    await v27._run(
        receiver,
        "rm -f " + shlex.quote(logfile) + " || true",
        4,
    )

    receiver_cmd = (
        "nohup timeout "
        + str(int(RECEIVER_OUTER_TIMEOUT_SECONDS))
        + "s python3 -u -c "
        + shlex.quote(v27.RECEIVER_CODE)
        + " "
        + shlex.quote(dst)
        + " "
        + str(int(port))
        + " >"
        + shlex.quote(logfile)
        + " 2>&1 </dev/null &\ntrue"
    )

    await v27._run(
        receiver,
        receiver_cmd,
        5,
    )

    if not await v27._wait_ready(receiver, logfile):
        diagnostic = await v27._run(
            receiver,
            "cat " + shlex.quote(logfile) + " 2>/dev/null || true",
            4,
        )
        await v27._run(
            receiver,
            "rm -f " + shlex.quote(logfile) + " || true",
            4,
        )
        raise RuntimeError(
            "throughput_receiver_not_ready:"
            + label
            + ":log="
            + _compact_log(
                (diagnostic.stdout or "") + "\n" + (diagnostic.stderr or "")
            )
        )

    sender_cmd = (
        "timeout 6s python3 -u -c "
        + shlex.quote(v27.SENDER_CODE)
        + " "
        + shlex.quote(src)
        + " "
        + shlex.quote(dst)
        + " "
        + str(int(port))
        + " "
        + str(float(v27.BENCHMARK_SECONDS))
        + " "
        + str(int(v27.BENCHMARK_MAX_BYTES))
    )

    tx = await v27._run(
        sender,
        sender_cmd,
        8,
    )

    if tx.exit_status != 0:
        diagnostic = await v27._run(
            receiver,
            "cat " + shlex.quote(logfile) + " 2>/dev/null || true",
            4,
        )
        await v27._run(
            receiver,
            "rm -f " + shlex.quote(logfile) + " || true",
            4,
        )
        raise RuntimeError(
            "throughput_sender_failed:"
            + label
            + ":rx_log="
            + _compact_log(
                (diagnostic.stdout or "") + "\n" + (diagnostic.stderr or "")
            )
        )

    value, receiver_text = await _wait_receiver_result(
        receiver,
        logfile,
    )

    await v27._run(
        receiver,
        "rm -f " + shlex.quote(logfile) + " || true",
        4,
    )

    if value is None:
        raise RuntimeError(
            "throughput_receiver_result_timeout:"
            + label
            + ":log="
            + _compact_log(receiver_text)
        )

    return float(value)


def install_throughput_receiver_v28() -> None:
    # _benchmark_candidate in V27 resolves _one_direction from the V27 module's
    # globals at call time, so replacing this one function upgrades the live
    # benchmark lifecycle without duplicating scheduling/scoring logic.
    v27._one_direction = one_direction_v28

    print(
        "TWINPANEL_THROUGHPUT_RECEIVER_V28_ACTIVE "
        f"result_wait={RECEIVER_RESULT_WAIT_SECONDS:.1f}s "
        f"poll={RECEIVER_RESULT_POLL_SECONDS:.1f}s "
        "fixed_sleep_removed=1 delayed_fin_safe=1",
        flush=True,
    )
