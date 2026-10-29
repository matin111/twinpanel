#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "backend" / "app"
PATCH_PATH = APP_DIR / "transport_benchmark_receiver_wait_v355.py"


class Result:
    def __init__(self, stdout: str = "", stderr: str = "", exit_status: int = 0):
        self.stdout = stdout
        self.stderr = stderr
        self.exit_status = exit_status


# Load V355 against a deliberately tiny fake SmartAuto module. The regression
# test exercises only the benchmark result-collection contract and therefore
# does not need SQLAlchemy, PostgreSQL, Redis or SSH dependencies.
app_pkg = types.ModuleType("app")
app_pkg.__path__ = [str(APP_DIR)]
sys.modules["app"] = app_pkg

smart = types.ModuleType("app.smart_transport_auto_v21")
smart.BENCHMARK_STREAMS = 4
smart.BENCHMARK_SECONDS = 3.0
smart.BENCHMARK_MAX_BYTES = 64 * 1024 * 1024


async def placeholder_run(conn, command: str, timeout: int = 12):
    return Result()


async def placeholder_wait_ready(conn, logfile: str) -> bool:
    return True


async def placeholder_one_direction(*args, **kwargs):
    return 1.0


smart._run = placeholder_run
smart._wait_ready = placeholder_wait_ready
smart._one_direction = placeholder_one_direction
smart.RECEIVER_CODE = "print('READY', flush=True)"
smart.SENDER_CODE = "print('TX_MBPS=1.0', flush=True)"
sys.modules["app.smart_transport_auto_v21"] = smart
setattr(app_pkg, "smart_transport_auto_v21", smart)

spec = importlib.util.spec_from_file_location(
    "app.transport_benchmark_receiver_wait_v355",
    PATCH_PATH,
)
assert spec is not None and spec.loader is not None
v355 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = v355
spec.loader.exec_module(v355)


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
        assert sum(command.startswith("rm -f ") for command in calls) >= 2, calls
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


async def patch_activation_case() -> None:
    original = smart._one_direction
    v355._applied = False
    v355._original_one_direction = None
    v355.apply_transport_benchmark_receiver_wait_v355()
    assert smart._one_direction is v355._one_direction_v355
    assert v355._original_one_direction is original


async def main() -> None:
    await delayed_result_case()
    await bounded_timeout_case()
    await patch_activation_case()

    source = PATCH_PATH.read_text(encoding="utf-8")
    assert "RESULT_WAIT_SECONDS = 3.0" in source
    assert "RESULT_POLL_INTERVAL_SECONDS = 0.25" in source
    assert "systemctl" not in source
    assert "iptables" not in source
    assert "nft " not in source
    assert "ip route" not in source
    assert "wg set" not in source

    manual = (APP_DIR / "manual_transport_benchmark_v351.py").read_text(
        encoding="utf-8"
    )
    manager = (APP_DIR / "tunnel_transport_manager_v12.py").read_text(
        encoding="utf-8"
    )
    assert "apply_transport_benchmark_receiver_wait_v355()" in manual
    assert "apply_transport_benchmark_receiver_wait_v355()" in manager

    print("TRANSPORT_BENCHMARK_RECEIVER_WAIT_V355_SMOKE_OK")


if __name__ == "__main__":
    asyncio.run(main())
