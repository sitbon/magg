"""Default logging config.

Uses standard Python logging configuration schema.

Intended for apps that don't use Django.

Just sets every logger to use this package's components.
"""
import os


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "()": "magg.logs.formatter.DefaultFormatter",
            "format": "[{asctime}.{msecs:03.0f}] {levelname} {name} {message}",
            "datefmt": "%Y-%m-%d %H:%M:%S",
            "style": "{",
            "defaults": {
                # "foo": "bar",
            },
        },
    },
    "handlers": {
        "stream": {
            "class": "magg.logs.handler.StreamHandler",
            "formatter": "default",
            "stream": "ext://sys.stderr",
        },
        "default": {
            "class": "magg.logs.handler.QueueHandler",
            "queue": "magg.logs.queue.LogQueue",
            "listener": "magg.logs.listener.QueueListener",
            "handlers": ["stream"],
        },
        # "rich": {
        #     "class": "rich.logging.RichHandler",
        #     # "formatter": "default",
        #     "rich_tracebacks": True,
        # }
    },
    "loggers": {
        "root": {
            "handlers": ["default"],
            "level": "WARNING",
            "propagate": False,
        },
        "magg": {
            "handlers": ["default"],
            "level": (os.getenv("MAGG_LOG_LEVEL") or "INFO").upper(),
            "propagate": False,
        },
        "FastMCP": {
            "handlers": ["default"],
            "level": (os.getenv("FASTMCP_LOG_LEVEL") or "WARNING").upper(),
            "propagate": False,
        },
        "uvicorn": {
            "handlers": ["default"],
            "level": "WARNING",
            "propagate": False,
        },
        "uvicorn.access": {
            "handlers": ["default"],
            "level": "WARNING",
            "propagate": False,
        },
        "uvicorn.error": {
            "handlers": ["default"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}
