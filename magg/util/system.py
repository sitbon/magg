import os
import shutil
import sys
from pathlib import Path
from typing import Optional

try:
    from rich import console, pretty, traceback

    _rc: console.Console | None = None

except (ImportError, ModuleNotFoundError):
    pass

__all__ = "initterm", "is_subdirectory", "get_project_root"


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
