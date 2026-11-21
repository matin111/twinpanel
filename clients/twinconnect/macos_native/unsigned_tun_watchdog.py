#!/usr/bin/env python3
"""Independent fail-safe for the experimental TwinConnect sing-box TUN.

Runs root-owned with no network listeners. Watches the daemon's lifetime and
stops the dedicated sing-box process group on parent disappearance or TTL.
Does not install routes or assert that an inaccessible Mac can be recovered.
"""
from __future__ import annotations
import argparse
import os
import select
import signal
import sys
import time

MAX_SECONDS = 600


def valid_pid(value: int) -> bool:
    return isinstance(value, int) and 1 < value < 2**22


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def terminate_group(pid: int) -> None:
    # The engine is started in its own session and is its group leader.
    # Never signal unrelated processes when its PID/group no longer match.
    try:
        if os.getpgid(pid) != pid:
            return
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return


def watch(parent: int, engine: int, lifetime: int) -> None:
    if not valid_pid(parent) or not valid_pid(engine) or parent == engine:
        raise ValueError("INVALID_PID")
    if not 1 <= lifetime <= MAX_SECONDS:
        raise ValueError("INVALID_WATCHDOG_DURATION")
    if os.geteuid() != 0 or sys.platform != "darwin":
        raise ValueError("LOCAL_ROOT_MAC_REQUIRED")
    if os.getppid() != parent or os.getpgid(engine) != engine:
        raise ValueError("WATCHDOG_NOT_CHILD_OF_DAEMON")

    # Darwin kqueue delivers NOTE_EXIT for the watched daemon, avoiding
    # a kill(pid,0) PID-reuse race. Check deadline independently.
    queue = select.kqueue()
    try:
        event = select.kevent(parent, filter=select.KQ_FILTER_PROC,
                              flags=select.KQ_EV_ADD | select.KQ_EV_ENABLE,
                              fflags=select.KQ_NOTE_EXIT)
        queue.control([event], 0, 0)
        print("WATCHDOG_READY", flush=True)
        deadline = time.monotonic() + lifetime
        while process_alive(engine):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if queue.control(None, 1, min(remaining, 1.0)):
                break
    finally:
        queue.close()
        terminate_group(engine)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parent", type=int, required=True)
    parser.add_argument("--engine", type=int, required=True)
    parser.add_argument("--seconds", type=int, default=MAX_SECONDS)
    args = parser.parse_args()
    try:
        watch(args.parent, args.engine, args.seconds)
    except (ValueError, OSError):
        # Watchdog failure is fatal for the invoking daemon's start path.
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
