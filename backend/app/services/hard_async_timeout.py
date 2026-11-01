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
    wait_for_cancel: bool = False,
) -> T:
    """Apply a request deadline with an optional cancellation drain.

    The default preserves the original hard-deadline behaviour: an overdue task
    is cancelled, given a short grace period, and then allowed to finish cleanup
    in the background.

    ``wait_for_cancel=True`` is required for operations that retain request-local
    resources such as a SQLAlchemy Session or ORM instances. In that mode this
    helper never returns while the cancelled task can still touch those objects,
    preventing background work from racing a caller rollback/close.
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

    if wait_for_cancel:
        try:
            await task
        except asyncio.CancelledError as exc:
            raise asyncio.TimeoutError from exc
        except BaseException:
            raise
        raise asyncio.TimeoutError

    task.add_done_callback(_consume_task_result)
    raise asyncio.TimeoutError