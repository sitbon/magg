"""Logging configuration.
"""
import logging
from logging import Logger, config as logging_config
from typing import Literal

from fastmcp.utilities import logging as fastmcp_logging

from .defaults import LOGGING_CONFIG

__all__ = "configure_logging", "LOGGING_CONFIG",


def configure_logging(config=None, *, incremental=False) -> None:
    """Configure logging.

    Args:
        config (dict): Logging configuration dictionary.
            If None, the default configuration will be used.

        incremental (bool): Whether to apply the configuration incrementally.

    Returns:
        None
    """
    if config is None:
        config = LOGGING_CONFIG.copy()

    if incremental:
        config["incremental"] = True

    logging_config.dictConfig(config)


def configure_logging_fastmcp(
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] | int = "INFO",
    logger: Logger | None = None,
    enable_rich_tracebacks: bool = True,
) -> None:
    """Patched configuration for FastMCP logging."""
    # from rich.logging import RichHandler
    # from rich.console import Console
    # rich_handler: RichHandler | None = logging.getHandlerByName("rich")
    # if rich_handler:
    #     rich_handler.console = Console(stderr=True)


fastmcp_logging.configure_logging = configure_logging_fastmcp
