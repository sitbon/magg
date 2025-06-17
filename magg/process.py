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
    config = config_manager.load_config()

    environment.setdefault("MAGG_CONFIG_PATH", str(config_manager.config_path))
    environment.setdefault("MAGG_LOG_LEVEL", config.log_level.upper())

    for key, value in environment.items():
        os.environ.setdefault(key, value)

    if not os.environ.get("NO_TERM", False):
        from .utils.system import initterm
        initterm()

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
