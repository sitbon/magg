import logging
from . import config, adapter


def initialize_logging(*, configure_logging: bool = True, start_listeners: bool = True) -> None:
    """Initialize logging queues and listeners.

    Typically called once on application startup, after logging has been configured.
    """
    if configure_logging:
        config.configure_logging()

    if start_listeners:
        from .listener import QueueListener
        QueueListener.start_all()


def adapt_logger(logger, extra) -> adapter.LoggerAdapter:
    """
    Adapt a logger object by attaching additional contextual information
    provided via the `extras` parameter. This function ensures a consistent
    logging format enriched with dynamic data, improving the clarity and
    traceability of log messages.

    :param logger: A logging.Logger instance to adapt or None. If None,
        a default logger is utilized.
    :param extra: A dictionary containing additional contextual
        information to be included in the logs.
    :return: A LoggerAdapter instance that wraps the provided logger
        and enriches its output with the given extras.
    :rtype: adapter.LoggerAdapter
    """
    if logger is None:
        logger = get_logger()

    return adapter.LoggerAdapter(logger, extra)


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a logger by name.

    Args:
        name (str | None): The name of the logger. If None, the root logger is returned.

    Returns:
        logging.Logger: The logger instance.
    """
    return logging.getLogger(name)
