from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app import throughput_auto_v27 as v27
from app.throughput_receiver_v28 import (
    _wait_receiver_result,
    install_throughput_receiver_v28,
    one_direction_v28,
    receiver_mbps_from_text,
)


async def delayed_result_smoke() -> tuple[float, int]:
    calls = 0

    async def fake_runner(_conn, _command, _timeout):
        nonlocal calls
        calls += 1

        if calls == 1:
            text = "READY\n"
        elif calls == 2:
            text = "READY\nRX_BYTES=524288\n"
        elif calls == 3:
            text = "READY\nRX_BYTES=524288\nRX_SECONDS=1.000000\n"
        else:
            text = (
                "READY\n"
                "RX_BYTES=524288\n"
                "RX_SECONDS=1.000000\n"
                "RX_MBPS=4.194\n"
            )

        return SimpleNamespace(
            stdout=text,
            stderr="",
            exit_status=0,
        )

    value, text = await _wait_receiver_result(
        object(),
        "/tmp/fake-v28.log",
        runner=fake_runner,
        wait_seconds=1.0,
        poll_seconds=0.01,
    )

    assert value == 4.194, (value, text)
    assert calls >= 4, calls
    assert "RX_MBPS=4.194" in text, text

    return value, calls


def main() -> None:
    assert receiver_mbps_from_text("RX_MBPS=1.250\n") == 1.25
    assert receiver_mbps_from_text("READY\nRX_BYTES=10\n") is None
    assert receiver_mbps_from_text("RX_MBPS=0.000\n") is None

    value, calls = asyncio.run(
        delayed_result_smoke()
    )

    install_throughput_receiver_v28()
    assert v27._one_direction is one_direction_v28

    print(
        "THROUGHPUT_RECEIVER_V28_SMOKE_OK "
        f"delayed_polls={calls} "
        f"result_mbps={value:.3f} "
        "runtime_hook=1"
    )


if __name__ == "__main__":
    main()
