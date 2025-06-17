"""Logging configuration.
"""
from logging import config as logging_config

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
