"""Logging queue handler.
"""
import logging.handlers
from queue import Queue

__all__ = "QueueHandler", "StreamHandler",


class QueueHandler(logging.handlers.QueueHandler):
    """Queue handler.

    Just a thin wrapper around the standard library's QueueHandler that
    starts the listener if it isn't already running.
    """
    listener: logging.handlers.QueueListener | None

    def __init__(self, queue):
        super().__init__(queue)

    def emit(self, record):
        if not bool(self.listener) and isinstance(self.queue, Queue):
            self.listener.start()
        super().emit(record)


class StreamHandler(logging.StreamHandler):
    """Stream handler.

    Just a thin wrapper around the standard library's StreamHandler.

    Used to have a consistent import path for all handlers.
    """

    def __init__(self, stream=None):
        super().__init__(stream)
