import atexit
import logging.handlers
import weakref

from .queue import LogQueue

__all__ = "QueueListener",


class QueueListener(logging.handlers.QueueListener):
    """Queue listener.

    Support self-starting and stopping, and sets respect_handler_level to True by default.
    """
    __listeners = []

    def __init__(self, queue: LogQueue, *handlers: logging.Handler, respect_handler_level=True, start=False):
        super().__init__(queue, *handlers, respect_handler_level=respect_handler_level)

        type(self).__listeners.append(weakref.proxy(self, type(self).__listeners.remove))

        if start:
            self.start()

    def __bool__(self):
        return self._thread is not None

    def __del__(self):
        self.stop()

    def start(self):
        if not self:
            super().start()
            atexit.register(self.stop)

    def stop(self):
        if self:
            super().stop()
            atexit.unregister(self.stop)

    @classmethod
    def start_all(cls):
        """Start all listeners.

        NOTE: When using the logs.handler.QueueHandler handler,
              this method is called automatically upon emitting a log record.
        """
        for listener in cls.__listeners:
            listener.start()

    @classmethod
    def stop_all(cls):
        """Stop all listeners.

        NOTE: Each listener stops itself on deletion or program exit, so calling this method is optional.
        """
        for listener in cls.__listeners:
            listener.stop()
