"""Logging formatter module.

Defines a default formatter for log messages.
"""
import logging

__all__ = "DefaultFormatter",


class DefaultFormatter(logging.Formatter):
    """Default log formatter.

    Uses `{}`-style formatting.
    """
    def __init__(self, fmt=None, datefmt=None, style="{", **kwds):
        super().__init__(fmt=fmt, datefmt=datefmt, style=style, **kwds)
