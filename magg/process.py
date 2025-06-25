import logging
import os

__all__ = "initialize_process", "is_initialized", "setup",

_initialized = False


def initialize_process(**environment) -> bool:
    """Process-level initialization.
    """
    global _initialized

    if _initialized:
        return False

    _initialized = True

    for key, value in environment.items():
        os.environ.setdefault(key, value)

    if not os.environ.get("NO_TERM", False):
        from .util.system import initterm
        initterm()

    return True


def is_initialized() -> bool:
    """Check if the process has been initialized."""
    return _initialized


def setup(source: str | None = __name__, **environment) -> None:
    """Application initialization

     Sets up the package environment, logging, and configuration in proper order.
    """
    first = initialize_process(**environment)

    if first:
        from .logs import initialize_logging
        initialize_logging()

        logger = logging.getLogger(__name__)
        logger.debug("Process initialized by %r", source)

        from .settings import ConfigManager
        config_manager = ConfigManager()

        if not config_manager.config_path.exists():
            logger.warning(f"Config file {config_manager.config_path} does not exist. Using default settings.")

        config_manager.load_config()
