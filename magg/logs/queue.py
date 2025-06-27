"""Async-capable logging queue.

TODO: Make use of asyncio.Queue dynamically?
"""
import asyncio
import queue

__all__ = "LogQueue",


class LogQueue(queue.Queue):
    """Queue for logging messages.
    """
    def __init__(self):
        super().__init__(maxsize=0)

    def put(self, item, block=True, timeout=None) -> asyncio.Handle | None:
        try:
            # Use get_running_loop() to avoid deprecation warning
            loop = asyncio.get_running_loop()
            return loop.call_soon_threadsafe(super().put, item, block, timeout)
        except RuntimeError:
            # No running event loop, use synchronous put
            pass

        return super().put(item, block, timeout)
