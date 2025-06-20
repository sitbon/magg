import os

__all__ = "initialize", "is_initialized", "setup",

_initialized = False


def initialize(**environment) -> bool:
    """Process-level initialization.
    """
    global _initialized

    if _initialized:
        return False

    _initialized = True

    from .settings import ConfigManager
    config_manager = ConfigManager()

    for key, value in environment.items():
        os.environ.setdefault(key, value)

    if not os.environ.get("NO_TERM", False):
        from .util.system import initterm
        initterm()

    config_manager.load_config()
    return True


def is_initialized() -> bool:
    """Check if the process has been initialized."""
    return _initialized


def setup(source: str | None = __name__, **environment) -> None:
    """Setup the package environment.

    Initialize the process and setup config-dependent features such as logging.
    """
    first = initialize(**environment)

    if first:
        from .logs import initialize_logging, get_logger
        initialize_logging()
        logger = get_logger(__name__)
        logger.debug("Process initialized by %r", source)
