from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import TypeVar


T = TypeVar("T")


def _consume_task_result(task: asyncio.Task[object]) -> None:
    try:
        task.result()
    except BaseException:
        pass


async def await_hard_timeout(
    operation: Awaitable[T],
    *,
    timeout_seconds: float,
    cancel_grace_seconds: float = 2.0,
) -> T:
    """Apply a request deadline without waiting forever for cancellation cleanup.

    ``asyncio.wait_for()`` cancels an overdue task and then waits until that task
    finishes cancellation. A coroutine stuck in an async ``finally`` block can
    therefore make a nominal timeout unbounded. This helper gives cancellation a
    short grace period, then lets cleanup drain in the background while the
    caller receives ``TimeoutError`` and can settle its HTTP request.
    """

    timeout = max(0.01, float(timeout_seconds))
    cancel_grace = max(0.0, float(cancel_grace_seconds))
    task: asyncio.Task[T] = asyncio.create_task(operation)

    done, _ = await asyncio.wait({task}, timeout=timeout)
    if task in done:
        return task.result()

    task.cancel()
    if cancel_grace > 0:
        done, _ = await asyncio.wait({task}, timeout=cancel_grace)
        if task in done:
            try:
                return task.result()
            except asyncio.CancelledError as exc:
                raise asyncio.TimeoutError from exc

    task.add_done_callback(_consume_task_result)
    raise asyncio.TimeoutError
