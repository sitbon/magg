"""Helpers to locate package paths.

Used when searching for kits and mbro scripts.
"""
from pathlib import Path

from magg import contrib

__all__ = "get_contrib_paths", "contrib"


def get_contrib_paths() -> list[Path]:
    """Get all paths for contrib namespace packages."""
    return [Path(path) for path in contrib.__path__ if Path(path).is_dir()]
