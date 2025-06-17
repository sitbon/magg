import logging

__all__ = "LoggerAdapter",


class LoggerAdapter(logging.LoggerAdapter):
    """Default logger adapter.

    Just a thin wrapper around the standard library's LoggerAdapter.

    Its main purpose is to set Python 3.13's new merge_extra to True by default.
    """

    def __init__(self, logger, extra=None, merge_extra=True):
        super().__init__(logger, extra, merge_extra)

    def process(self, msg, kwds):
        return super().process(msg, kwds)
