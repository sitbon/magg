import os
import shutil
from pathlib import Path
from typing import Optional

try:
    from rich import console, pretty, traceback

    _rc: console.Console | None = None

except (ImportError, ModuleNotFoundError):
    pass

__all__ = "chown", "initterm", "is_subdirectory", "get_project_root"


def chown(path: Path, uid: int | str | None = None, gid: int | str | None = None, *, recursive: bool = False) -> None:
    if os.getuid() != 0:
        return

    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    gid = gid if gid is not None else uid
    shutil.chown(path, uid, gid if gid is not None else uid)

    if recursive and path.is_dir():
        for root, dirs, files in path.walk():
            for d in dirs:
                shutil.chown(root / d, uid, gid if gid is not None else uid)
            for f in files:
                shutil.chown(root / f, uid, gid if gid is not None else uid)


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
