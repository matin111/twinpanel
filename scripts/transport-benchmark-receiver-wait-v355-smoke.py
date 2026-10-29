#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("APP_SECRET_KEY", "v355-smoke-secret-key-000000000000")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://twinpanel:twinpanel@127.0.0.1:5432/twinpanel",
)
os.environ.setdefault(
    "NODE_AGENT_SHARED_SECRET",
    "v355-smoke-node-agent-secret-000000000000",
)
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6379/0")

from app import smart_transport_auto_v21 as smart  # noqa: E402
from app import transport_benchmark_receiver_wait_v355 as v355  # noqa: E402


class Result:
    def __init__(self, stdout: str = "", stderr: str = "", exit_status: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_status = exit_status


async def delayed_result_case() -> None:
    calls: list[str] = []
    polls = 0

    async def fake_run(conn, command: str, timeout: int = 12):
        nonlocal polls
        calls.append(command)
        if command.startswith("cat "):
            polls += 1
            if polls < 4:
                return Result("READY\n")
            return Result("READY\nRX_BYTES=6983636\nRX_MBPS=14.010\n")
        return Result()

    async def fake_wait_ready(conn, logfile: str) -> bool:
        return True

    old_run = smart._run
    old_wait_ready = smart._wait_ready
    old_poll = v355.RESULT_POLL_INTERVAL_SECONDS
    old_wait = v355.RESULT_WAIT_SECONDS
    try:
        smart._run = fake_run
        smart._wait_ready = fake_wait_ready
        v355.RESULT_POLL_INTERVAL_SECONDS = 0.01
        v355.RESULT_WAIT_SECONDS = 0.20

        value = await v355._one_direction_v355(
            object(),
            object(),
            src="10.250.0.33",
            dst="10.250.0.34",
            port=42918,
            label="upload",
        )
        assert abs(value - 14.010) < 0.0001, value
        assert polls == 4, polls
        assert any(command.startswith("rm -f ") for command in calls), calls
    finally:
        smart._run = old_run
        smart._wait_ready = old_wait_ready
        v355.RESULT_POLL_INTERVAL_SECONDS = old_poll
        v355.RESULT_WAIT_SECONDS = old_wait


async def bounded_timeout_case() -> None:
    cleanup_calls = 0

    async def fake_run(conn, command: str, timeout: int = 12):
        nonlocal cleanup_calls
        if command.startswith("rm -f "):
            cleanup_calls += 1
        if command.startswith("cat "):
            return Result("READY\n")
        return Result()

    async def fake_wait_ready(conn, logfile: str) -> bool:
        return True

    old_run = smart._run
    old_wait_ready = smart._wait_ready
    old_poll = v355.RESULT_POLL_INTERVAL_SECONDS
    old_wait = v355.RESULT_WAIT_SECONDS
    try:
        smart._run = fake_run
        smart._wait_ready = fake_wait_ready
        v355.RESULT_POLL_INTERVAL_SECONDS = 0.005
        v355.RESULT_WAIT_SECONDS = 0.02

        try:
            await v355._one_direction_v355(
                object(),
                object(),
                src="10.250.0.33",
                dst="10.250.0.34",
                port=42918,
                label="upload",
            )
        except RuntimeError as exc:
            assert str(exc).startswith(
                "throughput_receiver_result_missing:upload"
            ), str(exc)
        else:
            raise AssertionError("expected bounded missing-result failure")

        assert cleanup_calls >= 2, cleanup_calls
    finally:
        smart._run = old_run
        smart._wait_ready = old_wait_ready
        v355.RESULT_POLL_INTERVAL_SECONDS = old_poll
        v355.RESULT_WAIT_SECONDS = old_wait


async def main() -> None:
    await delayed_result_case()
    await bounded_timeout_case()

    source = (ROOT / "backend/app/transport_benchmark_receiver_wait_v355.py").read_text(
        encoding="utf-8"
    )
    assert "RESULT_WAIT_SECONDS = 3.0" in source
    assert "RESULT_POLL_INTERVAL_SECONDS = 0.25" in source
    assert "route" not in source.lower().split("def apply_transport_benchmark_receiver_wait_v355", 1)[1]

    manual = (ROOT / "backend/app/manual_transport_benchmark_v351.py").read_text(
        encoding="utf-8"
    )
    manager = (ROOT / "backend/app/tunnel_transport_manager_v12.py").read_text(
        encoding="utf-8"
    )
    assert "apply_transport_benchmark_receiver_wait_v355()" in manual
    assert "apply_transport_benchmark_receiver_wait_v355()" in manager

    print("TRANSPORT_BENCHMARK_RECEIVER_WAIT_V355_SMOKE_OK")


if __name__ == "__main__":
    asyncio.run(main())
