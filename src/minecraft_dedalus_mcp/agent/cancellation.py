"""Cooperative cancellation token for agent tasks.

Wraps ``asyncio.Event`` with helpers that race any awaitable against the
cancel signal, so long-running LLM calls and tool executions can be
interrupted promptly.
"""

from __future__ import annotations

import asyncio
from typing import TypeVar

T = TypeVar("T")


class AgentCancelled(Exception):
    """Raised when an agent run is cancelled via its CancellationToken."""


class CancellationToken:
    """Thread/task-safe cancellation primitive.

    Usage::

        token = CancellationToken()

        # In the worker:
        result = await token.wrap(slow_coro())

        # From the controller:
        token.cancel()
    """

    def __init__(self) -> None:
        self._event = asyncio.Event()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def reset(self) -> None:
        self._event = asyncio.Event()

    def check(self) -> None:
        """Raise ``AgentCancelled`` if already cancelled."""
        if self._event.is_set():
            raise AgentCancelled("Agent run cancelled")

    async def wrap(self, coro: asyncio.Future[T] | asyncio.Task[T], *, timeout: float | None = None) -> T:
        """Race *coro* against the cancellation signal.

        If the token fires first, *coro* is cancelled and ``AgentCancelled``
        is raised.  An optional *timeout* (seconds) is also enforced — if the
        coro exceeds it, ``asyncio.TimeoutError`` propagates.
        """
        cancel_waiter = asyncio.ensure_future(self._event.wait())
        work = asyncio.ensure_future(coro)

        tasks: list[asyncio.Future] = [work, cancel_waiter]
        try:
            done, _ = await asyncio.wait(
                tasks,
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
        except asyncio.CancelledError:
            work.cancel()
            cancel_waiter.cancel()
            raise

        if not done:
            work.cancel()
            cancel_waiter.cancel()
            raise asyncio.TimeoutError(f"Timed out after {timeout}s")

        if cancel_waiter in done:
            try:
                await asyncio.wait_for(asyncio.shield(work), timeout=0.5)
            except (asyncio.TimeoutError, asyncio.CancelledError, Exception):
                work.cancel()
                try:
                    await work
                except (asyncio.CancelledError, Exception):
                    pass
            raise AgentCancelled("Agent run cancelled")

        cancel_waiter.cancel()
        return work.result()

    async def sleep(self, seconds: float) -> None:
        """Cancellation-aware sleep."""
        waiter = asyncio.ensure_future(self._event.wait())
        try:
            done, _ = await asyncio.wait(
                [asyncio.ensure_future(asyncio.sleep(seconds)), waiter],
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            waiter.cancel()

        if self._event.is_set():
            raise AgentCancelled("Agent run cancelled during sleep")
