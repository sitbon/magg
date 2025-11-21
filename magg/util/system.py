"""System utilities for Magg - terminal initialization, paths, and environment handling."""
import os
import re
import sys
from pathlib import Path
from typing import Optional

try:
    from rich import console, pretty, traceback

    _rc: console.Console | None = None

except (ImportError, ModuleNotFoundError):
    pass

__all__ = (
    "initterm",
    "is_subdirectory",
    "get_project_root",
    "get_subprocess_environment",
    "expand_env_vars",
    "expand_env_vars_in_dict",
)


def initterm(**kwds) -> Optional["console.Console"]:
    try:
        if not os.isatty(0):
            return None

    except (AttributeError, OSError):
        return None

    try:
        global _rc

        if _rc is None:
            kwds.setdefault("color_system", "truecolor")
            kwds.setdefault("file", sys.stderr)
            _rc = console.Console(**kwds)
            pretty.install(console=_rc)
            traceback.install(console=_rc, show_locals=True)

        return _rc

    except NameError:
        return None


def is_subdirectory(child: Path, parent: Path) -> bool:
    """Check if child is a subdirectory of parent.

    Args:
        child: Potential subdirectory path
        parent: Parent directory path

    Returns:
        True if child is same as or subdirectory of parent
    """
    child_abs = child.resolve()
    parent_abs = parent.resolve()

    return child_abs.is_relative_to(parent_abs)


def get_project_root() -> Path:
    """Get the current project root (where .magg directory is)."""
    return Path.cwd()


def get_subprocess_environment(*, inherit: bool = False, provided: dict | None = None) -> dict:
    """Get the environment for subprocesses.

    Args:
        inherit: If True, inherit the current environment.
        provided: Additional environment variables to include.

    Returns:
        A dictionary of environment variables.
    """
    env = os.environ.copy() if inherit else {}

    if provided:
        env.update(provided)

    return env


def expand_env_vars(value: str) -> str:
    """Expand environment variables in a string.

    Supports the following formats:
    - ${VAR} - expands to the value of VAR (or stays as-is if VAR doesn't exist)
    - ${VAR:-default} - expands to the value of VAR, or 'default' if VAR is unset

    Args:
        value: String potentially containing environment variable references

    Returns:
        String with environment variables expanded

    Examples:
        >>> os.environ['API_KEY'] = 'secret123'
        >>> expand_env_vars('Bearer ${API_KEY}')
        'Bearer secret123'
        >>> expand_env_vars('${MISSING:-default}')
        'default'
    """
    if not isinstance(value, str):
        return value

    # Pattern for ${VAR:-default} or ${VAR}
    def replace_braced(match):
        var_expr = match.group(1)
        if ':-' in var_expr:
            var_name, default = var_expr.split(':-', 1)
            return os.environ.get(var_name.strip(), default)
        return os.environ.get(var_expr, match.group(0))

    # Handle ${VAR:-default} and ${VAR}
    return re.sub(r'\$\{([^}]+)\}', replace_braced, value)


def expand_env_vars_in_dict(data: dict) -> dict:
    """Recursively expand environment variables in dictionary string values.

    Args:
        data: Dictionary potentially containing string values with env var references

    Returns:
        Dictionary with all string values expanded

    Examples:
        >>> os.environ['TOKEN'] = 'abc123'
        >>> expand_env_vars_in_dict({'auth': 'Bearer ${TOKEN}', 'count': 5})
        {'auth': 'Bearer abc123', 'count': 5}
    """
    if not isinstance(data, dict):
        return data

    result = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = expand_env_vars(value)
        elif isinstance(value, dict):
            result[key] = expand_env_vars_in_dict(value)
        elif isinstance(value, list):
            result[key] = [
                expand_env_vars(item) if isinstance(item, str)
                else expand_env_vars_in_dict(item) if isinstance(item, dict)
                else item
                for item in value
            ]
        else:
            result[key] = value

    return result
