from __future__ import annotations

import asyncio
import os
from typing import Any

import asyncssh


# AsyncSSH connection.close() is synchronous, but wait_closed() can remain
# pending while the transport finishes teardown. Provisioning uses per-protocol
# asyncio.wait_for() deadlines; an unbounded wait_closed() in a driver's finally
# block can otherwise keep cancellation pending beyond those deadlines.
DEFAULT_SSH_CLOSE_TIMEOUT_SECONDS = 2.0
_MIN_SSH_CLOSE_TIMEOUT_SECONDS = 0.25
_MAX_SSH_CLOSE_TIMEOUT_SECONDS = 10.0
_PATCH_MARKER = "_twinpanel_bounded_wait_closed_v1"


def _configured_timeout() -> float:
    raw = os.getenv(
        "TWINPANEL_SSH_CLOSE_TIMEOUT_SECONDS",
        str(DEFAULT_SSH_CLOSE_TIMEOUT_SECONDS),
    )
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = DEFAULT_SSH_CLOSE_TIMEOUT_SECONDS
    return max(_MIN_SSH_CLOSE_TIMEOUT_SECONDS, min(value, _MAX_SSH_CLOSE_TIMEOUT_SECONDS))


def _consume_background_result(task: asyncio.Task[Any]) -> None:
    try:
        task.result()
    except BaseException:
        # The connection has already been told to close. Once the bounded wait
        # expires, teardown may finish later or be cancelled at loop shutdown;
        # neither outcome should resurrect a completed provisioning request.
        pass


def install_asyncssh_close_guard(
    connection_cls: type[Any] | None = None,
    *,
    timeout_seconds: float | None = None,
) -> bool:
    """Bound SSH wait_closed() without cancelling connection teardown.

    Returns True when the class was patched and False when the same guard was
    already installed. The wrapper intentionally lets the original close wait
    continue in the background after the bounded deadline because close() has
    already started and there must be no further remote mutation at this stage.
    """

    cls = connection_cls or asyncssh.SSHClientConnection
    if bool(getattr(cls, _PATCH_MARKER, False)):
        return False

    original_wait_closed = getattr(cls, "wait_closed")
    timeout = (
        _configured_timeout()
        if timeout_seconds is None
        else max(
            _MIN_SSH_CLOSE_TIMEOUT_SECONDS,
            min(float(timeout_seconds), _MAX_SSH_CLOSE_TIMEOUT_SECONDS),
        )
    )

    async def bounded_wait_closed(self: Any) -> Any:
        task = asyncio.create_task(original_wait_closed(self))
        done, _ = await asyncio.wait({task}, timeout=timeout)
        if task in done:
            return task.result()

        # Do not cancel the underlying connection teardown. Returning here makes
        # protocol cancellation/timeout deterministic while SSH cleanup keeps
        # draining independently.
        task.add_done_callback(_consume_background_result)
        return None

    setattr(cls, "wait_closed", bounded_wait_closed)
    setattr(cls, _PATCH_MARKER, True)
    return True
