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
            if (loop := asyncio.get_event_loop()).is_running():
                return loop.call_soon_threadsafe(super().put, item, block, timeout)

        except RuntimeError:
            pass

        return super().put(item, block, timeout)
